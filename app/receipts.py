"""رسید واریزی: دانش‌آموز یک عکس یا PDF می‌فرستد و تمام؛ مدیر در بات یا پنل می‌بیند و «دریافت شد» می‌زند."""
from __future__ import annotations

import logging
import secrets
from pathlib import Path

from . import jalali as J
from .bale import BaleError, btn
from .core import App, Ctx
from .fa import clean, fa

log = logging.getLogger("rosh.receipts")

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
PAGE = 8
BACK = [[btn("⬅ منوی اصلی", "s:home")]]


def new_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) c FROM receipts WHERE status='new'").fetchone()["c"]


# ---------- دانش‌آموز ----------
def ask(app: App, ctx: Ctx, st):
    app.set_state(ctx.chat_id, "s:rcpt", {})
    app.send(ctx.chat_id, "🧾 رسید واریزی را همین‌جا بفرست: عکس یا PDF، یا اگر فایل نداری، شماره‌ی پیگیری و مشخصات واریز را به‌صورت متن بنویس.\nیک متن کوتاه (مثلاً ماه یا مبلغ) هم می‌توانی کنار عکس بنویسی.",
             [[btn("❌ لغو", "s:home")]])


def on_message(app: App, ctx: Ctx, st, msg):
    from .student import _extract, home
    got = _extract(msg)
    cancel = [[btn("❌ لغو", "s:home")]]
    if not got:
        text = clean(msg.get("text") or "")
        if len(text) < 3:
            app.send(ctx.chat_id, "عکس یا PDF رسید را بفرست، یا مشخصات واریز را به‌صورت متن بنویس.", cancel)
            return
        cur = app.conn.execute("INSERT INTO receipts(student_id,path,name,note,ts,status) VALUES(?,?,?,?,?, 'new')",
                               (st["id"], "", None, text[:500], app.now()))
        app.conn.commit()
        _done(app, ctx, st, cur.lastrowid, text[:500])
        return
    file_id, name, ext, size = got
    if ext not in ALLOWED_EXT:
        app.send(ctx.chat_id, "فقط عکس (jpg، png، webp، heic) یا PDF قبول است.", cancel)
        return
    cap = app.cfg.max_file_mb * 1024 * 1024
    if size and size > cap:
        app.send(ctx.chat_id, f"حجم فایل بیشتر از {fa(app.cfg.max_file_mb)} مگابایت است.", cancel)
        return
    dest = app.data / "receipts" / str(st["id"]) / f"{app.now()}_{secrets.token_hex(3)}{ext}"
    try:
        real = app.bale.download(file_id, dest)
    except BaleError as e:
        log.warning("دانلود رسید ناموفق: %s", e)
        app.send(ctx.chat_id, "دریافت فایل ناموفق بود؛ دوباره بفرست.", cancel)
        return
    if real > cap:
        dest.unlink(missing_ok=True)
        app.send(ctx.chat_id, f"حجم فایل بیشتر از {fa(app.cfg.max_file_mb)} مگابایت است.", cancel)
        return
    note = clean(msg.get("caption") or "")[:200]
    cur = app.conn.execute("INSERT INTO receipts(student_id,path,name,note,ts,status) VALUES(?,?,?,?,?, 'new')",
                           (st["id"], str(dest), name, note or None, app.now()))
    app.conn.commit()
    _done(app, ctx, st, cur.lastrowid, note)


def _done(app: App, ctx: Ctx, st, rid: int, note: str):
    from .student import home
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, "✅ رسیدت دریافت شد. ممنون! 🙏\nبعد از بررسی، مدیر خبرت می‌کند.")
    for adm in app.admin_ids():
        app.send(adm, f"🧾 رسید تازه از {st['full_name']}" + (f"\n{note}" if note else ""), [[btn("👁 دیدن رسید", f"a:rcv:{rid}")]])
    home(app, ctx, st)


# ---------- مدیر در بات ----------
def lst(app: App, ctx: Ctx, offset: int = 0, sid: int = 0):
    """فهرست رسیدها؛ با sid فقط رسیدهای همان دانش‌آموز."""
    where, args = ("WHERE r.student_id=?", [sid]) if sid else ("", [])
    suffix = f":{sid}" if sid else ""
    total = app.conn.execute(f"SELECT COUNT(*) c FROM receipts r {where}", args).fetchone()["c"]
    rows_db = app.conn.execute(f"SELECT r.*, s.full_name FROM receipts r JOIN students s ON s.id=r.student_id {where} "
                               "ORDER BY (r.status='new') DESC, r.ts DESC LIMIT ? OFFSET ?", args + [PAGE, offset]).fetchall()
    back = [btn("⬅ دانش‌آموز", f"a:st:{sid}")] if sid else [btn("⬅ پنل مدیریت", "a:menu")]
    if not rows_db:
        app.show(ctx, "هنوز رسیدی نرسیده است.", [back])
        return
    rows = [[btn(f"{'🆕' if r['status'] == 'new' else '✅'} {'📝 ' if not r['path'] else ''}{r['full_name']} — {J.fmt_short(r['ts'])}"[:56], f"a:rcv:{r['id']}")] for r in rows_db]
    nav = []
    if offset > 0:
        nav.append(btn("⬅ قبلی", f"a:rcp:{max(0, offset - PAGE)}{suffix}"))
    if offset + PAGE < total:
        nav.append(btn("بعدی ➡", f"a:rcp:{offset + PAGE}{suffix}"))
    if nav:
        rows.append(nav)
    rows.append(back)
    app.show(ctx, f"🧾 رسیدها ({fa(total)} مورد؛ 🆕 = هنوز بررسی نشده، 📝 = رسید متنی)", rows)


def view(app: App, ctx: Ctx, rid: int):
    r = app.conn.execute("SELECT r.*, s.full_name FROM receipts r JOIN students s ON s.id=r.student_id WHERE r.id=?", (rid,)).fetchone()
    if not r:
        app.show(ctx, "رسید پیدا نشد.", [[btn("⬅ رسیدها", "a:rcp:0")]])
        return
    head = f"🧾 {r['full_name']} — {J.fmt_short(r['ts'])}" + (f"\n{r['note']}" if r["note"] else "")
    if r["path"]:
        app.send_file(ctx.chat_id, r["path"], head)
    else:
        app.send(ctx.chat_id, head + "\n(رسید متنی؛ فایلی ندارد)")
    rows = ([[btn("✅ دریافت شد", f"a:rco:{rid}")]] if r["status"] == "new" else []) + [[btn("⬅ رسیدها", "a:rcp:0")]]
    app.send(ctx.chat_id, "وضعیت: " + ("🆕 بررسی‌نشده" if r["status"] == "new" else f"✅ دریافت‌شده ({J.fmt_short(r['seen_ts'])})"), rows)


def mark_seen(app: App, admin_id: int, rid: int):
    r = app.conn.execute("SELECT * FROM receipts WHERE id=?", (rid,)).fetchone()
    if not r:
        return False, "رسید پیدا نشد."
    if r["status"] == "new":
        app.conn.execute("UPDATE receipts SET status='seen', seen_ts=?, admin_id=? WHERE id=?", (app.now(), admin_id, rid))
        app.conn.commit()
        app.audit(admin_id, "receipt_seen", f"{rid}:{r['student_id']}")
        s = app.student(r["student_id"])
        if s and s["chat_id"]:
            app.send(s["chat_id"], f"✅ رسیدی که {J.fmt_short(r['ts'])} فرستادی بررسی و دریافت شد. ممنون! 🙏")
    return True, "رسید دریافت‌شده ثبت شد و به دانش‌آموز خبر رفت."
