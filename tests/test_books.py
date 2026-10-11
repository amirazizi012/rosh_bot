"""آزمون پایه‌ی نهم (باشگاه کتابخوانی)، امتیازها، مدیریت نشان‌ها، جداسازی پایه‌ها و سقف حجم فایل."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app import books, main, reports, rules as R, jalali as J
from app.fa import fa
import test_flow as tf
from test_flow import make_app, upd, go, ADMIN, STU

S6 = 3000
GROUP = -100500
H = 3600


def gupd(chat, user, text, title="گروه نهمی‌ها"):
    tf._uid[0] += 1
    return {"update_id": tf._uid[0], "message": {"chat": {"id": chat, "type": "group", "title": title},
                                                 "from": {"id": user}, "text": text}}


def code_of(app, name):
    return app.conn.execute("SELECT code FROM students WHERE full_name=?", (name,)).fetchone()["code"]


def setup():
    app, bale = make_app()
    app._t = int(J.from_jalali(1405, 7, 15, 12, 0))      # چهارشنبه ۱۵ مهر ۱۴۰۵
    go(app, upd(ADMIN, "/start"),
       upd(ADMIN, data="a:sadd"), upd(ADMIN, data="a:sadd:9"), upd(ADMIN, "مهدی نمونه\nرضا نمونه"),
       upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "علی ششمی"))
    go(app, upd(STU, "/start"), upd(STU, code_of(app, "مهدی نمونه")), upd(S6, "/start"), upd(S6, code_of(app, "علی ششمی")))
    return app, bale


def set_group(app):
    go(app, gupd(GROUP, ADMIN, "/setgroup"))


def report(app, pair_cb, book, a, b, chat=STU):
    go(app, upd(chat, data="b:new"), upd(chat, data=pair_cb), upd(chat, book), upd(chat, str(a)), upd(chat, str(b)), upd(chat, data="b:ok"))


def test_grades_and_isolation():
    app, bale = setup()
    s9 = app.conn.execute("SELECT * FROM students WHERE full_name='مهدی نمونه'").fetchone()
    s6 = app.conn.execute("SELECT * FROM students WHERE full_name='علی ششمی'").fetchone()
    assert s9["grade"] == 9 and s6["grade"] == 6
    assert any("باشگاه کتابخوانی" in t for t in bale.texts(STU))
    # نهمی: دکمه‌های تکالیف کار نمی‌کند و فقط منوی کتابخوانی برمی‌گردد
    n = len(bale.out)
    go(app, upd(STU, data="s:open"))
    assert "باشگاه کتابخوانی" in bale.out[-1][1] and len(bale.out) == n + 1
    # ششمی: بخش کتابخوانی را ندارد
    go(app, upd(S6, data="b:new"))
    assert "چه کاری می‌خواهی" in bale.out[-1][1]
    # تکلیف برای همه فقط به ششمی‌ها می‌رسد
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ت','required',?,20,24,1,?)", (app._t + H, app._t))
    app.conn.commit()
    a = app.assignment(1)
    assert [s["id"] for s in R.target_students(app.conn, a)] == [s6["id"]]
    assert R.targets_for_student(app.conn, s9["id"]) == []


def test_book_report_flow_and_group_post():
    app, bale = setup()
    set_group(app)
    assert app.get_setting("book_group_chat_id") == str(GROUP)
    assert any("تنظیم شد" in t for t in bale.texts(GROUP))
    # دکمه‌های انتخاب روز: ۶ جفت + تاریخ دلخواه
    go(app, upd(STU, data="b:new"))
    rows = bale.out[-1][2]
    labels = [r[0]["text"] for r in rows]
    assert labels[0] == "سه‌شنبه و چهارشنبه ۱۴ و ۱۵ مهر" and len(labels) == 8, labels
    # جریان کامل مثل قالب کاربر
    go(app, upd(STU, data="b:d:1"))                       # دوشنبه و سه‌شنبه ۱۳ و ۱۴ مهر
    go(app, upd(STU, "اسطوره های موازی"), upd(STU, "۴۵۱"))
    go(app, upd(STU, "۴۷۰"))
    preview = bale.texts(STU)[-1]
    assert "نام: *مهدی نمونه*" in preview and "(۲۰ صفحه)" in preview
    go(app, upd(STU, data="b:ok"))
    r = app.conn.execute("SELECT * FROM book_reports").fetchone()
    assert (r["from_page"], r["to_page"], r["pages"], r["posted"]) == (451, 470, 20, 1)
    msg = bale.texts(GROUP)[-1]
    assert msg == ("نام: *مهدی نمونه*\nگزارش روز: *دوشنبه و سه‌شنبه ۱۳ و ۱۴ مهر*\nنام کتاب: *اسطوره های موازی*\n"
                   "از صفحه *۴۵۱* تا صفحه *۴۷۰* *(۲۰ صفحه)*"), msg
    assert any("در گروه هم ارسال شد" in t for t in bale.texts(STU))
    # تکراری برای همان دو روز
    go(app, upd(STU, data="b:new"), upd(STU, data="b:d:1"))
    assert "قبلاً گزارش ثبت کرده" in bale.texts(STU)[-1]
    # کتاب قبلی با یک دکمه
    go(app, upd(STU, data="b:new"), upd(STU, data="b:d:3"))
    assert any("📕 اسطوره های موازی" in b["text"] for row in bale.out[-1][2] for b in row)
    go(app, upd(STU, data="b:pb:0"))
    assert app.get_state(STU)[0] == "b:from"
    # اعتبارسنجی‌ها
    go(app, upd(STU, "abc"), upd(STU, "471"), upd(STU, "400"))
    assert "کمتر از" in bale.texts(STU)[-1]
    go(app, upd(STU, "1000"))
    assert "بیشتر از ۳۰۰" in bale.texts(STU)[-1]
    go(app, upd(STU, "480"))
    assert app.get_state(STU)[0] == "b:confirm"
    go(app, upd(STU, data="b:cancel"))
    assert app.get_state(STU)[0] == ""
    # تاریخ دلخواه: آینده رد، گذشته‌ی دور رد، معتبر قبول
    go(app, upd(STU, data="b:new"), upd(STU, data="b:dx"), upd(STU, "۱۴۰۵/۰۷/۱۵"))
    assert "آینده" in bale.texts(STU)[-1]
    go(app, upd(STU, "۱۴۰۵/۰۵/۰۱"))
    assert "روز گذشته" in bale.texts(STU)[-1]
    go(app, upd(STU, "۱۴۰۵/۰۷/۰۶"))
    assert app.get_state(STU)[0] == "b:book"
    # گزارش‌های من
    go(app, upd(STU, data="b:mine"))
    assert "اسطوره های موازی" in bale.texts(STU)[-1]


def test_markdown_chars_are_neutralised():
    assert books.md_safe("کتاب *پررنگ* و _کج_ [لینک]") == "کتاب پررنگ و کج (لینک)"
    t = books.report_text("نام*", 1790000000, 1790086400, "اسم_کتاب*", 1, 5)
    assert "نام: *نام*" in t and "نام کتاب: *اسم کتاب*" in t and "_" not in t


def test_admin_book_tools_and_group_failure():
    app, bale = setup()                                    # گروه تنظیم نشده
    report(app, "b:d:0", "کتاب الف", 10, 40)
    assert any("در گروه ارسال نشد" in t for t in bale.texts(ADMIN))      # به مدیر خبر داده می‌شود
    assert app.conn.execute("SELECT posted FROM book_reports").fetchone()["posted"] == 0
    # گروه را مدیر از فهرست انتخاب می‌کند؛ بعد «ارسال مجدد»
    go(app, gupd(GROUP, STU, "/setgroup"))                 # دانش‌آموز نمی‌تواند گروه را تنظیم کند
    assert app.get_setting("book_group_chat_id") is None
    assert app.conn.execute("SELECT title FROM known_groups").fetchone()["title"] == "گروه نهمی‌ها"
    go(app, upd(ADMIN, data="a:book:grp"))
    assert any(f"a:book:gs:{GROUP}" == b["callback_data"] for row in bale.out[-1][2] for b in row)
    go(app, upd(ADMIN, data=f"a:book:gs:{GROUP}"), upd(ADMIN, data="a:book:retry"))
    assert app.conn.execute("SELECT posted FROM book_reports").fetchone()["posted"] == 1
    # گزارش کلی و اکسل
    report(app, "b:d:2", "کتاب ب", 1, 20)
    go(app, upd(ADMIN, data="a:book:sum"))
    t = bale.texts(ADMIN)[-1]
    assert "مهدی نمونه: ۲ گزارش | ۵۱ صفحه | ۲ کتاب" in t and "رضا نمونه: ۰ گزارش" in t and "رتبه" not in t
    go(app, upd(ADMIN, data="a:book:xlsx"))
    assert any(f.endswith(".xlsx") for _, f in bale.files)
    # ویرایش و حذف (فقط مدیر)
    rid = app.conn.execute("SELECT id FROM book_reports ORDER BY id").fetchone()["id"]
    go(app, upd(ADMIN, data=f"a:book:eb:{rid}"), upd(ADMIN, "کتاب اصلاح‌شده"),
       upd(ADMIN, data=f"a:book:ep:{rid}"), upd(ADMIN, "۱۰ ۱۰۹"))
    r = app.conn.execute("SELECT * FROM book_reports WHERE id=?", (rid,)).fetchone()
    assert (r["book"], r["pages"]) == ("کتاب اصلاح‌شده", 100)
    n = len(bale.texts(GROUP))
    go(app, upd(ADMIN, data=f"a:book:rp:{rid}"))
    assert bale.texts(GROUP)[-1].startswith("✏ گزارش اصلاح‌شده") and len(bale.texts(GROUP)) == n + 1
    go(app, upd(ADMIN, data=f"a:book:dely:{rid}"))
    assert app.conn.execute("SELECT status FROM book_reports WHERE id=?", (rid,)).fetchone()["status"] == "deleted"
    assert reports.book_stats(app.conn)["total_pages"] == 20
    # دانش‌آموز راهی برای ویرایش ندارد
    go(app, upd(STU, data=f"a:book:dely:{rid}"))
    assert "مخصوص مدیران" in bale.texts(STU)[-1]


def test_bonus_points_approval_flow():
    app, bale = setup()
    go(app, upd(ADMIN, data="a:new"), upd(ADMIN, "مسئله‌ی ویژه"), upd(ADMIN, "حل کنید"), upd(ADMIN, data="a:nb"),
       upd(ADMIN, data="a:nk:bonus"))
    assert "امتیاز این تکلیف امتیازی" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, "abc"))
    assert "عدد" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, "۱۵"), upd(ADMIN, data="a:nt:all"), upd(ADMIN, "فردا ۲۱:۳۰"))
    assert "⭐ ۱۵ امتیاز" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, data="a:npub:1"))
    a = app.conn.execute("SELECT * FROM assignments").fetchone()
    assert a["kind"] == "bonus" and a["points"] == 15
    s6 = app.conn.execute("SELECT id FROM students WHERE full_name='علی ششمی'").fetchone()["id"]
    go(app, upd(S6, data=f"s:send:{a['id']}"), upd(S6, photo=True), upd(S6, data="s:fin"))
    assert any("بعد از تأیید مدیر" in t for t in bale.texts(S6))
    led = app.conn.execute("SELECT * FROM points_ledger").fetchall()
    assert len(led) == 1 and led[0]["status"] == "pending" and led[0]["delta"] == 15
    assert R.points_total(app.conn, s6) == (0, 15)
    go(app, upd(S6, data="s:prog"))
    assert "در انتظار تأیید مدیر: ۱۵" in bale.texts(S6)[-1]
    # مدیر: صف تأیید
    go(app, upd(ADMIN, data="a:pts:0"))
    assert "علی ششمی" in bale.texts(ADMIN)[-1] and "+۱۵" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, data=f"a:pok:{led[0]['id']}"))
    assert R.points_total(app.conn, s6) == (15, 0)
    assert any("۱۵ امتیاز" in t and "تأیید شد" in t for t in bale.texts(S6))
    go(app, upd(S6, data="s:prog"))
    t = bale.texts(S6)[-1]
    assert "امتیاز تو: ۱۵" in t and "علی" not in t.replace("علی ششمی", "")  # فقط امتیاز خودش
    # دوباره award → امتیاز تکراری نمی‌شود
    app.award(s6); app.award(s6)
    assert app.conn.execute("SELECT COUNT(*) c FROM points_ledger").fetchone()["c"] == 1
    # ویرایش امتیاز تکلیف
    go(app, upd(ADMIN, data=f"a:aedf:{a['id']}:p"), upd(ADMIN, "۲۵"))
    assert app.assignment(a["id"])["points"] == 25


def test_extra_streak_badge_points_and_badge_management():
    app, bale = setup()
    s6 = app.conn.execute("SELECT id FROM students WHERE full_name='علی ششمی'").fetchone()["id"]
    now = app._t
    app.conn.execute("UPDATE students SET created_ts=?", (now - 60 * 86400,)); app.conn.commit()   # عضو قدیمی
    for i in range(5):
        dl = now - (10 - i) * 86400
        kind = "optional" if i % 2 else "bonus"
        app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts,points) VALUES(?,?,?,20,24,1,?,0)",
                         (f"اختیاری {i}", kind, dl, dl - 5 * 86400))
        app.conn.commit()
        a = app.conn.execute("SELECT * FROM assignments ORDER BY id DESC").fetchone()
        cur = app.conn.execute("INSERT INTO submissions(assignment_id,student_id,state,created_ts) VALUES(?,?,'draft',?)", (a["id"], s6, dl - 3600))
        app.conn.commit()
        R.finalize(app.conn, a, s6, cur.lastrowid, dl - 3600)
    new = app.award(s6)
    assert any("نشان کوشا" in t for t in new)
    led = app.conn.execute("SELECT * FROM points_ledger WHERE kind='badge'").fetchall()
    assert len(led) == 1 and led[0]["delta"] == 10 and led[0]["status"] == "pending"
    assert R.points_total(app.conn, s6) == (0, 10)
    # حذف نشان خودکار → دوباره صادر نمی‌شود و امتیاز در انتظارش رد می‌شود
    bid = app.conn.execute("SELECT id FROM badges WHERE code='xstreak'").fetchone()["id"]
    go(app, upd(ADMIN, data=f"a:sbd:{s6}"))
    assert "🏅" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, data=f"a:sbdd:{bid}"), upd(ADMIN, data=f"a:sbddy:{bid}"))
    assert app.conn.execute("SELECT COUNT(*) c FROM badges WHERE code='xstreak'").fetchone()["c"] == 0
    assert app.award(s6) == [] or all("کوشا" not in t for t in app.award(s6))
    assert app.conn.execute("SELECT COUNT(*) c FROM badges WHERE code='xstreak'").fetchone()["c"] == 0
    assert R.points_total(app.conn, s6)[1] == 0
    # ویرایش عنوان نشان
    first = app.conn.execute("SELECT id FROM badges WHERE student_id=? ORDER BY id", (s6,)).fetchone()["id"]
    go(app, upd(ADMIN, data=f"a:sbde:{first}"), upd(ADMIN, "عنوان تازه"))
    assert app.conn.execute("SELECT title FROM badges WHERE id=?", (first,)).fetchone()["title"] == "عنوان تازه"
    # افزودن نشان دستی
    go(app, upd(ADMIN, data=f"a:bds:{s6}"), upd(ADMIN, "بهترین توضیح هفته"))
    assert app.conn.execute("SELECT 1 FROM badges WHERE title LIKE '%بهترین توضیح%'").fetchone()


def test_manual_points_adjustment():
    app, bale = setup()
    s6 = app.conn.execute("SELECT id FROM students WHERE full_name='علی ششمی'").fetchone()["id"]
    go(app, upd(ADMIN, data=f"a:padj:{s6}"), upd(ADMIN, "abc"))
    assert "با عدد شروع کن" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, "+۵ مشارکت عالی در کلاس"))
    go(app, upd(ADMIN, data=f"a:padj:{s6}"), upd(ADMIN, "-3 بی‌نظمی"))
    assert R.points_total(app.conn, s6) == (2, 0)
    assert any("مدیر امتیاز تو را تغییر داد" in t for t in bale.texts(S6))
    go(app, upd(ADMIN, data=f"a:spts:{s6}"))
    t = bale.texts(ADMIN)[-1]
    assert "تأییدشده: ۲" in t and "مشارکت عالی در کلاس" in t and "-۳" in t
    # تأیید همه
    R.add_points(app.conn, s6, 10, "x", "bonus", "asg", 99, app._t, "pending")
    R.add_points(app.conn, s6, 10, "y", "bonus", "asg", 98, app._t, "pending")
    go(app, upd(ADMIN, data="a:pall"))
    assert R.points_total(app.conn, s6) == (22, 0)


def test_upload_limit_15mb():
    app, bale = setup()
    assert app.cfg.max_file_mb == 15
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ت','required',?,20,24,1,?)", (app._t + H, app._t))
    app.conn.commit()
    big = {"file_id": "d", "file_name": "a.pdf", "mime_type": "application/pdf", "file_size": 16 * 1024 * 1024}
    go(app, upd(S6, data="s:send:1"), upd(S6, doc=big))
    assert "۱۵ مگابایت" in bale.texts(S6)[-1]
    assert app.conn.execute("SELECT COUNT(*) c FROM submission_files").fetchone()["c"] == 0
    ok = dict(big, file_size=14 * 1024 * 1024)
    go(app, upd(S6, doc=ok))
    assert app.conn.execute("SELECT COUNT(*) c FROM submission_files").fetchone()["c"] == 1
    app.cfg.max_file_mb = 0                                  # اندازه‌ی واقعی بعد از دانلود هم بررسی می‌شود
    go(app, upd(S6, doc=dict(ok, file_size=0)))
    assert app.conn.execute("SELECT COUNT(*) c FROM submission_files").fetchone()["c"] == 1


def test_broadcast_by_grade_and_reports_filter_by_grade():
    app, bale = setup()
    go(app, upd(ADMIN, data="a:bc"), upd(ADMIN, data="a:bct:g9"), upd(ADMIN, "جلسه‌ی باشگاه فردا است"), upd(ADMIN, data="a:bcsend"))
    assert any("جلسه‌ی باشگاه" in t for t in bale.texts(STU))
    assert not any("جلسه‌ی باشگاه" in t for t in bale.texts(S6))
    assert "مهدی نمونه" not in reports.class_lines(app) and "علی ششمی" in reports.class_lines(app)
    go(app, upd(ADMIN, data="a:slist:0"))
    labels = [b["text"] for row in bale.out[-1][2] for b in row]
    assert any("مهدی نمونه (نهم)" in l for l in labels) and any("علی ششمی (ششم)" in l for l in labels)


def test_polling_pause():
    assert main.needs_pause([], 0.01) is True
    assert main.needs_pause([], 20.0) is False and main.needs_pause([{"update_id": 1}], 0.01) is False


def test_old_db_migration():
    import sqlite3, tempfile
    from app import db
    p = tempfile.mktemp(suffix=".db")
    c = sqlite3.connect(p)
    c.executescript("CREATE TABLE students(id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, code TEXT UNIQUE NOT NULL, chat_id INTEGER UNIQUE, active INTEGER NOT NULL DEFAULT 1, created_ts INTEGER NOT NULL, joined_ts INTEGER);"
                    "INSERT INTO students(full_name,code,created_ts) VALUES('علی','111111',1);"
                    "CREATE TABLE assignments(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'required', deadline_ts INTEGER NOT NULL, grace_min INTEGER NOT NULL, late_hours INTEGER NOT NULL, target_all INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active', created_ts INTEGER NOT NULL);"
                    "INSERT INTO assignments(title,deadline_ts,grace_min,late_hours,created_ts) VALUES('ت',5,20,24,1);")
    c.commit(); c.close()
    conn = db.connect(p)
    assert dict(conn.execute("SELECT full_name, grade FROM students").fetchone()) == {"full_name": "علی", "grade": 6}
    assert conn.execute("SELECT points FROM assignments").fetchone()["points"] == 0
    db.connect(p).close()                                    # اجرای دوباره‌ی مهاجرت بی‌خطر است


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
