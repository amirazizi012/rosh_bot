"""قواعد اصلی: مهلت، تاخیر، تاخیر مجاز، عذر موجه، ارسال مجدد، شمارنده‌ی پشت‌سرهم و نشان‌ها.

همه‌ی منطق حساس اینجاست تا جدا از بات قابل آزمایش باشد.
"""
from __future__ import annotations

from math import ceil

from .fa import fa, duration

KIND_LABEL = {"required": "الزامی", "optional": "اختیاری", "bonus": "امتیازی"}
KIND_ICON = {"required": "📘", "optional": "🧩", "bonus": "⭐"}

# کد وضعیت -> (آیکون، برچسب)
STATUS_LABEL = {
    "on_time": ("✅", "به‌موقع"),
    "late": ("⏰", "با تاخیر"),
    "excused": ("🙏", "عذر موجه"),
    "waiting": ("⏳", "در انتظار ارسال"),
    "overdue": ("⚠️", "ارسال‌نشده (هنوز می‌تواند با تاخیر بفرستد)"),
    "missed": ("❌", "ارسال‌نشده (مهلت بسته شد)"),
}


# ---------- هدف‌گیری تکالیف ----------
def is_target(conn, a, sid) -> bool:
    if a["target_all"]:
        return True
    return conn.execute(
        "SELECT 1 FROM assignment_groups ag JOIN student_groups sg ON sg.group_id=ag.group_id "
        "WHERE ag.assignment_id=? AND sg.student_id=? LIMIT 1", (a["id"], sid)).fetchone() is not None


def _closed_before_join(a, student) -> bool:
    # تکلیفی که پیش از عضویت دانش‌آموز کاملاً بسته شده، به حساب او نمی‌آید
    return a["deadline_ts"] + a["late_hours"] * 3600 < student["created_ts"]


def targets_for_student(conn, sid, kinds=None):
    st = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    out = []
    if st is None or st["grade"] != 6:
        return out  # تکالیف فقط برای پایه‌ی ششم است
    rows = conn.execute("SELECT * FROM assignments WHERE status='active' ORDER BY deadline_ts, id").fetchall()
    for a in rows:
        if kinds and a["kind"] not in kinds:
            continue
        if _closed_before_join(a, st):
            continue
        if is_target(conn, a, sid):
            out.append(a)
    return out


def target_students(conn, a):
    studs = conn.execute("SELECT * FROM students WHERE active=1 ORDER BY full_name").fetchall()
    return [s for s in studs if s["grade"] == 6 and not _closed_before_join(a, s) and is_target(conn, a, s["id"])]


# ---------- مهلت و تاخیر ----------
def effective_deadline(conn, a, sid) -> int:
    r = conn.execute("SELECT deadline_ts FROM student_deadlines WHERE assignment_id=? AND student_id=?",
                     (a["id"], sid)).fetchone()
    return max(r["deadline_ts"], a["deadline_ts"]) if r else a["deadline_ts"]


def verdict(a, deadline_ts: int, now: int):
    """(on_time | late | closed , دقیقه‌ی گذشته از مهلت)"""
    over = max(0, ceil((now - deadline_ts) / 60))
    if now <= deadline_ts + a["grace_min"] * 60:
        return "on_time", over
    if now <= deadline_ts + a["late_hours"] * 3600:
        return "late", over
    return "closed", over


def current_final(conn, aid, sid):
    return conn.execute("SELECT * FROM submissions WHERE assignment_id=? AND student_id=? AND state='final' "
                        "ORDER BY id DESC LIMIT 1", (aid, sid)).fetchone()


def open_resubmit(conn, aid, sid):
    return conn.execute("SELECT * FROM resubmit_requests WHERE assignment_id=? AND student_id=? AND open=1",
                        (aid, sid)).fetchone()


def is_excused(conn, aid, sid) -> bool:
    return conn.execute("SELECT 1 FROM excuses WHERE assignment_id=? AND student_id=?", (aid, sid)).fetchone() is not None


def student_status(conn, a, sid, now) -> dict:
    sub = current_final(conn, a["id"], sid)
    if sub:
        return {"code": "on_time" if sub["on_time"] else "late", "over": sub["over_minutes"] or 0, "sub": sub}
    if is_excused(conn, a["id"], sid):
        return {"code": "excused", "over": 0, "sub": None}
    dl = effective_deadline(conn, a, sid)
    v, over = verdict(a, dl, now)
    code = {"on_time": "waiting", "late": "overdue", "closed": "missed"}[v]
    return {"code": code, "over": 0 if v == "on_time" else over, "sub": None}


def can_submit(conn, a, sid, now):
    if a["status"] != "active":
        return False, "این تکلیف لغو شده است."
    dl = effective_deadline(conn, a, sid)
    v, _ = verdict(a, dl, now)
    sub = current_final(conn, a["id"], sid)
    req = open_resubmit(conn, a["id"], sid)
    if sub and not req:
        if now <= dl:
            return True, ""  # پیش از مهلت می‌تواند پاسخ را عوض کند
        return False, "پاسخ این تکلیف را قبلاً فرستاده‌ای. برای ارسال مجدد باید مدیر اجازه بدهد."
    if not sub and v == "closed" and not req:
        return False, "مهلت ارسال این تکلیف بسته شده است. اگر دلیل موجهی داری با مدیر صحبت کن."
    return True, ""


def finalize(conn, a, sid, draft_id: int, now: int):
    """پیش‌نویس را نهایی می‌کند. خروجی: (on_time, over_minutes, was_resubmit_request)"""
    dl = effective_deadline(conn, a, sid)
    v, over = verdict(a, dl, now)
    prev = current_final(conn, a["id"], sid)
    req = open_resubmit(conn, a["id"], sid)
    if v == "closed" and not req:
        raise ValueError("closed")
    if req and prev:
        # ارسال مجدد به درخواست مدیر، وضعیت زمانی ارسال اول را تغییر نمی‌دهد
        on_time, over_m = prev["on_time"], prev["over_minutes"]
    else:
        on_time, over_m = (1 if v == "on_time" else 0), over
    if prev:
        conn.execute("UPDATE submissions SET state='superseded' WHERE id=?", (prev["id"],))
    conn.execute("UPDATE submissions SET state='final', submitted_ts=?, on_time=?, over_minutes=?, resubmit_of=? "
                 "WHERE id=?", (now, on_time, over_m, prev["id"] if prev else None, draft_id))
    if req:
        conn.execute("UPDATE resubmit_requests SET open=0 WHERE assignment_id=? AND student_id=?", (a["id"], sid))
    conn.commit()
    return bool(on_time), over_m, bool(req)


# ---------- شمارنده‌ی پشت‌سرهم ----------
def streak_state(conn, sid, now, n):
    """(تعداد نشان‌های کامل، شمارنده‌ی فعلی).
    فقط تکالیف «الزامی». به‌موقع +۱ ؛ تاخیر/ارسال‌نشده → صفر ؛ عذر موجه → نادیده ؛
    تکلیفی که هنوز تکلیفش روشن نیست (منتظر ارسال) شمارش را همان‌جا نگه می‌دارد."""
    counter = blocks = 0
    for a in targets_for_student(conn, sid, ("required",)):
        code = student_status(conn, a, sid, now)["code"]
        if code == "excused":
            continue
        if code == "on_time":
            counter += 1
            if counter >= n:
                blocks += 1
                counter = 0
        elif code == "waiting":
            break
        else:  # late / overdue / missed
            counter = 0
    return blocks, counter


def extra_streak_state(conn, sid, now, n):
    """مثل شمارنده‌ی تکالیف الزامی، ولی برای تکالیف «اختیاری و امتیازی» (n ارسال پشت‌سرهم و به‌موقع)."""
    counter = blocks = 0
    for a in targets_for_student(conn, sid, ("optional", "bonus")):
        code = student_status(conn, a, sid, now)["code"]
        if code == "excused":
            continue
        if code == "on_time":
            counter += 1
            if counter >= n:
                blocks += 1
                counter = 0
        elif code == "waiting":
            break
        else:
            counter = 0
    return blocks, counter


def add_points(conn, sid, delta, reason, kind, source_code, source_key, now, status="pending", admin_id=None) -> bool:
    """یک ردیف در دفتر امتیاز. ردیف‌های خودکار (source_code دارند) یک‌بار ثبت می‌شوند."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO points_ledger(student_id,delta,reason,kind,source_code,source_key,status,created_ts,decided_ts,admin_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (sid, delta, reason, kind, source_code, None if source_key is None else str(source_key), status, now,
         now if status == "approved" else None, admin_id if status == "approved" else None))
    conn.commit()
    return cur.rowcount == 1


def points_total(conn, sid):
    """(جمع تأییدشده، جمع در انتظار تأیید)"""
    r = conn.execute("SELECT COALESCE(SUM(CASE WHEN status='approved' THEN delta END),0) a, "
                     "COALESCE(SUM(CASE WHEN status='pending' THEN delta END),0) p FROM points_ledger WHERE student_id=?", (sid,)).fetchone()
    return r["a"], r["p"]


def student_stats(conn, sid, now, n) -> dict:
    s = {"on_time": 0, "late": 0, "missed": 0, "excused": 0, "waiting": 0, "extra_done": 0}
    for a in targets_for_student(conn, sid):
        code = student_status(conn, a, sid, now)["code"]
        if a["kind"] != "required":
            if code in ("on_time", "late"):
                s["extra_done"] += 1
            continue
        s[{"overdue": "missed"}.get(code, code)] += 1
    s["blocks"], s["current"] = streak_state(conn, sid, now, n)
    s["badges"] = conn.execute("SELECT COUNT(*) c FROM badges WHERE student_id=?", (sid,)).fetchone()["c"]
    s["points"], s["points_pending"] = points_total(conn, sid)
    return s


# ---------- نشان‌ها ----------
def give_badge(conn, sid, code, key, title, now) -> bool:
    if conn.execute("SELECT 1 FROM badge_blocks WHERE student_id=? AND code=? AND key=?", (sid, code, str(key))).fetchone():
        return False  # مدیر این نشان را حذف کرده؛ خودکار دوباره داده نمی‌شود
    cur = conn.execute("INSERT OR IGNORE INTO badges(student_id,code,key,title,awarded_ts) VALUES(?,?,?,?,?)",
                       (sid, code, str(key), title, now))
    conn.commit()
    return cur.rowcount == 1


def award_auto(conn, sid, now, n, xn=5, xp=10) -> list:
    """نشان‌های خودکار را بررسی و تازه‌ها را برمی‌گرداند (تکراری ثبت نمی‌شود)."""
    new = []
    blocks, _ = streak_state(conn, sid, now, n)
    for i in range(1, blocks + 1):
        t = f"🏅 نشان پشتکار {fa(i)} — {fa(n)} تکلیف الزامی پشت‌سرهم و به‌موقع"
        if give_badge(conn, sid, "streak", i, t, now):
            new.append(t)
    xblocks, _ = extra_streak_state(conn, sid, now, xn)
    for i in range(1, xblocks + 1):
        t = f"🌟 نشان کوشا {fa(i)} — {fa(xn)} تکلیف اختیاری/امتیازی پشت‌سرهم و به‌موقع"
        if give_badge(conn, sid, "xstreak", i, t, now):
            new.append(t)
            add_points(conn, sid, xp, t, "badge", "xstreak", i, now, "pending")  # بعد از تأیید مدیر حساب می‌شود
    subs = conn.execute(
        "SELECT s.*, a.kind, a.title, a.deadline_ts, a.points FROM submissions s JOIN assignments a ON a.id=s.assignment_id "
        "WHERE s.student_id=? AND s.state='final' AND a.status='active'", (sid,)).fetchall()
    if subs and give_badge(conn, sid, "first", 1, "🌱 اولین قدم — اولین تکلیف ارسال شد", now):
        new.append("🌱 اولین قدم — اولین تکلیف ارسال شد")
    early = sum(1 for s in subs if s["on_time"] and s["submitted_ts"] <= s["deadline_ts"] - 12 * 3600)
    for i in range(1, early // 3 + 1):
        t = f"⏰ پیشگام {fa(i)} — {fa(3)} تکلیف، دست‌کم ۱۲ ساعت زودتر از مهلت"
        if give_badge(conn, sid, "early", i, t, now):
            new.append(t)
    for s in subs:
        if s["kind"] == "bonus":
            t = f"⭐ ستاره‌ی امتیازی — {s['title']}"
            if give_badge(conn, sid, "bonus", s["assignment_id"], t, now):
                new.append(t)
            if s["points"] and s["points"] > 0:
                add_points(conn, sid, s["points"], f"تکلیف امتیازی «{s['title']}»", "bonus", "asg", s["assignment_id"], now, "pending")
        elif s["kind"] == "optional" and s["on_time"]:
            t = f"🧩 کنجکاو — {s['title']}"
            if give_badge(conn, sid, "optional", s["assignment_id"], t, now):
                new.append(t)
    return new


def describe_for_student(s: dict, closes_ts_text: str = "") -> str:
    code = s["code"]
    if code == "on_time":
        return "✅ به‌موقع ارسال کرده‌ای"
    if code == "late":
        return f"⏰ با {duration(s['over'])} تاخیر ارسال شده"
    if code == "excused":
        return "🙏 برای این تکلیف عذر موجه ثبت شده"
    if code == "overdue":
        return f"⚠️ مهلت گذشته؛ هنوز می‌توانی با تاخیر بفرستی{closes_ts_text}"
    if code == "missed":
        return "⛔ مهلت ارسال بسته شده"
    return "⏳ هنوز ارسال نکرده‌ای"
