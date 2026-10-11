"""امتیاز و نشان‌ها از دید مدیر: صف تأیید، تغییر دستی امتیاز، افزودن/حذف/ویرایش نشان.
هیچ امتیازی (تکلیف امتیازی یا نشان کوشا) بدون تأیید مدیر حساب نمی‌شود."""
from __future__ import annotations

import re

from . import jalali as J
from . import rules as R
from .bale import btn
from .core import App, Ctx
from .fa import clean, en, fa

BACK = [[btn("⬅ پنل مدیریت", "a:menu")]]
PER = 6


def tell(app: App, sid, text, rows=None):
    s = app.student(sid)
    if s and s["chat_id"]:
        app.send(s["chat_id"], text, rows)


# ---------- صف تأیید ----------
def pending_view(app: App, ctx: Ctx, offset: int = 0):
    total = app.conn.execute("SELECT COUNT(*) c FROM points_ledger WHERE status='pending'").fetchone()["c"]
    rows_db = app.conn.execute("SELECT l.*, s.full_name FROM points_ledger l JOIN students s ON s.id=l.student_id "
                               "WHERE l.status='pending' ORDER BY l.id LIMIT ? OFFSET ?", (PER, offset)).fetchall()
    if not rows_db:
        app.show(ctx, "✅ امتیاز در انتظار تأییدی نیست.", BACK)
        return
    lines = [f"⭐ امتیازهای در انتظار تأیید ({fa(total)} مورد)", ""]
    rows = []
    for r in rows_db:
        lines.append(f"{fa(r['id'])}) {r['full_name']} — {r['reason']} — +{fa(r['delta'])}")
        rows.append([btn(f"✅ تأیید {fa(r['id'])}", f"a:pok:{r['id']}"), btn(f"❌ رد {fa(r['id'])}", f"a:pno:{r['id']}")])
    rows.append([btn(f"✅ تأیید همه‌ی {fa(total)} مورد", "a:pall")])
    if total > offset + PER:
        rows.append([btn("بعدی ▶", f"a:pts:{offset + PER}")])
    rows += BACK
    app.show(ctx, "\n".join(lines), rows)


def _decide(app: App, ctx: Ctx, pid: int, status: str):
    r = app.conn.execute("SELECT * FROM points_ledger WHERE id=? AND status='pending'", (pid,)).fetchone()
    if not r:
        return False
    app.conn.execute("UPDATE points_ledger SET status=?, decided_ts=?, admin_id=? WHERE id=?", (status, app.now(), ctx.user_id, pid))
    app.conn.commit()
    app.audit(ctx.user_id, "points_" + status, f"{pid}:{r['student_id']}:{r['delta']}")
    if status == "approved":
        tot, _ = R.points_total(app.conn, r["student_id"])
        tell(app, r["student_id"], f"⭐ {fa(r['delta'])} امتیاز برای «{r['reason']}» تأیید شد!\nمجموع امتیاز تو: {fa(tot)}")
    return True


def approve(app, ctx, pid, offset=0):
    _decide(app, ctx, pid, "approved")
    pending_view(app, ctx, offset)


def reject(app, ctx, pid, offset=0):
    _decide(app, ctx, pid, "rejected")
    pending_view(app, ctx, offset)


def approve_all(app, ctx):
    ids = [r["id"] for r in app.conn.execute("SELECT id FROM points_ledger WHERE status='pending' ORDER BY id")]
    n = sum(1 for i in ids if _decide(app, ctx, i, "approved"))
    app.show(ctx, f"✅ {fa(n)} مورد تأیید شد.", BACK)


# ---------- امتیاز یک نفر ----------
def student_points(app: App, ctx: Ctx, sid: int):
    s = app.student(sid)
    tot, pend = R.points_total(app.conn, sid)
    rows_db = app.conn.execute("SELECT * FROM points_ledger WHERE student_id=? ORDER BY id DESC LIMIT 12", (sid,)).fetchall()
    mark = {"approved": "✅", "pending": "⏳", "rejected": "❌"}
    lines = [f"⭐ امتیاز {s['full_name']}", f"تأییدشده: {fa(tot)} | در انتظار: {fa(pend)}", "", "آخرین تغییرها:"]
    for r in rows_db:
        sign = "+" if r["delta"] > 0 else ""
        lines.append(f"{mark[r['status']]} {sign}{fa(r['delta'])} — {r['reason']} — {J.fmt_short(r['created_ts']).split(' ')[0]}")
    if not rows_db:
        lines.append("—")
    app.show(ctx, "\n".join(lines), [[btn("➕/➖ تغییر دستی امتیاز", f"a:padj:{sid}")], [btn("⬅ دانش‌آموز", f"a:st:{sid}")]])


def st_padj(app, ctx, msg, text, data):
    m = re.match(r"^([+\-−]?\d{1,4})\s*(.*)$", en(text).replace("−", "-"))
    if not m or int(m.group(1)) == 0:
        app.send(ctx.chat_id, "با عدد شروع کن؛ مثلاً: +5 مشارکت عالی در کلاس   یا   -3 تاخیر")
        return
    delta, reason = int(m.group(1)), clean(m.group(2)) or "تغییر دستی مدیر"
    sid = data["sid"]
    R.add_points(app.conn, sid, delta, reason, "manual", None, None, app.now(), "approved", ctx.user_id)
    app.audit(ctx.user_id, "points_manual", f"{sid}:{delta}:{reason}")
    app.clear_state(ctx.chat_id)
    tot, _ = R.points_total(app.conn, sid)
    sign = "+" if delta > 0 else ""
    tell(app, sid, f"⭐ مدیر امتیاز تو را تغییر داد: {sign}{fa(delta)} ({reason})\nمجموع امتیاز تو: {fa(tot)}")
    app.send(ctx.chat_id, f"✅ ثبت شد. مجموع امتیاز {app.student(sid)['full_name']}: {fa(tot)}", [[btn("⬅ امتیازها", f"a:spts:{sid}")]])


# ---------- مدیریت نشان‌ها ----------
def badges_view(app: App, ctx: Ctx, sid: int):
    s = app.student(sid)
    bs = app.conn.execute("SELECT * FROM badges WHERE student_id=? ORDER BY awarded_ts", (sid,)).fetchall()
    rows = []
    for b in bs:
        rows.append([btn(f"✏ {b['title']}"[:34], f"a:sbde:{b['id']}"), btn("🗑", f"a:sbdd:{b['id']}")])
    rows.append([btn("➕ نشان دستی جدید", f"a:bds:{sid}")])
    rows.append([btn("⬅ دانش‌آموز", f"a:st:{sid}")])
    app.show(ctx, f"🏅 نشان‌های {s['full_name']} ({fa(len(bs))} نشان)\n✏ ویرایش عنوان | 🗑 حذف" +
             ("" if bs else "\n\nنشانی ندارد."), rows)


def badge_delete(app: App, ctx: Ctx, bid: int, confirm: bool):
    b = app.conn.execute("SELECT * FROM badges WHERE id=?", (bid,)).fetchone()
    if not b:
        app.show(ctx, "نشان پیدا نشد.", BACK)
        return
    if not confirm:
        app.show(ctx, f"نشان «{b['title']}» حذف شود؟\n(نشان خودکار حذف‌شده دوباره خودکار داده نمی‌شود؛ امتیاز در انتظارِ آن رد می‌شود.)",
                 [[btn("✅ بله، حذف شود", f"a:sbddy:{bid}"), btn("↩ انصراف", f"a:sbd:{b['student_id']}")]])
        return
    sid = b["student_id"]
    app.conn.execute("DELETE FROM badges WHERE id=?", (bid,))
    if b["code"] != "manual":
        app.conn.execute("INSERT OR IGNORE INTO badge_blocks VALUES(?,?,?)", (sid, b["code"], b["key"]))
    app.conn.execute("UPDATE points_ledger SET status='rejected', decided_ts=?, admin_id=? "
                     "WHERE student_id=? AND kind='badge' AND source_code=? AND source_key=? AND status='pending'",
                     (app.now(), ctx.user_id, sid, b["code"], b["key"]))
    app.conn.commit()
    app.audit(ctx.user_id, "badge_delete", f"{sid}:{b['code']}:{b['key']}")
    badges_view(app, ctx, sid)


def st_sbde(app, ctx, msg, text, data):
    if not text:
        app.send(ctx.chat_id, "عنوان جدید را بنویس.")
        return
    b = app.conn.execute("SELECT * FROM badges WHERE id=?", (data["bid"],)).fetchone()
    app.conn.execute("UPDATE badges SET title=? WHERE id=?", (text, data["bid"]))
    app.conn.commit()
    app.audit(ctx.user_id, "badge_edit", f"{data['bid']}")
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, "✅ عنوان نشان ویرایش شد.", [[btn("⬅ نشان‌ها", f"a:sbd:{b['student_id']}")]])
