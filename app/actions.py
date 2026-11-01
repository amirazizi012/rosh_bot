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
