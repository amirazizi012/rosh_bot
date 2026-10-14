"""آزمون ورود با یوزرنیم بله و ویرایش پاسخ تا پایان مهلت."""
import os, sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app import rules as R, usernames
import test_flow as tf
from test_flow import make_app, upd, go, ADMIN, STU

H = 3600


def uupd(chat, text=None, username=None, data=None, name="کاربر بله"):
    """به‌روزرسانی با یوزرنیم و نام نمایشی فرستنده."""
    u = upd(chat, text, data=data)
    frm = {"id": chat, "first_name": name}
    if username:
        frm["username"] = username
    (u["callback_query"] if "callback_query" in u else u["message"])["from"] = frm
    return u


def mk():
    app, bale = make_app()
    app.cfg.login_mode = "username"
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd"), upd(ADMIN, data="a:sadd:6"),
       upd(ADMIN, "علی رضایی | @Ali_01\nمحمد کریمی | گروه ب\nرضا بی‌یوزرنیم"))
    return app, bale


def sid(app, name):
    return app.conn.execute("SELECT id FROM students WHERE full_name=?", (name,)).fetchone()["id"]


def test_username_normalize():
    assert usernames.normalize("@Ali_01") == "ali_01" and usernames.normalize("https://ble.ir/Reza_x/") == "reza_x"
    assert usernames.normalize("ab") is None and usernames.normalize("علی") is None and usernames.normalize(None) is None


def test_admin_adds_students_with_usernames():
    app, bale = mk()
    rows = {r["full_name"]: r for r in app.conn.execute("SELECT * FROM students")}
    assert rows["علی رضایی"]["username"] == "ali_01"
    assert rows["محمد کریمی"]["username"] is None and rows["رضا بی‌یوزرنیم"]["username"] is None
    assert app.conn.execute("SELECT 1 FROM groups WHERE name='گروه ب'").fetchone()           # قالب قدیمی «نام | گروه»
    assert "@ali_01" in bale.texts(ADMIN)[-1]


def test_login_by_username_flow():
    app, bale = mk()
    ali = sid(app, "علی رضایی")
    # یوزرنیم درست (بزرگ/کوچک فرقی ندارد) ← ورود خودکار + خبر به مدیر
    go(app, uupd(4000, "/start", "ALI_01"))
    assert app.conn.execute("SELECT chat_id FROM students WHERE id=?", (ali,)).fetchone()["chat_id"] == 4000
    assert any("یوزرنیمت تأیید شد" in t for t in bale.texts(4000))
    assert any("علی رضایی" in t and "@ali_01" in t and "وارد بات شد" in t for t in bale.texts(ADMIN))
    # حساب دیگری با همان یوزرنیم ← رد + هشدار به مدیر
    go(app, uupd(4001, "/start", "ali_01"))
    assert app.conn.execute("SELECT chat_id FROM students WHERE id=?", (ali,)).fetchone()["chat_id"] == 4000
    assert any("حساب دیگر" in t for t in bale.texts(4001)) and any("تلاش ورود" in t for t in bale.texts(ADMIN))
    # بازنشانی ورود توسط مدیر ← حساب جدید وارد می‌شود
    go(app, upd(ADMIN, data=f"a:streset:{ali}"), uupd(4001, "/start", "ali_01"))
    assert app.conn.execute("SELECT chat_id FROM students WHERE id=?", (ali,)).fetchone()["chat_id"] == 4001
    # حساب قدیمی دیگر وارد نیست
    assert app.student_by_chat(4000) is None
    # بدون یوزرنیم و با یوزرنیم ناشناس: راهنما + ثبت در فهرست «ورود نشده‌ها»
    go(app, uupd(4002, "/start", None, name="بدون یوزرنیم"), uupd(4003, "/start", "zed_99", name="زد"))
    assert "یوزرنیم" in bale.texts(4002)[-1] and "@zed_99" in bale.texts(4003)[-1]
    go(app, upd(ADMIN, data="a:lfail"))
    t = bale.texts(ADMIN)[-1]
    assert "@zed_99" in t and "بدون یوزرنیم" in t
    # در حالت یوزرنیم، کد ۶ رقمی کار نمی‌کند
    code = app.conn.execute("SELECT code FROM students WHERE full_name='محمد کریمی'").fetchone()["code"]
    go(app, uupd(4004, code, None))
    assert app.student_by_chat(4004) is None
    # حالت «هر دو»: کد هم قبول می‌شود
    app.cfg.login_mode = "both"
    go(app, uupd(4005, "/start", None), uupd(4005, code, None))
    assert app.student_by_chat(4005)["full_name"] == "محمد کریمی"


def test_inactive_and_grade9_login():
    app, bale = mk()
    go(app, upd(ADMIN, data="a:sadd"), upd(ADMIN, data="a:sadd:9"), upd(ADMIN, "حسین نهمی | @Hos_9"))
    go(app, uupd(4100, "/start", "hos_9"))
    assert "باشگاه کتابخوانی" in bale.texts(4100)[-1]
    ali = sid(app, "علی رضایی")
    go(app, upd(ADMIN, data=f"a:sttog:{ali}"), uupd(4101, "/start", "ali_01"))
    assert app.student_by_chat(4101) is None


def test_existing_students_learn_username():
    app, bale = make_app()                                    # حالت both؛ دانش‌آموز قبلاً با کد وارد شده
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "رضا قدیمی\nسارا قدیمی".replace("سارا", "کیان")))
    r, k = sid(app, "رضا قدیمی"), sid(app, "کیان قدیمی")
    app.conn.execute("UPDATE students SET chat_id=5000 WHERE id=?", (r,))
    app.conn.execute("UPDATE students SET chat_id=5001 WHERE id=?", (k,))
    app.conn.commit()
    go(app, uupd(5000, "سلام", "Reza_7"))
    assert app.conn.execute("SELECT username FROM students WHERE id=?", (r,)).fetchone()["username"] == "reza_7"
    go(app, uupd(5001, "سلام", "reza_7"))                      # تکراری: بازنویسی نمی‌شود
    assert app.conn.execute("SELECT username FROM students WHERE id=?", (k,)).fetchone()["username"] is None
    go(app, uupd(5000, "سلام", "Changed_9"))                   # عوض‌شدن یوزرنیم، ورود را خراب نمی‌کند و تغییر نمی‌کند
    assert app.student_by_chat(5000) and app.conn.execute("SELECT username FROM students WHERE id=?", (r,)).fetchone()["username"] == "reza_7"


def test_admin_username_tools():
    app, bale = mk()
    ali, mo = sid(app, "علی رضایی"), sid(app, "محمد کریمی")
    go(app, upd(ADMIN, data=f"a:stun:{mo}"), upd(ADMIN, "ab"))
    assert "معتبر نیست" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, "@ali_01"))
    assert "ثبت شده است" in bale.texts(ADMIN)[-1]               # تکراری
    go(app, upd(ADMIN, "@Mo_K"))
    assert app.conn.execute("SELECT username FROM students WHERE id=?", (mo,)).fetchone()["username"] == "mo_k"
    go(app, upd(ADMIN, data=f"a:stun:{mo}"), upd(ADMIN, "-"))
    assert app.conn.execute("SELECT username FROM students WHERE id=?", (mo,)).fetchone()["username"] is None
    # ثبت گروهی برای دانش‌آموزان موجود
    go(app, upd(ADMIN, data="a:uns"),
       upd(ADMIN, "محمد کریمی | @mo_k\nرضا بی‌یوزرنیم | https://ble.ir/Reza_B\nنفر ناشناس | @x_yy\nغلط\nعلی رضایی | @mo_k"))
    t = bale.texts(ADMIN)[-1]
    assert "۲ یوزرنیم ثبت شد" in t and "نفر ناشناس" in t and "قالب نادرست" in t
    assert app.conn.execute("SELECT username FROM students WHERE id=?", (sid(app, "رضا بی‌یوزرنیم"),)).fetchone()["username"] == "reza_b"
    assert app.conn.execute("SELECT username FROM students WHERE id=?", (ali,)).fetchone()["username"] == "ali_01"   # دست نخورد
    go(app, upd(ADMIN, data="a:codes"))
    assert "@ali_01" in bale.texts(ADMIN)[-1] and "کد" not in bale.texts(ADMIN)[-1]


# ====================== ویرایش پاسخ ======================
def mk_edit():
    app, bale = make_app()
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "علی ویرایشگر"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "دیگری"))
    code = app.conn.execute("SELECT code FROM students WHERE full_name='علی ویرایشگر'").fetchone()["code"]
    go(app, upd(STU, "/start"), upd(STU, code))
    dl = app._t + 5 * H
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ریاضی','required',?,20,24,1,?)", (dl, app._t))
    app.conn.commit()
    pdf = {"file_id": "d", "file_name": "answer.pdf", "mime_type": "application/pdf", "file_size": 1000}
    go(app, upd(STU, data="s:send:1"), upd(STU, photo=True), upd(STU, doc=pdf), upd(STU, data="s:fin"))
    return app, bale, dl


def files_of(app, sub_id):
    return [Path(r["path"]) for r in app.conn.execute("SELECT path FROM submission_files WHERE submission_id=? ORDER BY id", (sub_id,))]


def final(app):
    return R.current_final(app.conn, 1, 1)


def disk_files(app):
    return {p for p in (app.data / "submissions").rglob("*") if p.is_file()}


def test_edit_multiple_times_until_deadline():
    app, bale, dl = mk_edit()
    f1 = final(app)
    old = files_of(app, f1["id"])
    assert len(old) == 2 and all(p.exists() for p in old) and f1["on_time"] == 1
    # صفحه‌ی تکلیف: دکمه‌های ویرایش و دیدن پاسخ
    go(app, upd(STU, data="s:a:1"))
    cbs = [b["callback_data"] for row in bale.out[-1][2] for b in row]
    assert "s:ed:1" in cbs and "s:vw:1" in cbs and "s:send:1" not in cbs
    n_files = len(bale.files)
    go(app, upd(STU, data="s:vw:1"))
    assert len(bale.files) == n_files + 2
    # ویرایش ۱: حذف فایل اول + افزودن عکس تازه
    app._t += H
    go(app, upd(STU, data="s:ed:1"))
    assert app.get_state(STU)[0] == "s:upload"
    draft_files = app.conn.execute("SELECT id FROM submission_files WHERE submission_id=(SELECT id FROM submissions WHERE state='draft')").fetchall()
    assert len(draft_files) == 2
    go(app, upd(STU, data=f"s:rm:{draft_files[0]['id']}"), upd(STU, photo=True), upd(STU, data="s:fin"))
    f2 = final(app)
    assert f2["id"] != f1["id"] and f2["on_time"] == 1 and f2["submitted_ts"] == app._t
    new = files_of(app, f2["id"])
    assert len(new) == 2 and old[1] in new and old[0] not in new
    assert not old[0].exists() and old[1].exists()           # فایل حذف‌شده پاک شد، فایل نگه‌داشته‌شده ماند
    assert any("ویرایش پاسخت ثبت شد" in t for t in bale.texts(STU))
    # ویرایش ۲: حذف همه و فرستادن یک فایل تازه
    app._t += H
    go(app, upd(STU, data="s:ed:1"), upd(STU, data="s:rma"), upd(STU, photo=True), upd(STU, data="s:fin"))
    f3 = final(app)
    assert len(files_of(app, f3["id"])) == 1 and not any(p.exists() for p in new)
    assert disk_files(app) == set(files_of(app, f3["id"]))    # هیچ فایل یتیمی روی دیسک نمانده
    # لغو ویرایش: پاسخ فعلی دست‌نخورده
    go(app, upd(STU, data="s:ed:1"), upd(STU, data="s:cancel"))
    assert final(app)["id"] == f3["id"] and all(p.exists() for p in files_of(app, f3["id"]))
    assert "ویرایش لغو شد" in bale.texts(STU)[-1] and app.get_state(STU)[0] == ""
    # /start وسط ویرایش هم چیزی را خراب نمی‌کند
    go(app, upd(STU, data="s:ed:1"), upd(STU, "/start"))
    assert final(app)["id"] == f3["id"] and all(p.exists() for p in files_of(app, f3["id"]))
    assert app.conn.execute("SELECT COUNT(*) c FROM submissions WHERE state='draft'").fetchone()["c"] == 0
    # هنوز به‌موقع و بدون تاخیر
    assert final(app)["on_time"] == 1 and (final(app)["over_minutes"] or 0) == 0
    # مدیر تعداد ویرایش‌ها را می‌بیند
    go(app, upd(ADMIN, data="a:asub:1:1"))
    assert any("ویرایش‌شده ۲ بار" in (c or "") for c in bale.captions)
    assert app.conn.execute("SELECT COUNT(*) c FROM submissions WHERE state='superseded'").fetchone()["c"] == 2
    # «ارسال‌های من» دکمه دارد
    go(app, upd(STU, data="s:done"))
    assert any(b["callback_data"] == "s:a:1" for row in bale.out[-1][2] for b in row)


def test_edit_closes_at_deadline():
    app, bale, dl = mk_edit()
    keep = final(app)
    kept = files_of(app, keep["id"])
    # ویرایش را قبل از مهلت شروع می‌کند و بعد از مهلت «ارسال نهایی» می‌زند ← رد؛ پاسخ قبلی حفظ می‌شود
    go(app, upd(STU, data="s:ed:1"), upd(STU, photo=True))
    app._t = dl + 60
    go(app, upd(STU, data="s:fin"))
    assert "مهلت ویرایش همین الان تمام شد" in bale.texts(STU)[-1]
    f = final(app)
    assert f["id"] == keep["id"] and f["on_time"] == 1 and all(p.exists() for p in kept)
    assert disk_files(app) == set(kept)                       # فایل پیش‌نویس رهاشده هم پاک شد
    # بعد از مهلت اصلاً ویرایش شروع نمی‌شود (حتی داخل تاخیر مجاز)
    go(app, upd(STU, data="s:ed:1"))
    assert app.get_state(STU)[0] == "" and "⛔" in bale.texts(STU)[-1]
    go(app, upd(STU, data="s:a:1"))
    cbs = [b["callback_data"] for row in bale.out[-1][2] for b in row]
    assert "s:ed:1" not in cbs and "s:vw:1" in cbs
    # تمدید مهلت برای همین دانش‌آموز ← دوباره می‌تواند ویرایش کند
    app.conn.execute("INSERT INTO student_deadlines VALUES(1,1,?)", (app._t + 10 * H,)); app.conn.commit()
    go(app, upd(STU, data="s:ed:1"), upd(STU, photo=True), upd(STU, data="s:fin"))
    assert final(app)["id"] != keep["id"] and final(app)["on_time"] == 1


def test_edit_safety_and_resubmit_request():
    app, bale, dl = mk_edit()
    # فایل شخص دیگر را نمی‌شود با شناسه‌ی دستکاری‌شده حذف کرد
    app.conn.execute("INSERT INTO submissions(assignment_id,student_id,state,created_ts,submitted_ts,on_time) VALUES(1,2,'final',?,?,1)", (app._t, app._t))
    app.conn.execute("INSERT INTO submission_files(submission_id,path,name,size) VALUES((SELECT MAX(id) FROM submissions),'/tmp/foreign.jpg','x',1)")
    app.conn.commit()
    foreign = app.conn.execute("SELECT id FROM submission_files WHERE path='/tmp/foreign.jpg'").fetchone()["id"]
    go(app, upd(STU, data="s:ed:1"), upd(STU, data=f"s:rm:{foreign}"))
    assert app.conn.execute("SELECT 1 FROM submission_files WHERE id=?", (foreign,)).fetchone()
    go(app, upd(STU, data="s:cancel"))
    # سقف تعداد فایل در ویرایش هم رعایت می‌شود
    app.cfg.max_files_per_submission = 3
    go(app, upd(STU, data="s:ed:1"), upd(STU, photo=True), upd(STU, photo=True))
    assert "حداکثر ۳ فایل" in bale.texts(STU)[-1]
    go(app, upd(STU, data="s:cancel"))
    # درخواست ارسال مجدد مدیر: مسیر قبلی (جایگزینی کامل) و پاک‌سازی نسخه‌ی قبلی
    old = files_of(app, final(app)["id"])
    go(app, upd(ADMIN, data="a:arss:1:1"), upd(ADMIN, "-"))
    go(app, upd(STU, data="s:a:1"))
    cbs = [b["callback_data"] for row in bale.out[-1][2] for b in row]
    assert "s:send:1" in cbs and "s:ed:1" not in cbs
    go(app, upd(STU, data="s:send:1"), upd(STU, photo=True), upd(STU, data="s:fin"))
    assert not any(p.exists() for p in old) and len(files_of(app, final(app)["id"])) == 1


def test_finalize_guard_unit():
    import tempfile
    from app import db
    conn = db.connect(tempfile.mktemp(suffix=".db"))
    conn.execute("INSERT INTO students(full_name,code,created_ts) VALUES('ع','1',1)")
    conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ت','required',1000,20,24,1,1)")
    for ts in (500, 600):
        conn.execute("INSERT INTO submissions(assignment_id,student_id,state,created_ts) VALUES(1,1,'draft',?)", (ts,))
    conn.commit()
    a = conn.execute("SELECT * FROM assignments").fetchone()
    R.finalize(conn, a, 1, 1, 500)
    try:
        R.finalize(conn, a, 1, 2, 1010)                      # بعد از مهلت، داخل تاخیر مجاز، بدون درخواست ارسال مجدد
        assert False
    except ValueError as e:
        assert str(e) == "edit_closed"
    assert R.current_final(conn, 1, 1)["id"] == 1


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
