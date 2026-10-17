"""بررسی پاسخ‌ها توسط مدیر: ویرایش وضعیت هر تکلیف برای هر دانش‌آموز.

وضعیت‌هایی که مدیر می‌تواند ثبت کند:
  ✅ ارسال‌شده (به‌موقع) | ⏰ با تاخیر | ⚠️ ناقص | ❌ ارسال‌نشده | ↩ برگرداندن به حالت خودکار
اثر روی شمارنده: فقط «ارسال‌شده (به‌موقع)» در ۶ تکلیف پشت‌سرهم حساب می‌شود؛ بقیه شمارنده را قطع می‌کنند.
نشان پشتکار/کوشا «در انتظار تأیید مدیر» می‌ماند و اگر بعد از ویرایش شرطش از بین برود پس گرفته می‌شود.
«ناقص» به دانش‌آموز اجازه‌ی ارسال مجدد می‌دهد (وضعیت زمانی ارسال اول حفظ می‌شود).
"""
from __future__ import annotations

from . import jalali as J
from . import reports
from . import rules as R
from .bale import btn
from .core import App, Ctx
from .fa import clean, duration, fa

CODES = {"ok": "on_time", "late": "late", "inc": "incomplete", "miss": "missed"}
LABEL = {"on_time": "✅ ارسال‌شده (به‌موقع)", "late": "⏰ با تاخیر", "incomplete": "⚠️ ناقص", "missed": "❌ ارسال‌نشده"}
ICON = {"on_time": "✅", "late": "⏰", "incomplete": "⚠️", "missed": "❌", "excused": "🙏", "waiting": "⏳", "overdue": "⌛"}


def _tell(app: App, sid, text, rows=None):
    s = app.student(sid)
    if s and s["chat_id"]:
        app.send(s["chat_id"], text, rows)


def _status_text(st: dict) -> str:
    code = st["code"]
    base = {"on_time": "✅ ارسال‌شده (به‌موقع)", "late": f"⏰ با تاخیر ({duration(st['over'])})" if st["over"] else "⏰ با تاخیر",
            "incomplete": "⚠️ ناقص", "missed": "❌ ارسال‌نشده", "excused": "🙏 عذر موجه",
            "waiting": "⏳ در انتظار ارسال", "overdue": "⌛ مهلت گذشته (هنوز باز)"}[code]
    return base + (" ✎ (ویرایش مدیر)" if st.get("override") else "")


# ---------- لیست‌ها ----------
def student_list(app: App, ctx: Ctx, sid: int):
    s = app.student(sid)
    now = app.now()
    rows, lines = [], [f"📋 بررسی تکالیف {s['full_name']}", "برای تغییر وضعیت هر تکلیف آن را بزن:", ""]
    for a in reversed(R.targets_for_student(app.conn, sid)):
        st = R.student_status(app.conn, a, sid, now)
        label = f"{ICON[st['code']]}{'✎' if st.get('override') else ''} {R.KIND_ICON[a['kind']]} {a['title']}"
        rows.append([btn(label[:56], f"a:rv:{a['id']}:{sid}")])
    if not rows:
        app.show(ctx, "تکلیفی برای این دانش‌آموز نیست.", [[btn("⬅ دانش‌آموز", f"a:st:{sid}")]])
        return
    app.show(ctx, "\n".join(lines[:2]) + "\n✎ = وضعیت ویرایش‌شده توسط مدیر", rows[:30] + [[btn("⬅ دانش‌آموز", f"a:st:{sid}")]])


def pick_student(app: App, ctx: Ctx, aid: int):
    a = app.assignment(aid)
    rows, row = [], []
    for s in R.target_students(app.conn, a):
        st = R.student_status(app.conn, a, s["id"], app.now())
        row.append(btn(f"{ICON[st['code']]} {s['full_name']}"[:28], f"a:rv:{aid}:{s['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    app.show(ctx, f"✏ وضعیت «{a['title']}» برای چه کسی تغییر کند؟", rows + [[btn("⬅ بازگشت", f"a:as:{aid}")]])


# ---------- صفحه‌ی ویرایش ----------
def view(app: App, ctx: Ctx, aid: int, sid: int):
    a, s = app.assignment(aid), app.student(sid)
    now = app.now()
    eff = R.student_status(app.conn, a, sid, now)
    auto = R.student_status(app.conn, a, sid, now, use_override=False)
    sub = eff["sub"]
    lines = [f"✏ {s['full_name']} — {a['title']}", "",
             f"وضعیت فعلی: {_status_text(eff)}",
             f"وضعیت خودکار: {_status_text(auto)}"]
    if sub:
        lines.append(f"زمان ارسال: {J.fmt_short(sub['submitted_ts'])}")
    ov = eff.get("override")
    if ov:
        lines.append(f"ویرایش مدیر: {J.fmt_short(ov['ts'])}" + (f" — توضیح: {ov['note']}" if ov["note"] else ""))
    rows = [[btn(LABEL["on_time"], f"a:rvs:{aid}:{sid}:ok"), btn(LABEL["late"], f"a:rvs:{aid}:{sid}:late")],
            [btn(LABEL["incomplete"], f"a:rvs:{aid}:{sid}:inc"), btn(LABEL["missed"], f"a:rvs:{aid}:{sid}:miss")]]
    if ov:
        rows.append([btn("↩ برگرداندن به حالت خودکار", f"a:rvs:{aid}:{sid}:clr")])
    if sub:
        rows.append([btn("👁 دیدن فایل‌ها", f"a:asub:{aid}:{sid}")])
    rows.append([btn("⬅ فهرست تکالیف او", f"a:rvl:{sid}"), btn("⬅ تکلیف", f"a:as:{aid}")])
    app.show(ctx, "\n".join(lines), rows)


# ---------- اعمال تغییر ----------
def apply(app: App, ctx: Ctx, aid: int, sid: int, status, note: str = ""):
    """status: یکی از on_time/late/incomplete/missed یا None (برگشت به خودکار)."""
    a, s = app.assignment(aid), app.student(sid)
    conn, now = app.conn, app.now()
    prev = R.get_override(conn, aid, sid)
    had_sub = R.current_final(conn, aid, sid) is not None
    if status is None:
        conn.execute("DELETE FROM status_overrides WHERE assignment_id=? AND student_id=?", (aid, sid))
    else:
        conn.execute("INSERT OR REPLACE INTO status_overrides(assignment_id,student_id,status,note,admin_id,ts) VALUES(?,?,?,?,?,?)",
                     (aid, sid, status, note or None, ctx.user_id, now))
    # «ناقص»: دانش‌آموز می‌تواند دوباره بفرستد؛ برعکسش: اگر از ناقص برگشت، اجازه‌ی ارسال مجدد خودکار بسته می‌شود
    if status == "incomplete" and had_sub:
        conn.execute("INSERT OR REPLACE INTO resubmit_requests(assignment_id,student_id,note,ts,open) VALUES(?,?,?,?,1)",
                     (aid, sid, note or "پاسخ ناقص بود", now))
    elif prev and prev["status"] == "incomplete" and status != "incomplete":
        conn.execute("UPDATE resubmit_requests SET open=0 WHERE assignment_id=? AND student_id=?", (aid, sid))
    # امتیاز تکلیف امتیازی با وضعیت هماهنگ می‌شود
    if a["kind"] == "bonus":
        _sync_bonus_points(conn, a, sid, status, now)
    conn.commit()
    app.audit(ctx.user_id, "status_override", f"{aid}:{sid}:{status or 'auto'}")
    _notify_student(app, a, sid, status, note)
    new = app.award(sid)          # نشان‌ها و شمارنده با وضعیت تازه بازمحاسبه می‌شود (نشان‌های در انتظارِ نامعتبر پس گرفته می‌شود)
    return new


def _sync_bonus_points(conn, a, sid, status, now):
    from .rules import add_points
    where = "student_id=? AND kind='bonus' AND source_code='asg' AND source_key=?"
    if status in ("incomplete", "missed"):
        conn.execute(f"UPDATE points_ledger SET status='rejected', decided_ts=? WHERE {where} AND status='pending'", (now, sid, str(a["id"])))
    elif status in ("on_time", "late") and a["points"] and a["points"] > 0:
        row = conn.execute(f"SELECT id,status FROM points_ledger WHERE {where}", (sid, str(a["id"]))).fetchone()
        if row and row["status"] == "rejected":
            conn.execute("UPDATE points_ledger SET status='pending', decided_ts=NULL WHERE id=?", (row["id"],))
        elif not row:
            add_points(conn, sid, a["points"], f"تکلیف امتیازی «{a['title']}»", "bonus", "asg", a["id"], now, "pending")


def _notify_student(app: App, a, sid, status, note):
    open_btn = [[btn("📖 باز کردن تکلیف", f"s:a:{a['id']}")]]
    if status is None:
        _tell(app, sid, f"↩ وضعیت تکلیف «{a['title']}» به حالت خودکار برگشت.", open_btn)
    elif status == "incomplete":
        _tell(app, sid, f"⚠️ مدیر پاسخ تکلیف «{a['title']}» را «ناقص» ثبت کرد." + (f"\nتوضیح: {note}" if note else "") +
              "\nمی‌توانی پاسخ کامل‌تر را دوباره بفرستی (وضعیت زمانی ارسال اولت حفظ می‌شود).", open_btn)
    else:
        txt = {"on_time": "«ارسال‌شده (به‌موقع)»", "late": "«با تاخیر»", "missed": "«ارسال‌نشده»"}[status]
        _tell(app, sid, f"{ICON[status]} مدیر وضعیت تکلیف «{a['title']}» را {txt} ثبت کرد." + (f"\nتوضیح: {note}" if note else ""), open_btn)


def st_note(app, ctx, msg, text, data):
    note = "" if (msg.get("text") or "").strip() in ("-", "—") else clean(msg.get("text") or "")
    app.clear_state(ctx.chat_id)
    apply(app, ctx, data["aid"], data["sid"], "incomplete", note)
    view(app, ctx, data["aid"], data["sid"])


def callback(app: App, ctx: Ctx, c: str, arg):
    i = lambda k: int(arg[k])  # noqa: E731
    if c == "rvl":
        student_list(app, ctx, i(0))
    elif c == "arv":
        pick_student(app, ctx, i(0))
    elif c == "rv":
        view(app, ctx, i(0), i(1))
    elif c == "rvs":
        aid, sid, code = i(0), i(1), arg[2]
        if code == "inc":
            app.set_state(ctx.chat_id, "a:rvn", {"aid": aid, "sid": sid})
            app.send(ctx.chat_id, "توضیح برای دانش‌آموز بنویس (مثلاً «حل مسئله‌ی ۳ ناقص است»)؛ یا «-» برای بدون توضیح:")
            return
        apply(app, ctx, aid, sid, None if code == "clr" else CODES[code])
        view(app, ctx, aid, sid)
