"""آزمون پنل وب: ورود با کد یک‌بارمصرف، صفحه‌ها، فقط‌خواندنی‌بودن، امنیت فایل‌ها."""
import http.client, os, re, sqlite3, sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app import db, router, panel, jalali as J
from app.config import Config
from app.core import App
from app.fa import en
from test_flow import FakeBale, upd, go, ADMIN, STU

H = 3600


def setup():
    d = Path(tempfile.mkdtemp())
    cfg = Config(token="tok:123", admin_ids={ADMIN}, data_dir=d)
    bale = FakeBale()
    conn = db.connect(d / "rosh.db")
    app = App(cfg, bale, conn)
    app._t = int(time.time())  # پنل از ساعت واقعی سیستم استفاده می‌کند؛ ساعت آزمون هم باید با آن هم‌خوان باشد
    app.clock = lambda: app._t
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd"), upd(ADMIN, "علی رضایی | گروه الف\n<script>alert(1)</script>"))
    ali = conn.execute("SELECT * FROM students ORDER BY id").fetchone()
    conn.execute("UPDATE students SET chat_id=? WHERE id=?", (STU, ali["id"])); conn.commit()
    dl = app._t + 10 * H
    conn.execute("INSERT INTO assignments(title,description,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ریاضی ۱','حل کنید','required',?,20,24,1,?)", (dl, app._t))
    conn.commit()
    go(app, upd(STU, data="s:send:1"), upd(STU, photo=True), upd(STU, data="s:fin"))
    go(app, upd(ADMIN, data=f"a:fbs:{ali['id']}:1"), upd(ADMIN, "کارت عالی بود"))
    return app, bale, cfg


def web_code(app, bale):
    go(app, upd(ADMIN, data="a:web"))
    txt = [t for t in bale.texts(ADMIN) if "کد ورود به پنل وب" in t][-1]
    return re.search(r"(\d{8})", en(txt)).group(1)


class Client:
    def __init__(self, port): self.port, self.cookie = port, ""

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Cookie": self.cookie} if self.cookie else {}
        if body is not None:
            h["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body=body, headers=h)
        r = c.getresponse(); data = r.read()
        sc = r.getheader("Set-Cookie")
        if sc and "rosh_session=" in sc:
            v = sc.split("rosh_session=")[1].split(";")[0]
            self.cookie = f"rosh_session={v}" if v else ""
        return r.status, r, data

    def login(self, code):
        return self.req("POST", "/login", f"code={code}")


def test_panel_all():
    app, bale, cfg = setup()
    srv = panel.make_server(cfg, "127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cl = Client(port)
        # بدون ورود: هدایت به صفحه‌ی ورود
        st, r, _ = cl.req("GET", "/")
        assert st == 303 and r.getheader("Location") == "/login"
        st, r, body = cl.req("GET", "/login")
        assert st == 200 and 'dir="rtl"' in body.decode() and "ورود به پنل رشد" in body.decode()
        # کد اشتباه
        st, _, _ = cl.login("12345678"); assert st == 401
        # کد درست (یک‌بارمصرف)
        code = web_code(app, bale)
        st, r, _ = cl.login(code)
        assert st == 303 and "HttpOnly" in r.getheader("Set-Cookie") and "SameSite=Strict" in r.getheader("Set-Cookie")
        other = Client(port)
        st, _, _ = other.login(code); assert st == 401, "کد دوم‌بار نباید کار کند"
        # صفحه‌ها
        for path in ["/", "/students", "/assignments", "/badges", "/feedback", "/audit", "/student/1", "/assignment/1"]:
            st, r, body = cl.req("GET", path)
            text = body.decode()
            assert st == 200, path
            assert 'dir="rtl"' in text and "Vazirmatn" in text, path
            assert "<script>alert(1)</script>" not in text, "XSS: نام باید escape شود"
        st, _, body = cl.req("GET", "/"); t = body.decode()
        assert "علی رضایی" in t and "داشبورد" in t
        st, _, body = cl.req("GET", "/student/1"); t = body.decode()
        assert "کارت عالی بود" in t and "اولین قدم" in t and "/file/1" in t
        st, _, body = cl.req("GET", "/assignment/1"); assert "ریاضی ۱" in body.decode() and "به‌موقع" in body.decode()
        assert cl.req("GET", "/student/999")[0] == 404
        # فایل‌ها
        st, r, body = cl.req("GET", "/file/1"); assert st == 200 and body == b"fake-image-bytes"
        assert r.getheader("X-Content-Type-Options") == "nosniff"
        st, r, body = cl.req("GET", "/zip/1"); assert st == 200 and body[:2] == b"PK"
        st, r, body = cl.req("GET", "/zip-student/1"); assert st == 200 and body[:2] == b"PK"
        st, r, body = cl.req("GET", "/export.xlsx"); assert st == 200 and body[:2] == b"PK"
        assert cl.req("GET", "/static/panel.js")[0] == 200
        assert cl.req("GET", "/static/../../etc/passwd")[0] == 404
        # فقط‌خواندنی: هر درخواست غیر GET پس از ورود رد می‌شود
        assert cl.req("POST", "/assignments", "title=x")[0] == 405
        ro = panel.open_ro(cfg)
        try:
            ro.execute("INSERT INTO groups(name) VALUES('x')"); assert False, "نباید بتوان نوشت"
        except sqlite3.Error:
            pass
        ro.close()
        # خروج از مسیر پوشه‌ی داده ممکن نیست
        app.conn.execute("UPDATE submission_files SET path='/etc/passwd' WHERE id=1"); app.conn.commit()
        assert cl.req("GET", "/file/1")[0] == 404
        # کد منقضی
        code2 = web_code(app, bale)
        app.conn.execute("UPDATE web_logins SET expires_ts=?", (int(time.time()) - 5,)); app.conn.commit()
        assert Client(port).login(code2)[0] == 401
        # خروج
        assert cl.req("POST", "/logout")[0] == 303
        assert cl.req("GET", "/")[0] == 303
        # محدودیت تلاش ورود
        c3 = Client(port)
        codes = [c3.login(f"0000000{i}")[0] for i in range(6)]
        assert codes[-1] == 429, codes
    finally:
        srv.shutdown()


def test_embedded_panel_thread():
    """PANEL_ENABLE=1: پنل داخل فرایند بات بالا می‌آید و غیرفعال بودنش چیزی بالا نمی‌آورد."""
    from app import main
    d = Path(tempfile.mkdtemp()); db.connect(d / "rosh.db").close()
    off = Config(token="t", admin_ids={1}, data_dir=d, panel_port=0)
    assert main.start_panel(off) is None
    on = Config(token="t", admin_ids={1}, data_dir=d, panel_port=0, panel_enable=True)
    srv = main.start_panel(on)
    try:
        st, _, body = Client(srv.server_address[1]).req("GET", "/login")
        assert st == 200 and "ورود به پنل رشد" in body.decode()
    finally:
        srv.shutdown()


def test_web_code_hash_only():
    app, bale, cfg = setup()
    code = web_code(app, bale)
    rows = app.conn.execute("SELECT * FROM web_logins").fetchall()
    assert len(rows) == 1 and code not in rows[0]["code_hash"] and len(rows[0]["code_hash"]) == 64


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
