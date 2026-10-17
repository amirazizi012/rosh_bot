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
def pending_count(conn) -> int:
    """تعداد موردهای منتظر تأیید: نشان‌های پشتکار/کوشا + امتیاز تکلیف‌های امتیازی."""
    b = conn.execute("SELECT COUNT(*) c FROM badges WHERE status='pending'").fetchone()["c"]
    p = conn.execute("SELECT COUNT(*) c FROM points_ledger WHERE status='pending' AND kind<>'badge'").fetchone()["c"]
    return b + p


def _pending_items(app: App):
    items = []
    for b in app.conn.execute("SELECT b.*, s.full_name FROM badges b JOIN students s ON s.id=b.student_id WHERE b.status='pending'"):
        pts = app.conn.execute("SELECT delta FROM points_ledger WHERE student_id=? AND kind='badge' AND source_code=? AND source_key=? "
                               "AND status='pending'", (b["student_id"], b["code"], b["key"])).fetchone()
        items.append((b["awarded_ts"], "badge", b, pts["delta"] if pts else 0))
    for r in app.conn.execute("SELECT l.*, s.full_name FROM points_ledger l JOIN students s ON s.id=l.student_id "
                              "WHERE l.status='pending' AND l.kind<>'badge'"):
        items.append((r["created_ts"], "points", r, r["delta"]))
    return sorted(items, key=lambda x: x[0])


def pending_view(app: App, ctx: Ctx, offset: int = 0):
    items = _pending_items(app)
    if not items:
        app.show(ctx, "✅ نشان یا امتیازی در انتظار تأیید نیست.", BACK)
        return
    lines = [f"⭐ در انتظار تأیید شما ({fa(len(items))} مورد)", ""]
    rows = []
    for n, (_, kind, r, delta) in enumerate(items[offset:offset + PER], 1):
        if kind == "badge":
            lines.append(f"{fa(n)}) 🏅 {r['full_name']} — {r['title']}" + (f" (+{fa(delta)} امتیاز)" if delta else ""))
            rows.append([btn(f"✅ تأیید {fa(n)}", f"a:bok:{r['id']}"), btn(f"❌ رد {fa(n)}", f"a:bno:{r['id']}")])
        else:
            lines.append(f"{fa(n)}) ⭐ {r['full_name']} — {r['reason']} — +{fa(delta)}")
            rows.append([btn(f"✅ تأیید {fa(n)}", f"a:pok:{r['id']}"), btn(f"❌ رد {fa(n)}", f"a:pno:{r['id']}")])
    rows.append([btn(f"✅ تأیید همه‌ی {fa(len(items))} مورد", "a:pall")])
    if len(items) > offset + PER:
        rows.append([btn("بعدی ▶", f"a:pts:{offset + PER}")])
    rows.append([btn("💡 اگر یکی از تکالیف ایراد دارد، از «بررسی تکالیف» وضعیتش را ناقص کنید", "a:slist:0")])
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


def approve_badge(app: App, ctx: Ctx, bid: int, offset: int = 0, quiet: bool = False):
    b = app.conn.execute("SELECT * FROM badges WHERE id=? AND status='pending'", (bid,)).fetchone()
    if not b:
        return False
    app.conn.execute("UPDATE badges SET status='approved', awarded_ts=? WHERE id=?", (app.now(), bid))
    led = app.conn.execute("SELECT * FROM points_ledger WHERE student_id=? AND kind='badge' AND source_code=? AND source_key=? "
                           "AND status='pending'", (b["student_id"], b["code"], b["key"])).fetchone()
    pts = 0
    if led:
        app.conn.execute("UPDATE points_ledger SET status='approved', decided_ts=?, admin_id=? WHERE id=?", (app.now(), ctx.user_id, led["id"]))
        pts = led["delta"]
    app.conn.commit()
    app.audit(ctx.user_id, "badge_approve", f"{b['student_id']}:{b['code']}:{b['key']}")
    tell(app, b["student_id"], f"🎉 نشان تازه گرفتی!\n{b['title']}" + (f"\n⭐ {fa(pts)} امتیاز هم به تو اضافه شد." if pts else ""))
    if not quiet:
        pending_view(app, ctx, offset)
    return True


def reject_badge(app: App, ctx: Ctx, bid: int):
    """رد نشان در انتظار: نشان حذف و مسدود می‌شود (دوباره خودکار داده نمی‌شود) و امتیازش رد می‌شود."""
    b = app.conn.execute("SELECT * FROM badges WHERE id=? AND status='pending'", (bid,)).fetchone()
    if b:
        badge_delete(app, ctx, bid, True, quiet=True)
    pending_view(app, ctx, 0)


def approve_all(app, ctx):
    n = 0
    for b in app.conn.execute("SELECT id FROM badges WHERE status='pending' ORDER BY id").fetchall():
        n += 1 if approve_badge(app, ctx, b["id"], quiet=True) else 0
    for r in app.conn.execute("SELECT id FROM points_ledger WHERE status='pending' AND kind<>'badge' ORDER BY id").fetchall():
        n += 1 if _decide(app, ctx, r["id"], "approved") else 0
    app.show(ctx, f"✅ {fa(n)} مورد تأیید شد.", BACK)


# ---------- امتیاز یک نفر ----------
NO_GAMIFY = "برای این پایه نشان و امتیاز فعال نیست (فقط پایه‌ی ششم)."


def student_points(app: App, ctx: Ctx, sid: int):
    s = app.student(sid)
    if not R.gamified(app.conn, sid):
        app.show(ctx, NO_GAMIFY, [[btn("⬅ دانش‌آموز", f"a:st:{sid}")]])
        return
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
    if not R.gamified(app.conn, sid):
        app.show(ctx, NO_GAMIFY, [[btn("⬅ دانش‌آموز", f"a:st:{sid}")]])
        return
    bs = app.conn.execute("SELECT * FROM badges WHERE student_id=? ORDER BY awarded_ts", (sid,)).fetchall()
    rows = []
    for b in bs:
        rows.append([btn(f"{'⏳' if b['status'] == 'pending' else '✏'} {b['title']}"[:34], f"a:sbde:{b['id']}"), btn("🗑", f"a:sbdd:{b['id']}")])
    rows.append([btn("➕ نشان دستی جدید", f"a:bds:{sid}")])
    rows.append([btn("⬅ دانش‌آموز", f"a:st:{sid}")])
    app.show(ctx, f"🏅 نشان‌های {s['full_name']} ({fa(len(bs))} نشان)\n✏ ویرایش عنوان | 🗑 حذف | ⏳ در انتظار تأیید" +
             ("" if bs else "\n\nنشانی ندارد."), rows)


def badge_delete(app: App, ctx: Ctx, bid: int, confirm: bool, quiet: bool = False):
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
    if not quiet:
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
