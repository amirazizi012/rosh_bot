"""آزمون بررسی مدیر: ویرایش وضعیت پاسخ‌ها (ناقص / ارسال‌شده / با تاخیر / ارسال‌نشده)، نشان و امتیاز بعد از تأیید."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app import rules as R, points, reports, panel_ui as UI, db
import test_flow as tf
from test_flow import make_app, upd, go, ADMIN, STU

H = 3600
D = 86400


def mk(n_asg=6, kind="required", points_=0):
    """یک دانش‌آموز ششم (STU) و n تکلیف گذشته که همه را به‌موقع فرستاده."""
    app, bale = make_app()
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "علی بررسی"))
    code = app.conn.execute("SELECT code FROM students").fetchone()["code"]
    go(app, upd(STU, "/start"), upd(STU, code))
    app.conn.execute("UPDATE students SET created_ts=?", (app._t - 90 * D,)); app.conn.commit()
    for i in range(n_asg):
        dl = app._t - (n_asg - i) * 2 * D
        app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts,points) VALUES(?,?,?,20,24,1,?,?)",
                         (f"تکلیف {i + 1}", kind, dl, dl - 5 * D, points_))
        app.conn.commit()
        a = app.conn.execute("SELECT * FROM assignments ORDER BY id DESC").fetchone()
        sub(app, a, dl - H)
    return app, bale


def sub(app, a, at, sid=1):
    cur = app.conn.execute("INSERT INTO submissions(assignment_id,student_id,state,created_ts) VALUES(?,?,'draft',?)", (a["id"], sid, at))
    app.conn.commit()
    p = app.data / "submissions" / str(a["id"]) / str(sid) / f"{cur.lastrowid}.jpg"
    p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")
    app.conn.execute("INSERT INTO submission_files(submission_id,path,name,size) VALUES(?,?,?,1)", (cur.lastrowid, str(p), "x.jpg"))
    app.conn.commit()
    return R.finalize(app.conn, a, sid, cur.lastrowid, at)


def status(app, aid, sid=1):
    a = app.assignment(aid)
    return R.student_status(app.conn, a, sid, app._t)


def badge(app, code="streak"):
    return app.conn.execute("SELECT * FROM badges WHERE code=?", (code,)).fetchone()


def test_mark_second_assignment_incomplete():
    app, bale = mk(3)
    assert [status(app, i)["code"] for i in (1, 2, 3)] == ["on_time"] * 3
    # مدیر: صفحه‌ی بررسی دانش‌آموز ← تکلیف دوم ← ناقص با توضیح
    go(app, upd(ADMIN, data="a:rvl:1"))
    labels = [b["text"] for row in bale.out[-1][2] for b in row]
    assert sum("✅" in l for l in labels) == 3
    go(app, upd(ADMIN, data="a:rv:2:1"))
    assert "وضعیت فعلی: ✅ ارسال‌شده (به‌موقع)" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, data="a:rvs:2:1:inc"), upd(ADMIN, "حل مسئله‌ی ۳ ناقص است"))
    st = status(app, 2)
    assert st["code"] == "incomplete" and st["sub"] is not None and st["override"]["note"] == "حل مسئله‌ی ۳ ناقص است"
    assert [status(app, i)["code"] for i in (1, 3)] == ["on_time"] * 2
    # آمار و شمارنده
    t = R.student_stats(app.conn, 1, app._t, 6)
    assert (t["on_time"], t["incomplete"], t["current"]) == (2, 1, 1)         # شمارنده بعد از ناقص از صفر شروع شد
    # دانش‌آموز خبر می‌گیرد و اجازه‌ی ارسال مجدد دارد
    assert any("«ناقص»" in t and "حل مسئله‌ی ۳ ناقص است" in t for t in bale.texts(STU))
    assert R.open_resubmit(app.conn, 2, 1) is not None
    go(app, upd(STU, data="s:a:2"))
    txt = bale.texts(STU)[-1]
    assert "ناقص" in txt and "حل مسئله‌ی ۳ ناقص است" in txt
    assert "s:send:2" in [b["callback_data"] for row in bale.out[-1][2] for b in row]
    go(app, upd(STU, data="s:done"))
    assert "ناقص" in bale.texts(STU)[-1]
    # گزارش‌ها
    assert "⚠️۱" in reports.class_lines(app) and "ناقص" in reports.student_report(app, 1)
    assert "ناقص" in UI.dashboard(app.conn, app.cfg, app._t) and "ناقص" in UI.assignment_page(app.conn, app.cfg, app._t, 2)
    # دانش‌آموز دوباره می‌فرستد ← «ناقص» برداشته می‌شود و وضعیت زمانی اول (به‌موقع) حفظ می‌شود
    go(app, upd(STU, data="s:send:2"), upd(STU, photo=True), upd(STU, data="s:fin"))
    st = status(app, 2)
    assert st["code"] == "on_time" and st["override"] is None and R.open_resubmit(app.conn, 2, 1) is None
    assert app.conn.execute("SELECT COUNT(*) c FROM audit WHERE action='status_override'").fetchone()["c"] == 1


def test_change_late_incomplete_missed_to_sent():
    app, bale = mk(0)
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('الف','required',?,20,24,1,?)", (app._t - 3 * D, app._t - 8 * D))
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ب','required',?,20,24,1,?)", (app._t - 2 * D, app._t - 8 * D))
    app.conn.commit()
    a1, a2 = app.assignment(1), app.assignment(2)
    sub(app, a1, a1["deadline_ts"] + 3 * H)                      # با تاخیر
    assert status(app, 1)["code"] == "late"
    # با تاخیر ← ارسال‌شده
    go(app, upd(ADMIN, data="a:rvs:1:1:ok"))
    assert status(app, 1)["code"] == "on_time" and "✎" in reports.cell_text(status(app, 1))
    assert any("«ارسال‌شده (به‌موقع)»" in t for t in bale.texts(STU))
    # ارسال‌نشده (فیزیکی تحویل داده) ← ارسال‌شده
    assert status(app, 2)["code"] == "missed"
    go(app, upd(ADMIN, data="a:rvs:2:1:ok"))
    assert status(app, 2)["code"] == "on_time" and status(app, 2)["sub"] is None
    # ناقص ← ارسال‌شده: اجازه‌ی ارسال مجدد خودکار بسته می‌شود
    go(app, upd(ADMIN, data="a:rvs:1:1:inc"), upd(ADMIN, "-"))
    assert R.open_resubmit(app.conn, 1, 1)
    go(app, upd(ADMIN, data="a:rvs:1:1:ok"))
    assert status(app, 1)["code"] == "on_time" and R.open_resubmit(app.conn, 1, 1) is None
    # ارسال‌شده ← ارسال‌نشده و ← با تاخیر، و برگشت به خودکار
    go(app, upd(ADMIN, data="a:rvs:1:1:miss"))
    assert status(app, 1)["code"] == "missed"
    go(app, upd(ADMIN, data="a:rvs:1:1:late"))
    assert status(app, 1)["code"] == "late"
    go(app, upd(ADMIN, data="a:rvs:1:1:clr"))
    st = status(app, 1)
    assert st["code"] == "late" and st["override"] is None                # خودکار: همان تاخیر واقعی
    assert any("به حالت خودکار برگشت" in t for t in bale.texts(STU))
    # انتخاب از صفحه‌ی تکلیف: همه‌ی دانش‌آموزان هدف
    go(app, upd(ADMIN, data="a:arv:1"))
    assert any("a:rv:1:1" == b["callback_data"] for row in bale.out[-1][2] for b in row)


def test_streak_badge_needs_admin_approval_and_points():
    app, bale = mk(6)
    app.cfg.streak_points = 5
    new = app.award(1)
    assert any("پشتکار" in t for t in new)
    b = badge(app)
    assert b["status"] == "pending"
    # دانش‌آموز هنوز نشان را نمی‌بیند و پیام «نشان تازه» نگرفته
    assert not any("نشان تازه" in t for t in bale.texts(STU))
    go(app, upd(STU, data="s:prog"))
    assert "پشتکار" not in bale.texts(STU)[-1]
    assert R.student_stats(app.conn, 1, app._t, 6)["badges"] == 1       # فقط «اولین قدم»؛ پشتکار هنوز منتظر تأیید است
    # مدیر خبر دارد و منو شمار را نشان می‌دهد
    assert any("نشان در انتظار تأیید شماست" in t for t in bale.texts(ADMIN))
    assert points.pending_count(app.conn) == 1
    go(app, upd(ADMIN, "/menu"))
    assert any("(۱)" in b["text"] for row in bale.out[-1][2] for b in row)
    go(app, upd(ADMIN, data="a:pts:0"))
    t = bale.texts(ADMIN)[-1]
    assert "نشان پشتکار" in t and "+۵ امتیاز" in t
    assert R.points_total(app.conn, 1) == (0, 5)
    # تأیید ← نشان و امتیاز هر دو
    go(app, upd(ADMIN, data=f"a:bok:{b['id']}"))
    assert badge(app)["status"] == "approved" and R.points_total(app.conn, 1) == (5, 0)
    assert any("نشان تازه گرفتی" in t and "پشتکار" in t and "۵ امتیاز" in t for t in bale.texts(STU))
    go(app, upd(STU, data="s:prog"))
    assert "پشتکار" in bale.texts(STU)[-1] and "امتیاز تو: ۵" in bale.texts(STU)[-1]
    assert R.student_stats(app.conn, 1, app._t, 6)["badges"] == 2
    # بعد از تأیید، ویرایش وضعیت یک تکلیف نشان تأییدشده را حذف نمی‌کند
    go(app, upd(ADMIN, data="a:rvs:3:1:inc"), upd(ADMIN, "-"))
    assert badge(app)["status"] == "approved"


def test_pending_badge_withdrawn_when_assignment_marked_incomplete():
    app, bale = mk(6)
    app.award(1)
    assert badge(app)["status"] == "pending"
    go(app, upd(ADMIN, data="a:rvs:3:1:inc"), upd(ADMIN, "ناقص"))
    assert badge(app) is None                                    # شرط از بین رفت؛ نشان در انتظار پس گرفته شد
    assert R.streak_state(app.conn, 1, app._t, 6) == (0, 3)      # تکلیف‌های ۴ تا ۶ بعد از ناقص شمارش می‌شوند
    # مدیر ناقص را برمی‌دارد ← نشان دوباره ساخته می‌شود (مسدود نشده بود)
    go(app, upd(ADMIN, data="a:rvs:3:1:ok"))
    assert badge(app) is not None and badge(app)["status"] == "pending"
    # رد نشان توسط مدیر ← مسدود می‌شود
    go(app, upd(ADMIN, data=f"a:bno:{badge(app)['id']}"))
    assert badge(app) is None
    app.award(1)
    assert badge(app) is None


def test_extra_streak_badge_pending_with_points_and_approve_all():
    app, bale = mk(5, kind="optional")
    app.award(1)
    b = badge(app, "xstreak")
    assert b["status"] == "pending" and R.points_total(app.conn, 1) == (0, 10)
    go(app, upd(ADMIN, data="a:pall"))
    assert badge(app, "xstreak")["status"] == "approved" and R.points_total(app.conn, 1) == (10, 0)
    # امتیاز نشان جدا در صف نیست (همراه خود نشان است)
    assert points.pending_count(app.conn) == 0


def test_bonus_points_follow_status():
    app, bale = mk(1, kind="bonus", points_=15)
    app.award(1)
    led = lambda: app.conn.execute("SELECT status FROM points_ledger WHERE kind='bonus'").fetchone()["status"]
    assert led() == "pending"
    go(app, upd(ADMIN, data="a:rvs:1:1:inc"), upd(ADMIN, "کامل نیست"))
    assert led() == "rejected"
    go(app, upd(ADMIN, data="a:rvs:1:1:ok"))
    assert led() == "pending" and points.pending_count(app.conn) == 1
    go(app, upd(ADMIN, data="a:pall"))
    assert R.points_total(app.conn, 1) == (15, 0)
    # ارسال‌نشده ← امتیاز رد می‌شود
    app.conn.execute("UPDATE points_ledger SET status='pending'"); app.conn.commit()
    go(app, upd(ADMIN, data="a:rvs:1:1:miss"))
    assert led() == "rejected"


def test_permissions_and_panel_rendering():
    app, bale = mk(6)
    app.award(1)
    go(app, upd(STU, data="a:rvs:1:1:inc"))
    assert "مخصوص مدیران" in bale.texts(STU)[-1] and status(app, 1)["code"] == "on_time"
    # پنل وب: نشان در انتظار و وضعیت ناقص نمایش داده می‌شود (فقط خواندنی)
    go(app, upd(ADMIN, data="a:rvs:2:1:inc"), upd(ADMIN, "-"))
    html = UI.student_page(app.conn, app.cfg, app._t, 1)
    assert "ناقص" in html and "✎" in html
    app.cfg.streak_points = 0
    app.conn.execute("DELETE FROM status_overrides"); app.conn.commit(); app.award(1)
    html = UI.points_page(app.conn, app.cfg, app._t)
    assert "نشان پشتکار" in html
    assert "در انتظار تأیید" in UI.student_page(app.conn, app.cfg, app._t, 1)


def test_old_db_gets_badge_status_column():
    import sqlite3
    p = tempfile.mktemp(suffix=".db")
    c = sqlite3.connect(p)
    c.executescript("CREATE TABLE badges(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, code TEXT NOT NULL, key TEXT NOT NULL, title TEXT NOT NULL, awarded_ts INTEGER NOT NULL, UNIQUE(student_id, code, key));"
                    "INSERT INTO badges(student_id,code,key,title,awarded_ts) VALUES(1,'streak','1','قدیمی',5);")
    c.commit(); c.close()
    conn = db.connect(p)
    assert conn.execute("SELECT status FROM badges").fetchone()["status"] == "approved"        # نشان‌های قبلی تأییدشده می‌مانند
    assert conn.execute("SELECT COUNT(*) c FROM sqlite_master WHERE name='status_overrides'").fetchone()["c"] == 1


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
