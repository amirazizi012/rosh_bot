"""حذف کامل دانش‌آموز از بات (دومرحله‌ای) و پنل (با تایپ نام): همه‌ی داده‌ها و فایل‌ها پاک می‌شود و دیگران دست‌نخورده می‌مانند."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from test_flow import upd, go, ADMIN, STU
from test_panel import setup
from test_panel_edit import start, token, post, row

TABLES = ("submissions", "student_deadlines", "excuses", "resubmit_requests", "receipts", "feedback", "badges", "reminders",
          "book_reports", "points_ledger", "badge_blocks", "status_overrides", "student_groups")


def seed(app, sid, tag):
    """برای دانش‌آموز sid از هر جدول مرتبط یک ردیف و فایل واقعی می‌سازد."""
    c, now = app.conn, app.now()
    aid = row(app, "SELECT id FROM assignments ORDER BY id LIMIT 1")
    aid = aid["id"] if aid else c.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('t','required',?,0,96,1,?)", (now + 9999, now)).lastrowid
    sub = c.execute("INSERT INTO submissions(assignment_id,student_id,state,created_ts,submitted_ts,on_time) VALUES(?,?,'final',?,?,1)", (aid, sid, now, now)).lastrowid
    d = app.data / "submissions" / tag
    d.mkdir(parents=True, exist_ok=True)
    f1, f2 = d / "a.jpg", app.data / "receipts" / f"{tag}.jpg"
    f2.parent.mkdir(parents=True, exist_ok=True)
    f1.write_bytes(b"x"); f2.write_bytes(b"y")
    c.execute("INSERT INTO submission_files(submission_id,path,name,size) VALUES(?,?,?,1)", (sub, str(f1), "a.jpg"))
    c.execute("INSERT INTO receipts(student_id,path,ts,status) VALUES(?,?,?, 'new')", (sid, str(f2), now))
    c.execute("INSERT INTO feedback(student_id,text,ts) VALUES(?,?,?)", (sid, "ب", now))
    c.execute("INSERT INTO points_ledger(student_id,delta,reason,kind,source_code,source_key,status,created_ts) VALUES(?,?,?,?,?,?,?,?)", (sid, 5, "r", "manual", "m", "1", "approved", now))
    c.execute("INSERT INTO badges(student_id,code,key,title,awarded_ts,status) VALUES(?,?,?,?,?,?)", (sid, "c", "k", "t", now, "approved"))
    c.execute("INSERT INTO excuses VALUES(?,?,?,?,?)", (aid, sid, "r", ADMIN, now))
    c.execute("INSERT INTO student_deadlines VALUES(?,?,?)", (aid, sid, now + 5))
    c.execute("INSERT INTO status_overrides(assignment_id,student_id,status,note,admin_id,ts) VALUES(?,?,?,?,?,?)", (aid, sid, "on_time", None, ADMIN, now))
    c.execute("INSERT INTO book_reports(student_id,day1_ts,day2_ts,book,from_page,to_page,pages,created_ts) VALUES(?,?,?,?,?,?,?,?)", (sid, now, now, "ک", 1, 2, 2, now))
    c.commit()
    return [f1, f2]


def count(app, sid):
    return sum(app.conn.execute(f"SELECT COUNT(*) FROM {t} WHERE student_id=?", (sid,)).fetchone()[0] for t in TABLES) + \
        app.conn.execute("SELECT COUNT(*) FROM submission_files WHERE submission_id IN (SELECT id FROM submissions WHERE student_id=?)", (sid,)).fetchone()[0]


def test_delete_from_bot_two_steps():
    app, bale, cfg = setup()
    go(app, upd(STU, "/start"))
    ali = row(app, "SELECT id FROM students WHERE chat_id=?", STU)["id"]
    other = app.conn.execute("INSERT INTO students(full_name,code,created_ts,grade) VALUES('دیگری','999111',?,6)", (app.now(),)).lastrowid
    mine, theirs = seed(app, ali, "ali"), seed(app, other, "other")
    assert count(app, ali) > 8
    go(app, upd(ADMIN, data=f"a:st:{ali}"))
    assert any(b["callback_data"] == f"a:sdel:{ali}" for r in bale.out[-1][2] for b in r)
    go(app, upd(ADMIN, data=f"a:sdel:{ali}"))
    assert row(app, "SELECT 1 FROM students WHERE id=?", ali)                              # هنوز حذف نشده؛ فقط تأیید می‌خواهد
    assert any(b["callback_data"] == f"a:sdelok:{ali}" for r in bale.out[-1][2] for b in r)
    go(app, upd(ADMIN, data=f"a:sdelok:{ali}"))
    assert not row(app, "SELECT 1 FROM students WHERE id=?", ali) and count(app, ali) == 0
    assert not any(p.exists() for p in mine) and all(p.exists() for p in theirs)             # فایل خودش پاک، فایل دیگری سالم
    assert count(app, other) > 8 and row(app, "SELECT 1 FROM students WHERE id=?", other)
    assert row(app, "SELECT details FROM audit WHERE action='student_delete'")
    assert not row(app, "SELECT 1 FROM chat_state WHERE chat_id=?", STU)
    go(app, upd(ADMIN, data=f"a:sdelok:{ali}"))                                              # دوباره زدن بی‌خطر است
    assert "پیدا نشد" in bale.texts(ADMIN)[-1]
    go(app, upd(STU, "/start"))                                                              # حساب بله‌اش دیگر وارد نیست
    assert not row(app, "SELECT 1 FROM students WHERE chat_id=?", STU)


def test_delete_from_panel_needs_exact_name():
    app, bale, cfg, srv, cl = start()
    try:
        go(app, upd(STU, "/start"))
        ali = row(app, "SELECT id, full_name FROM students WHERE chat_id=?", STU)
        files = seed(app, ali["id"], "pali")
        tok = token(cl, "/students")
        assert cl.req("GET", f"/student/{ali['id']}")[0] == 200 and "حذف کامل" in cl.req("GET", f"/student/{ali['id']}")[2].decode()
        assert not post(cl, "student_delete", tok, back="/students", sid=ali["id"], confirm="اشتباه")[2]
        assert not post(cl, "student_delete", tok, back="/students", sid=ali["id"], confirm="")[2]
        assert row(app, "SELECT 1 FROM students WHERE id=?", ali["id"]) and all(p.exists() for p in files)
        assert post(cl, "student_delete", tok, back="/students", sid=ali["id"], confirm=ali["full_name"])[2]
        assert not row(app, "SELECT 1 FROM students WHERE id=?", ali["id"]) and count(app, ali["id"]) == 0 and not any(p.exists() for p in files)
        assert cl.req("GET", f"/student/{ali['id']}")[0] == 404
        assert "(از پنل)" in row(app, "SELECT details FROM audit WHERE action='student_delete'")["details"]
        assert not post(cl, "student_delete", tok, back="/students", sid=ali["id"], confirm=ali["full_name"])[2]   # دوباره: پیدا نشد
        assert cl.req("GET", "/students")[0] == 200
    finally:
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
