"""عمل‌های نوشتنی مدیر برای پنل وب (مرحله‌ی ۱: دانش‌آموزان/گروه‌ها، بررسی پاسخ، نشان و امتیاز).

هر تابع `(ok, پیام)` برمی‌گرداند و HTML یا دکمه‌ی بله نمی‌سازد؛ منطق از همان توابع بات (`review`, `points`, `rules`) می‌آید
تا رفتار یکی بماند. هر عمل در `audit` ثبت می‌شود (برچسب «از پنل» را `PanelApp.audit` اضافه می‌کند).
"""
from __future__ import annotations

import re

from . import admin, points, review, usernames
from . import rules as R
from .core import App, Ctx
from .fa import clean, en, fa

GRADES = (6, 7, 9)
STATUSES = {"ok": "on_time", "late": "late", "inc": "incomplete", "miss": "missed", "auto": None}


class PanelApp(App):
    """همان App بات؛ فقط ثبت رویداد را با «(از پنل)» نشانه‌گذاری می‌کند."""

    def audit(self, admin_id, action, details=""):
        super().audit(admin_id, action, f"{details} (از پنل)".strip())


def _ctx(admin_id: int) -> Ctx:
    return Ctx(chat_id=0, user_id=admin_id)


# ---------- دانش‌آموزان ----------
def add_students(app: App, admin_id: int, text: str, grade: int):
    if grade not in GRADES:
        return False, "پایه نامعتبر است."
    lines = [clean(l) for l in (text or "").split("\n") if clean(l)][:60]
    if not lines:
        return False, "حداقل یک نام بنویس."
    done, notes = 0, []
    for line in lines:
        name, uname, grp = admin.parse_student_line(line)
        if not name:
            continue
        if uname and app.conn.execute("SELECT 1 FROM students WHERE username=?", (uname,)).fetchone():
            notes.append(f"{name}: یوزرنیم تکراری بود و ثبت نشد")
            uname = None
        cur = app.conn.execute("INSERT INTO students(full_name,code,created_ts,grade,username) VALUES(?,?,?,?,?)",
                               (name, admin.new_code(app), app.now(), grade, uname))
        if grp:
            app.conn.execute("INSERT OR IGNORE INTO groups(name) VALUES(?)", (grp,))
            gid = app.conn.execute("SELECT id FROM groups WHERE name=?", (grp,)).fetchone()["id"]
            app.conn.execute("INSERT OR IGNORE INTO student_groups VALUES(?,?)", (cur.lastrowid, gid))
        done += 1
    app.conn.commit()
    if not done:
        return False, "نام معتبری پیدا نشد."
    app.audit(admin_id, "students_add", str(done))
    return True, f"{fa(done)} دانش‌آموز اضافه شد." + ("" if not notes else " ⚠ " + "؛ ".join(notes))


def _student(app, sid):
    return app.student(sid)


def rename_student(app: App, admin_id: int, sid: int, name: str):
    name = clean(name)
    if not _student(app, sid) or not (2 <= len(name) <= 60):
        return False, "نام باید ۲ تا ۶۰ حرف باشد."
    app.conn.execute("UPDATE students SET full_name=? WHERE id=?", (name, sid))
    app.conn.commit()
    app.audit(admin_id, "student_rename", f"{sid}")
    return True, "نام تغییر کرد."


def set_username(app: App, admin_id: int, sid: int, raw: str):
    if not _student(app, sid):
        return False, "دانش‌آموز پیدا نشد."
    if clean(raw) in ("", "-", "—"):
        app.conn.execute("UPDATE students SET username=NULL WHERE id=?", (sid,))
        app.conn.commit()
        app.audit(admin_id, "username_clear", str(sid))
        return True, "یوزرنیم پاک شد."
    u = usernames.normalize(raw)
    if not u:
        return False, "یوزرنیم معتبر نیست (۳ تا ۳۲ حرف انگلیسی، عدد یا _)."
    other = app.conn.execute("SELECT full_name FROM students WHERE username=? AND id<>?", (u, sid)).fetchone()
    if other:
        return False, f"این یوزرنیم برای «{other['full_name']}» ثبت شده است."
    app.conn.execute("UPDATE students SET username=? WHERE id=?", (u, sid))
    app.conn.commit()
    app.audit(admin_id, "username_set", f"{sid}:{u}")
    return True, f"یوزرنیم ثبت شد: @{u}"


def toggle_active(app: App, admin_id: int, sid: int):
    if not _student(app, sid):
        return False, "دانش‌آموز پیدا نشد."
    app.conn.execute("UPDATE students SET active=1-active WHERE id=?", (sid,))
    app.conn.commit()
    app.audit(admin_id, "student_toggle", str(sid))
    return True, "وضعیت فعال/غیرفعال تغییر کرد."


def reset_login(app: App, admin_id: int, sid: int):
    if not _student(app, sid):
        return False, "دانش‌آموز پیدا نشد."
    app.conn.execute("UPDATE students SET code=?, chat_id=NULL, joined_ts=NULL WHERE id=?", (admin.new_code(app), sid))
    app.conn.commit()
    app.audit(admin_id, "student_reset", str(sid))
    return True, "ورود بازنشانی شد؛ دانش‌آموز دوباره /start بزند."


def set_student_groups(app: App, admin_id: int, sid: int, group_ids):
    if not _student(app, sid):
        return False, "دانش‌آموز پیدا نشد."
    valid = {r["id"] for r in app.conn.execute("SELECT id FROM groups")}
    want = {g for g in group_ids if g in valid}
    app.conn.execute("DELETE FROM student_groups WHERE student_id=?", (sid,))
    for g in sorted(want):
        app.conn.execute("INSERT INTO student_groups VALUES(?,?)", (sid, g))
    app.conn.commit()
    app.audit(admin_id, "student_groups_set", f"{sid}:{','.join(map(str, sorted(want)))}")
    return True, "گروه‌های دانش‌آموز ذخیره شد."


# ---------- گروه‌ها ----------
def create_group(app: App, admin_id: int, name: str):
    name = clean(name)
    if not (1 <= len(name) <= 40):
        return False, "نام گروه باید ۱ تا ۴۰ حرف باشد."
    if app.conn.execute("SELECT 1 FROM groups WHERE name=?", (name,)).fetchone():
        return False, "گروهی با این نام هست."
    app.conn.execute("INSERT INTO groups(name) VALUES(?)", (name,))
    app.conn.commit()
    app.audit(admin_id, "group_create", name)
    return True, f"گروه «{name}» ساخته شد."


def delete_group(app: App, admin_id: int, gid: int, confirmed: bool):
    g = app.conn.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
    if not g:
        return False, "گروه پیدا نشد."
    if not confirmed:
        return False, "برای حذف باید تیک تأیید را بزنی."
    app.conn.execute("DELETE FROM student_groups WHERE group_id=?", (gid,))
    app.conn.execute("DELETE FROM groups WHERE id=?", (gid,))
    app.conn.commit()
    app.audit(admin_id, "group_delete", g["name"])
    return True, f"گروه «{g['name']}» حذف شد."


def set_group_members(app: App, admin_id: int, gid: int, student_ids):
    if not app.conn.execute("SELECT 1 FROM groups WHERE id=?", (gid,)).fetchone():
        return False, "گروه پیدا نشد."
    valid = {r["id"] for r in app.conn.execute("SELECT id FROM students")}
    want = {s for s in student_ids if s in valid}
    app.conn.execute("DELETE FROM student_groups WHERE group_id=?", (gid,))
    for s in sorted(want):
        app.conn.execute("INSERT INTO student_groups VALUES(?,?)", (s, gid))
    app.conn.commit()
    app.audit(admin_id, "group_members_set", f"{gid}:{len(want)}")
    return True, f"اعضای گروه ذخیره شد ({fa(len(want))} نفر)."


# ---------- بررسی پاسخ ----------
def set_status(app: App, admin_id: int, aid: int, sid: int, code: str, note: str = ""):
    """code: ok | late | inc | miss | auto (برگشت به وضعیت خودکار)."""
    if code not in STATUSES:
        return False, "وضعیت نامعتبر است."
    a, s = app.assignment(aid), app.student(sid)
    if not a or not s:
        return False, "تکلیف یا دانش‌آموز پیدا نشد."
    if not R.is_target(app.conn, a, sid, s["grade"]):
        return False, "این تکلیف برای این دانش‌آموز نیست."
    review.apply(app, _ctx(admin_id), aid, sid, STATUSES[code], clean(note)[:200])
    return True, "وضعیت ثبت شد و دانش‌آموز خبردار شد."


# ---------- امتیاز و نشان ----------
def approve_item(app: App, admin_id: int, kind: str, item_id: int):
    """kind: points | badge"""
    ctx = _ctx(admin_id)
    ok = points.approve_badge(app, ctx, item_id, quiet=True) if kind == "badge" else points._decide(app, ctx, item_id, "approved")
    return (True, "تأیید شد.") if ok else (False, "مورد پیدا نشد (شاید قبلاً بررسی شده).")


def reject_item(app: App, admin_id: int, kind: str, item_id: int):
    ctx = _ctx(admin_id)
    if kind == "badge":
        if not app.conn.execute("SELECT 1 FROM badges WHERE id=? AND status='pending'", (item_id,)).fetchone():
            return False, "مورد پیدا نشد (شاید قبلاً بررسی شده)."
        points.badge_delete(app, ctx, item_id, True, quiet=True)
        return True, "رد شد و نشان حذف/مسدود شد."
    ok = points._decide(app, ctx, item_id, "rejected")
    return (True, "رد شد.") if ok else (False, "مورد پیدا نشد (شاید قبلاً بررسی شده).")


def approve_all(app: App, admin_id: int):
    ctx, n = _ctx(admin_id), 0
    for b in app.conn.execute("SELECT id FROM badges WHERE status='pending' ORDER BY id").fetchall():
        n += 1 if points.approve_badge(app, ctx, b["id"], quiet=True) else 0
    for r in app.conn.execute("SELECT id FROM points_ledger WHERE status='pending' AND kind<>'badge' ORDER BY id").fetchall():
        n += 1 if points._decide(app, ctx, r["id"], "approved") else 0
    return True, f"{fa(n)} مورد تأیید شد."


def adjust_points(app: App, admin_id: int, sid: int, delta_text: str, reason: str):
    if not R.gamified(app.conn, sid):
        return False, points.NO_GAMIFY
    m = re.fullmatch(r"([+\-−]?\d{1,4})", en(clean(delta_text)).replace("−", "-"))
    if not m or int(m.group(1)) == 0:
        return False, "امتیاز باید عددی غیرصفر باشد؛ مثلاً 5 یا -3."
    delta, reason = int(m.group(1)), clean(reason)[:100] or "تغییر دستی مدیر"
    R.add_points(app.conn, sid, delta, reason, "manual", None, None, app.now(), "approved", admin_id)
    app.audit(admin_id, "points_manual", f"{sid}:{delta}:{reason}")
    tot, _ = R.points_total(app.conn, sid)
    sign = "+" if delta > 0 else ""
    points.tell(app, sid, f"⭐ مدیر امتیاز تو را تغییر داد: {sign}{fa(delta)} ({reason})\nمجموع امتیاز تو: {fa(tot)}")
    return True, f"ثبت شد. مجموع امتیاز: {fa(tot)}"


def delete_badge(app: App, admin_id: int, bid: int):
    b = app.conn.execute("SELECT * FROM badges WHERE id=?", (bid,)).fetchone()
    if not b:
        return False, "نشان پیدا نشد."
    points.badge_delete(app, _ctx(admin_id), bid, True, quiet=True)
    return True, "نشان حذف شد."


# =====================================================================
# مرحله‌ی ۲ تا ۴: تکلیف، پیام و بازخورد، باشگاه کتابخوانی، مدیران
# =====================================================================
import shutil
import time
from pathlib import Path

from . import books
from . import jalali as J

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
FILE_EXT = IMG_EXT | {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".zip", ".mp3", ".mp4"}
MAX_FILES = 10
KINDS = ("required", "optional", "bonus")


def _tell(app, sid, text, rows=None):
    return admin.tell(app, sid, text, rows)


def _save_files(app, aid: int, files):
    """فایل‌های آپلودشده را کنار تکلیف ذخیره می‌کند؛ (تعداد ذخیره‌شده، توضیح‌های رد شده)."""
    folder = app.data / "assignments" / str(aid)
    folder.mkdir(parents=True, exist_ok=True)
    saved, skipped = 0, []
    cap = app.cfg.max_file_mb * 1024 * 1024
    for name, data in files[:MAX_FILES]:
        ext = Path(name).suffix.lower()
        if ext not in FILE_EXT or not data:
            skipped.append(f"{name} (نوع فایل مجاز نیست)")
            continue
        if len(data) > cap:
            skipped.append(f"{name} (بزرگ‌تر از {fa(app.cfg.max_file_mb)} مگابایت)")
            continue
        dest = folder / f"p{int(time.time())}_{saved + 1}{ext}"
        dest.write_bytes(data)
        app.conn.execute("INSERT INTO assignment_files(assignment_id,path,kind,name) VALUES(?,?,?,?)",
                         (aid, str(dest), "photo" if ext in IMG_EXT else "document", clean(Path(name).name)[:80]))
        saved += 1
    return saved, skipped


def create_assignment(app: App, admin_id: int, title, desc, kind, points_text, target, groups, deadline_text, notify, files):
    title, desc = clean(title), (desc or "").strip()
    if not (2 <= len(title) <= 120):
        return False, "عنوان باید ۲ تا ۱۲۰ حرف باشد."
    if kind not in KINDS:
        return False, "نوع تکلیف نامعتبر است."
    pts = 0
    if kind == "bonus":
        v = en(points_text or "").strip()
        if not v.isdigit() or not (1 <= int(v) <= 1000):
            return False, "برای تکلیف امتیازی، امتیاز را (۱ تا ۱۰۰۰) بنویس."
        pts = int(v)
    if target == "groups":
        gids = [g for g in groups if app.conn.execute("SELECT 1 FROM groups WHERE id=?", (g,)).fetchone()]
        if not gids:
            return False, "دست‌کم یک گروه انتخاب کن."
        target_all, tg = 0, 0
    else:
        gids = []
        tg = {"all": R.TARGET_ALL, "g6": 6, "g7": 7, "g9": 9}.get(target)
        if tg is None:
            return False, "مخاطب نامعتبر است."
        target_all = 1
    ts = J.parse(deadline_text or "", app.now())
    if ts is None:
        return False, "مهلت را نفهمیدم؛ مثل «۱۴۰۵/۰۸/۲۰ ۲۱:۳۰» یا «فردا ۲۱:۳۰» بنویس."
    if ts <= app.now():
        return False, "مهلت گذشته است؛ زمانی در آینده بنویس."
    cur = app.conn.execute(
        "INSERT INTO assignments(title,description,kind,deadline_ts,grace_min,late_hours,target_all,created_ts,points,target_grade) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (title, desc, kind, ts, app.cfg.grace_minutes, app.cfg.late_window_hours, target_all, app.now(), pts, tg))
    aid = cur.lastrowid
    for g in gids:
        app.conn.execute("INSERT OR IGNORE INTO assignment_groups VALUES(?,?)", (aid, g))
    saved, skipped = _save_files(app, aid, files or [])
    app.conn.commit()
    app.audit(admin_id, "assignment_create", f"{aid}:{title}")
    msg = f"تکلیف «{title}» ساخته شد."
    if saved:
        msg += f" {fa(saved)} فایل ضمیمه شد."
    if notify:
        msg += f" به {fa(admin.notify_assignment(app, aid))} دانش‌آموز اطلاع داده شد."
    if skipped:
        msg += " ⚠ " + "؛ ".join(skipped)
    return True, msg


def add_assignment_files(app: App, admin_id: int, aid: int, files):
    if not app.assignment(aid):
        return False, "تکلیف پیدا نشد."
    saved, skipped = _save_files(app, aid, files or [])
    app.conn.commit()
    if not saved:
        return False, "فایلی ذخیره نشد." + (" " + "؛ ".join(skipped) if skipped else "")
    app.audit(admin_id, "assignment_files", f"{aid}:{saved}")
    return True, f"{fa(saved)} فایل افزوده شد." + (" ⚠ " + "؛ ".join(skipped) if skipped else "")


def delete_assignment_file(app: App, admin_id: int, fid: int):
    r = app.conn.execute("SELECT * FROM assignment_files WHERE id=?", (fid,)).fetchone()
    if not r:
        return False, "فایل پیدا نشد."
    app.conn.execute("DELETE FROM assignment_files WHERE id=?", (fid,))
    app.conn.commit()
    Path(r["path"]).unlink(missing_ok=True)
    app.audit(admin_id, "assignment_file_delete", f"{r['assignment_id']}:{fid}")
    return True, "فایل حذف شد."


def edit_assignment(app: App, admin_id: int, aid: int, title, desc, points_text):
    a = app.assignment(aid)
    if not a:
        return False, "تکلیف پیدا نشد."
    title = clean(title)
    if not (2 <= len(title) <= 120):
        return False, "عنوان باید ۲ تا ۱۲۰ حرف باشد."
    pts = a["points"]
    if a["kind"] == "bonus":
        v = en(points_text or "").strip()
        if not v.isdigit() or not (1 <= int(v) <= 1000):
            return False, "امتیاز باید عددی بین ۱ تا ۱۰۰۰ باشد."
        pts = int(v)
    app.conn.execute("UPDATE assignments SET title=?, description=?, points=? WHERE id=?", (title, (desc or "").strip(), pts, aid))
    app.conn.commit()
    app.audit(admin_id, "assignment_edit", f"{aid}")
    return True, "تکلیف ویرایش شد (دانش‌آموزان خبردار نمی‌شوند؛ اگر لازم است از «یادآوری» استفاده کن)."


def _need_ts(app, text):
    ts = J.parse(text or "", app.now())
    return ts


def extend_all(app: App, admin_id: int, aid: int, text: str):
    a = app.assignment(aid)
    ts = _need_ts(app, text)
    if not a:
        return False, "تکلیف پیدا نشد."
    if ts is None:
        return False, "زمان را نفهمیدم؛ مثل «فردا ۲۱:۳۰» بنویس."
    app.conn.execute("UPDATE assignments SET deadline_ts=? WHERE id=?", (ts, aid))
    app.conn.commit()
    app.audit(admin_id, "extend_all", f"{aid}:{ts}")
    n = 0
    for s, _ in admin.tally(app, app.assignment(aid))["none"]:
        if _tell(app, s["id"], f"⏱ مهلت تکلیف «{a['title']}» تغییر کرد.\nمهلت جدید: {J.fmt(ts)}", admin.open_btn(aid)):
            n += 1
    return True, f"مهلت جدید ثبت شد: {J.fmt(ts)}؛ به {fa(n)} نفرِ ارسال‌نشده اطلاع داده شد."


def extend_one(app: App, admin_id: int, aid: int, sid: int, text: str):
    a, s = app.assignment(aid), app.student(sid)
    ts = _need_ts(app, text)
    if not a or not s:
        return False, "تکلیف یا دانش‌آموز پیدا نشد."
    if ts is None:
        return False, "زمان را نفهمیدم؛ مثل «فردا ۲۱:۳۰» بنویس."
    app.conn.execute("INSERT OR REPLACE INTO student_deadlines VALUES(?,?,?)", (aid, sid, ts))
    app.conn.commit()
    app.audit(admin_id, "extend_one", f"{aid}:{sid}:{ts}")
    _tell(app, sid, f"⏱ برای تو مهلت تکلیف «{a['title']}» تا {J.fmt(ts)} تمدید شد.", admin.open_btn(aid))
    return True, f"مهلت {s['full_name']} تا {J.fmt(ts)} تمدید شد."


def cancel_assignment(app: App, admin_id: int, aid: int, restore: bool = False):
    if not app.assignment(aid):
        return False, "تکلیف پیدا نشد."
    app.conn.execute("UPDATE assignments SET status=? WHERE id=?", ("active" if restore else "cancelled", aid))
    app.conn.commit()
    app.audit(admin_id, "assignment_restore" if restore else "assignment_cancel", str(aid))
    return True, "تکلیف دوباره فعال شد." if restore else "تکلیف لغو شد (پاسخ‌ها و فایل‌ها حذف نشدند)."


def excuse(app: App, admin_id: int, aid: int, sid: int, reason: str):
    a, s = app.assignment(aid), app.student(sid)
    if not a or not s:
        return False, "تکلیف یا دانش‌آموز پیدا نشد."
    app.conn.execute("INSERT OR REPLACE INTO excuses VALUES(?,?,?,?,?)", (aid, sid, clean(reason)[:200], admin_id, app.now()))
    app.conn.commit()
    app.audit(admin_id, "excuse", f"{aid}:{sid}")
    _tell(app, sid, f"🙏 برای تکلیف «{a['title']}» عذر موجهت ثبت شد و روی شمارنده‌ی نشانت اثر منفی ندارد.")
    for t in app.award(sid):
        _tell(app, sid, f"🎉 نشان تازه گرفتی!\n{t}")
    return True, f"عذر موجه برای {s['full_name']} ثبت شد."


def request_resubmit(app: App, admin_id: int, aid: int, sid: int, note: str):
    a, s = app.assignment(aid), app.student(sid)
    if not a or not s:
        return False, "تکلیف یا دانش‌آموز پیدا نشد."
    note = clean(note)[:300]
    app.conn.execute("INSERT OR REPLACE INTO resubmit_requests(assignment_id,student_id,note,ts,open) VALUES(?,?,?,?,1)", (aid, sid, note, app.now()))
    app.conn.commit()
    app.audit(admin_id, "resubmit_request", f"{aid}:{sid}")
    _tell(app, sid, f"🔁 مدیر از تو خواسته پاسخ تکلیف «{a['title']}» را دوباره بفرستی." + (f"\n\nتوضیح: {note}" if note else "")
          + "\n(وضعیت به‌موقع/تاخیر ارسال اولت تغییر نمی‌کند.)", admin.open_btn(aid))
    return True, f"درخواست ارسال مجدد برای {s['full_name']} فرستاده شد."


def remind_assignment(app: App, admin_id: int, aid: int):
    a = app.assignment(aid)
    if not a:
        return False, "تکلیف پیدا نشد."
    n = 0
    for s, _ in admin.tally(app, a)["none"]:
        if _tell(app, s["id"], f"🔔 یادآوری: تکلیف «{a['title']}» هنوز ارسال نشده.\n⏰ مهلت: {J.fmt(R.effective_deadline(app.conn, a, s['id']))}", admin.open_btn(aid)):
            n += 1
    app.audit(admin_id, "remind", f"{aid}:{n}")
    return True, f"یادآوری برای {fa(n)} نفرِ ارسال‌نشده فرستاده شد."


# ---------- بازخورد و پیام ----------
def give_feedback(app: App, admin_id: int, sid: int, aid: int, text: str):
    s = app.student(sid)
    text = (text or "").strip()
    if not s or not text:
        return False, "دانش‌آموز و متن بازخورد لازم است."
    a = app.assignment(aid) if aid else None
    app.conn.execute("INSERT INTO feedback(student_id,assignment_id,text,admin_id,ts) VALUES(?,?,?,?,?)",
                     (sid, a["id"] if a else None, text[:2000], admin_id, app.now()))
    app.conn.commit()
    app.audit(admin_id, "feedback", str(sid))
    sent = _tell(app, sid, "💬 بازخورد مدیر" + (f" برای «{a['title']}»" if a else "") + f":\n\n{text[:2000]}")
    return True, "بازخورد ثبت و فرستاده شد." if sent else "بازخورد ثبت شد (دانش‌آموز هنوز وارد بات نشده)."


def broadcast(app: App, admin_id: int, target: str, text: str):
    text = (text or "").strip()
    if not text:
        return False, "متن پیام را بنویس."
    if not re.fullmatch(r"all|g6|g7|g9|s\d+|\d+", target or ""):
        return False, "گیرنده نامعتبر است."
    rec = admin.bc_recipients(app, target)
    if not rec:
        return False, "گیرنده‌ای پیدا نشد (هنوز وارد بات نشده‌اند یا غیرفعال‌اند)."
    n = 0
    for s in rec:
        if app.send(s["chat_id"], f"📢 پیام مجموعه رشد\n\n{text[:3500]}"):
            n += 1
        time.sleep(0.04)
    app.audit(admin_id, "broadcast", f"{target}:{n}")
    return True, f"پیام برای {fa(n)} نفر ارسال شد."


# ---------- باشگاه کتابخوانی ----------
def book_edit(app: App, admin_id: int, rid: int, book: str, from_p: str, to_p: str):
    r = app.conn.execute("SELECT * FROM book_reports WHERE id=? AND status='active'", (rid,)).fetchone()
    if not r:
        return False, "گزارش پیدا نشد."
    book = clean(book)
    if not (2 <= len(book) <= 80):
        return False, "نام کتاب ۲ تا ۸۰ حرف باشد."
    a, b = en(from_p or "").strip(), en(to_p or "").strip()
    if not (a.isdigit() and b.isdigit()) or int(a) < 1 or int(b) < int(a) or int(b) - int(a) + 1 > max(app.cfg.book_max_pages * 3, 900):
        return False, "صفحه‌ها معتبر نیست (تا صفحه نباید کمتر از از صفحه باشد)."
    a, b = int(a), int(b)
    app.conn.execute("UPDATE book_reports SET book=?, from_page=?, to_page=?, pages=?, edited_ts=? WHERE id=?", (book, a, b, b - a + 1, app.now(), rid))
    app.conn.commit()
    app.audit(admin_id, "book_edit", str(rid))
    return True, "گزارش ویرایش شد (در گروه پیام اصلاحیه نمی‌رود؛ اگر لازم است «ارسال دوباره» را بزن)."


def book_delete(app: App, admin_id: int, rid: int):
    if not app.conn.execute("SELECT 1 FROM book_reports WHERE id=? AND status='active'", (rid,)).fetchone():
        return False, "گزارش پیدا نشد."
    app.conn.execute("UPDATE book_reports SET status='deleted', edited_ts=? WHERE id=?", (app.now(), rid))
    app.conn.commit()
    app.audit(admin_id, "book_delete", str(rid))
    return True, "گزارش حذف شد (پیام گروه پاک نمی‌شود)."


def book_repost(app: App, admin_id: int, rid: int):
    r = app.conn.execute("SELECT edited_ts FROM book_reports WHERE id=? AND status='active'", (rid,)).fetchone()
    if not r:
        return False, "گزارش پیدا نشد."
    ok = books.post_report(app, rid, "✏ گزارش اصلاح‌شده\n" if r["edited_ts"] else "")
    return (True, "در گروه ارسال شد.") if ok else (False, "ارسال نشد؛ گروه تنظیم نشده یا بات در گروه نیست.")


def book_set_group(app: App, admin_id: int, chat_id: int):
    if not app.conn.execute("SELECT 1 FROM known_groups WHERE chat_id=?", (chat_id,)).fetchone():
        return False, "این گروه را بات ندیده است."
    ok = books.set_group(app, chat_id)
    app.audit(admin_id, "book_group_set", str(chat_id))
    return True, "گروه تنظیم شد و پیام آزمایشی فرستاده شد." if ok else "گروه ذخیره شد، اما پیام آزمایشی نرفت؛ مطمئن شو بات عضو گروه است."


# ---------- مدیران ----------
def admin_add(app: App, admin_id: int, raw: str):
    v = en(raw or "").replace(" ", "")
    if not v.isdigit() or len(v) > 15:
        return False, "شناسه باید فقط عدد باشد."
    app.conn.execute("INSERT OR IGNORE INTO admins VALUES(?,?)", (int(v), app.now()))
    app.conn.commit()
    app.audit(admin_id, "admin_add", v)
    return True, "مدیر اضافه شد."


def admin_remove(app: App, admin_id: int, uid: int):
    if uid == admin_id:
        return False, "نمی‌توانی خودت را حذف کنی."
    if uid in app.cfg.admin_ids:
        return False, "این مدیر در تنظیمات سرور (ADMIN_IDS) است و از اینجا حذف نمی‌شود."
    if not app.conn.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone():
        return False, "این مدیر پیدا نشد."
    app.conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    app.conn.commit()
    app.audit(admin_id, "admin_remove", str(uid))
    return True, "مدیر حذف شد."
