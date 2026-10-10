"""پنل وب فقط‌خواندنی «رشد»  —  اجرا: python -m app.panel

اصول طراحی
• فرایند جدا از بات است و دیتابیس اصلی را فقط‌خواندنی باز می‌کند (mode=ro / query_only)؛ پس حتی با باگ هم چیزی را عوض نمی‌کند.
• ورود: مدیر در بات «🌐 ورود به پنل وب» را می‌زند و یک کد ۸ رقمی یک‌بارمصرف (۵ دقیقه) می‌گیرد؛ رمز عبور نداریم.
• نشست‌ها و کدهای مصرف‌شده در یک فایل جدا (panel.db) نگه داشته می‌شوند، نه در دیتابیس اصلی.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import mimetypes
import secrets
import sqlite3
import tempfile
import threading
import time
import zipfile
from contextlib import closing
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import config, panel_ui as UI, reports
from .fa import en

log = logging.getLogger("rosh.panel")

COOKIE = "rosh_session"
SESSION_TTL = 12 * 3600
LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW = 600
INLINE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


# ---------- دیتابیس ----------
def open_ro(cfg) -> sqlite3.Connection:
    """اتصال فقط‌خواندنی به دیتابیس اصلی."""
    path = (Path(cfg.data_dir) / "rosh.db").resolve()
    try:
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.Error:
        conn = sqlite3.connect(str(path), timeout=10)  # راه جایگزین؛ نوشتن را در سطح اتصال قفل می‌کنیم
    conn.execute("PRAGMA query_only=ON")
    conn.row_factory = sqlite3.Row
    return conn


class Store:
    """نشست‌ها و کدهای مصرف‌شده (فایل جدا از دیتابیس اصلی)."""

    def __init__(self, path: Path):
        self.path = str(path)
        with closing(self._c()) as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, admin_id INTEGER, expires_ts INTEGER);
            CREATE TABLE IF NOT EXISTS used_codes(code_hash TEXT PRIMARY KEY, ts INTEGER);
            """)
            c.commit()

    def _c(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def _h(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def consume_code(self, code_hash: str, now: int) -> bool:
        with closing(self._c()) as c:
            try:
                c.execute("INSERT INTO used_codes VALUES(?,?)", (code_hash, now))
                c.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def new_session(self, admin_id: int, now: int) -> str:
        token = secrets.token_urlsafe(32)
        with closing(self._c()) as c:
            c.execute("DELETE FROM sessions WHERE expires_ts<?", (now,))
            c.execute("DELETE FROM used_codes WHERE ts<?", (now - 3600,))
            c.execute("INSERT INTO sessions VALUES(?,?,?)", (self._h(token), admin_id, now + SESSION_TTL))
            c.commit()
        return token

    def session_admin(self, token: str, now: int):
        if not token:
            return None
        with closing(self._c()) as c:
            r = c.execute("SELECT admin_id FROM sessions WHERE token_hash=? AND expires_ts>?", (self._h(token), now)).fetchone()
        return r[0] if r else None

    def drop(self, token: str):
        if token:
            with closing(self._c()) as c:
                c.execute("DELETE FROM sessions WHERE token_hash=?", (self._h(token),))
                c.commit()


def code_hash(cfg, code: str) -> str:
    return hmac.new(cfg.token.encode(), code.encode(), hashlib.sha256).hexdigest()


# ---------- سرور ----------
class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, cfg, addr):
        super().__init__(addr, Handler)
        self.cfg = cfg
        self.store = Store(Path(cfg.data_dir) / "panel.db")
        self.fails: dict = {}
        self.lock = threading.Lock()
        self.assets = Path(__file__).resolve().parent.parent / "assets"
        self.logo = (self.assets / "logo.png").exists()

    # محدودیت تلاش ورود به‌ازای IP
    def too_many(self, ip: str, now: int) -> bool:
        with self.lock:
            lst = [t for t in self.fails.get(ip, []) if t > now - LOGIN_FAIL_WINDOW]
            self.fails[ip] = lst
            return len(lst) >= LOGIN_FAIL_LIMIT

    def add_fail(self, ip: str, now: int):
        with self.lock:
            self.fails.setdefault(ip, []).append(now)


class Handler(BaseHTTPRequestHandler):
    server_version = "RoshPanel"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # لاگ پیش‌فرض را خاموش می‌کنیم؛ مسیرها نباید بی‌دلیل ثبت شوند
        pass

    # --- ابزارها
    def ip(self) -> str:
        if self.server.cfg.panel_trust_proxy:
            xff = self.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[0].strip()
        return self.client_address[0]

    def cookie(self) -> str:
        try:
            c = SimpleCookie(self.headers.get("Cookie", ""))
            return c[COOKIE].value if COOKIE in c else ""
        except Exception:
            return ""

    def _headers(self, ctype, length, extra=None, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
                         "font-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)

    def html(self, body: str, status=200, extra=None):
        data = body.encode("utf-8")
        h = {"Cache-Control": "no-store"}
        h.update(extra or {})
        self._headers("text/html; charset=utf-8", len(data), h, status)
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, to: str, extra=None):
        self.send_response(303)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def set_cookie(self, token: str, max_age: int) -> dict:
        flags = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        if self.server.cfg.panel_secure_cookie:
            flags += "; Secure"
        return {"Set-Cookie": flags}

    def send_bytes(self, data: bytes, ctype: str, extra=None):
        self._headers(ctype, len(data), extra)
        self.end_headers()
        self.wfile.write(data)

    def send_path(self, path: Path, ctype: str, extra=None, delete_after=False):
        size = path.stat().st_size
        self._headers(ctype, size, extra)
        self.end_headers()
        try:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        finally:
            if delete_after:
                path.unlink(missing_ok=True)

    # --- مسیریابی
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        try:
            self.route("POST")
        finally:
            self.close_connection = True  # بدنه‌ی خوانده‌نشده نباید روی درخواست بعدی اثر بگذارد

    def route(self, method: str):
        try:
            self._route(method)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            log.exception("خطا در پنل")
            try:
                self.html(UI.layout("خطا", '<div class="card"><h1>مشکلی پیش آمد</h1><p><a href="/">بازگشت</a></p></div>', logged=False), 500)
            except Exception:
                pass

    def _route(self, method: str):
        srv: PanelServer = self.server
        u = urlparse(self.path)
        path = u.path
        now = int(time.time())

        if path.startswith("/static/") and method == "GET":
            return self.static(path[len("/static/"):])
        if path == "/login":
            if method == "POST":
                return self.do_login(now)
            return self.html(UI.login_page(logo=srv.logo))
        if path == "/logout" and method == "POST":
            srv.store.drop(self.cookie())
            return self.redirect("/login", self.set_cookie("", 0))

        admin_id = srv.store.session_admin(self.cookie(), now)
        if not admin_id:
            return self.redirect("/login")
        if method != "GET":
            return self.html(UI.not_found(srv.logo), 405)  # پنل فقط‌خواندنی است

        cfg = srv.cfg
        logo = srv.logo
        with closing(open_ro(cfg)) as conn:
            pages = {"/": UI.dashboard, "/students": UI.students_page, "/assignments": UI.assignments_page,
                     "/badges": UI.badges_page, "/feedback": UI.feedback_page, "/audit": UI.audit_page}
            if path in pages:
                return self.html(pages[path](conn, cfg, now, logo=logo))
            seg = [p for p in path.split("/") if p]
            if len(seg) == 2 and seg[1].isdigit():
                kind, ident = seg[0], int(seg[1])
                if kind == "student":
                    page = UI.student_page(conn, cfg, now, ident, logo=logo)
                    return self.html(page) if page else self.html(UI.not_found(logo), 404)
                if kind == "assignment":
                    page = UI.assignment_page(conn, cfg, now, ident, logo=logo)
                    return self.html(page) if page else self.html(UI.not_found(logo), 404)
                if kind == "file":
                    return self.serve_file(conn, "submission_files", ident)
                if kind == "afile":
                    return self.serve_file(conn, "assignment_files", ident)
                if kind == "zip":
                    return self.serve_zip(conn, aid=ident)
                if kind == "zip-student":
                    return self.serve_zip(conn, sid=ident)
            if path == "/export.xlsx":
                return self.serve_xlsx(conn, now)
        return self.html(UI.not_found(logo), 404)

    # --- ورود
    def do_login(self, now: int):
        srv: PanelServer = self.server
        ip = self.ip()
        if srv.too_many(ip, now):
            return self.html(UI.login_page("تلاش‌های ناموفق زیاد بود؛ ۱۰ دقیقه بعد دوباره امتحان کن.", srv.logo), 429)
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        form = parse_qs(self.rfile.read(min(n, 2048)).decode("utf-8", "ignore"))
        code = en((form.get("code", [""])[0])).strip().replace(" ", "")
        admin_id = None
        if code.isdigit() and len(code) == 8:
            h = code_hash(srv.cfg, code)
            with closing(open_ro(srv.cfg)) as conn:
                try:
                    r = conn.execute("SELECT admin_id FROM web_logins WHERE code_hash=? AND expires_ts>?", (h, now)).fetchone()
                except sqlite3.Error:
                    r = None
            if r and srv.store.consume_code(h, now):
                admin_id = r["admin_id"]
        if not admin_id:
            srv.add_fail(ip, now)
            return self.html(UI.login_page("کد درست نیست یا منقضی شده است. از بات کد تازه بگیر.", srv.logo), 401)
        token = srv.store.new_session(admin_id, now)
        return self.redirect("/", self.set_cookie(token, SESSION_TTL))

    # --- فایل‌ها
    def static(self, name: str):
        srv: PanelServer = self.server
        if name == "panel.js":
            return self.send_bytes(UI.JS.encode(), "application/javascript; charset=utf-8", {"Cache-Control": "public, max-age=3600"})
        allowed = {"Vazirmatn-Regular.woff2": "font/woff2", "Vazirmatn-Bold.woff2": "font/woff2", "logo.png": "image/png"}
        if name in allowed and (srv.assets / name).exists():
            return self.send_path(srv.assets / name, allowed[name], {"Cache-Control": "public, max-age=86400"})
        return self.html(UI.not_found(srv.logo), 404)

    def serve_file(self, conn, table: str, fid: int):
        row = conn.execute(f"SELECT path FROM {table} WHERE id=?", (fid,)).fetchone()  # نام جدول ثابت است، از ورودی نمی‌آید
        if not row:
            return self.html(UI.not_found(self.server.logo), 404)
        base = Path(self.server.cfg.data_dir).resolve()
        p = Path(row["path"]).resolve()
        if base not in p.parents or not p.is_file():  # جلوگیری از خروج از پوشه‌ی داده
            return self.html(UI.not_found(self.server.logo), 404)
        ext = p.suffix.lower()
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        disp = "inline" if ext in INLINE_TYPES else "attachment"
        return self.send_path(p, ctype, {"Content-Disposition": f"{disp}; filename*=UTF-8''{quote(p.name)}", "Cache-Control": "private, max-age=300"})

    def serve_zip(self, conn, aid=None, sid=None):
        srv: PanelServer = self.server
        rows = reports._final_files(conn, aid, sid)
        if not rows:
            return self.html(UI.layout("پاسخی نیست", '<div class="card"><h1>پاسخی برای دانلود نیست</h1><p><a href="javascript:history.back()">بازگشت</a></p></div>', logo=srv.logo), 404)
        base = Path(srv.cfg.data_dir).resolve()
        tmp = Path(tempfile.mkdtemp(dir=str(base / "exports"))) if (base / "exports").exists() else Path(tempfile.mkdtemp())
        zp = tmp / "answers.zip"
        counters: dict = {}
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
            for r in rows:
                p = Path(r["path"]).resolve()
                if base not in p.parents or not p.is_file():
                    continue
                key = (r["student_id"], r["assignment_id"])
                counters[key] = counters.get(key, 0) + 1
                if aid is not None:
                    arc = f"{reports.safe_name(r['full_name'])}_{counters[key]}{p.suffix}"
                else:
                    arc = f"{reports.safe_name(r['title'])}/{counters[key]}{p.suffix}"
                z.write(p, arc)
        label = rows[0]["title"] if aid is not None else rows[0]["full_name"]
        try:
            self.send_path(zp, "application/zip", {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(reports.safe_name(label))}.zip"}, delete_after=True)
        finally:
            try:
                tmp.rmdir()
            except OSError:
                pass

    def serve_xlsx(self, conn, now: int):
        cfg = self.server.cfg

        class _App:  # جایگزین سبک برای گزارش‌ساز اکسل (فقط می‌خواند)
            pass
        a = _App()
        a.conn, a.cfg = conn, cfg
        a.now = lambda: now
        exports = Path(cfg.data_dir).resolve() / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        tmp = exports / f"web_{secrets.token_hex(6)}.xlsx"
        reports.build_xlsx(a, tmp)
        self.send_path(tmp, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       {"Content-Disposition": "attachment; filename=\"rosh-report.xlsx\""}, delete_after=True)


def make_server(cfg, host=None, port=None) -> PanelServer:
    return PanelServer(cfg, (host or cfg.panel_host, cfg.panel_port if port is None else port))


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = config.load()
    if not (Path(cfg.data_dir) / "rosh.db").exists():
        raise SystemExit("دیتابیس پیدا نشد؛ اول یک‌بار بات را اجرا کنید (python -m app.main).")
    srv = make_server(cfg)
    where = cfg.panel_url or f"http://localhost:{cfg.panel_port}"
    if cfg.panel_host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("پنل روی %s گوش می‌دهد؛ حتماً پشت HTTPS (Caddy/Nginx) سرو شود.", cfg.panel_host)
    log.info("پنل وب «رشد» آماده است: %s  (فقط‌خواندنی)", where)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
