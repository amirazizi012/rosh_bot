"""آزمون فاز ۲ تا ۴ پنل: تکلیف (با آپلود)، تمدید/عذر/ارسال مجدد/لغو، بازخورد و پیام، کتابخوانی، مدیران."""
import http.client, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from urllib.parse import urlparse, parse_qs
from test_flow import ADMIN, STU
from test_panel_edit import start, token, post, row


def mpost(cl, act, tok, fields, files=(), back="/assignments", origin=None):
    b = "----rosh"
    parts = []
    for k, vs in {"_csrf": [tok], "back": [back], **fields}.items():
        for v in (vs if isinstance(vs, list) else [vs]):
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for name, data in files:
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n")
    body = b"".join(parts) + f"--{b}--\r\n".encode()
    c = http.client.HTTPConnection("127.0.0.1", cl.port, timeout=10)
    h = {"Cookie": cl.cookie, "Content-Type": f"multipart/form-data; boundary={b}"}
    if origin:
        h["Origin"] = origin
    c.request("POST", f"/act/{act}", body=body, headers=h)
    r = c.getresponse(); r.read()
    q = parse_qs(urlparse(r.getheader("Location") or "").query)
    return r.status, (q.get("k", [""])[0] == "ok"), q.get("m", [""])[0]


def test_assignment_lifecycle():
    app, bale, cfg, srv, cl = start()
    try:
        tok = token(cl, "/assignments")
        ali = row(app, "SELECT id FROM students ORDER BY id")["id"]
        for p in ("/assignments", "/messages", "/admins", "/books", f"/student/{ali}", "/assignment/1"):
            assert cl.req("GET", p)[0] == 200, p
        # ساخت تکلیف با آپلود و اطلاع‌رسانی
        n0 = len(bale.texts(STU))
        st, ok, msg = mpost(cl, "asg_create", tok, {"title": "علوم — فصل ۳", "desc": "بخوانید", "kind": "required", "target": "all",
                                                   "deadline": "فردا ۲۱:۳۰", "notify": "1"},
                            [("sheet.pdf", b"%PDF-1.4 x"), ("bad.exe", b"MZ"), ("p.png", b"\x89PNG....")])
        assert ok, msg
        a = row(app, "SELECT * FROM assignments WHERE title='علوم — فصل ۳'")
        assert a and a["target_grade"] == 99 and a["target_all"] == 1
        fl = app.conn.execute("SELECT * FROM assignment_files WHERE assignment_id=?", (a["id"],)).fetchall()
        assert len(fl) == 2 and all(os.path.exists(f["path"]) for f in fl) and "bad.exe" in msg
        assert len(bale.texts(STU)) > n0                                          # دانش‌آموز خبردار شد
        aid = a["id"]
        # اعتبارسنجی
        assert not mpost(cl, "asg_create", tok, {"title": "x", "kind": "required", "target": "all", "deadline": "فردا ۲۱:۳۰"})[1]
        assert not mpost(cl, "asg_create", tok, {"title": "تکلیف خوب", "kind": "bonus", "target": "all", "deadline": "فردا ۲۱:۳۰"})[1]   # امتیاز لازم
        assert not mpost(cl, "asg_create", tok, {"title": "تکلیف خوب", "kind": "required", "target": "groups", "deadline": "فردا ۲۱:۳۰"})[1]
        assert not mpost(cl, "asg_create", tok, {"title": "تکلیف خوب", "kind": "required", "target": "all", "deadline": "نامفهوم"})[1]
        # بدون CSRF رد می‌شود
        assert not mpost(cl, "asg_create", "bad", {"title": "تکلیف خوب", "kind": "required", "target": "all", "deadline": "فردا ۲۱:۳۰"})[1]
        assert row(app, "SELECT COUNT(*) c FROM assignments WHERE title='تکلیف خوب'")["c"] == 0
        # ویرایش
        assert post(cl, "asg_edit", tok, aid=aid, title="علوم — فصل ۴", desc="جدید")[2]
        assert row(app, "SELECT title FROM assignments WHERE id=?", aid)["title"] == "علوم — فصل ۴"
        # تمدید همه و یک نفر
        assert post(cl, "asg_extend_all", tok, aid=aid, deadline="پس‌فردا ۲۰:۰۰")[2]
        d1 = row(app, "SELECT deadline_ts FROM assignments WHERE id=?", aid)["deadline_ts"]
        assert post(cl, "asg_extend_one", tok, aid=aid, sid=ali, deadline="امروز ۲۳:۵۰")[2]
        assert row(app, "SELECT 1 FROM student_deadlines WHERE assignment_id=? AND student_id=?", aid, ali)
        assert not post(cl, "asg_extend_one", tok, aid=aid, sid=ali, deadline="؟؟")[2]
        # عذر و ارسال مجدد و یادآوری
        assert post(cl, "asg_excuse", tok, aid=aid, sid=ali, reason="بیمار")[2] and row(app, "SELECT 1 FROM excuses WHERE assignment_id=?", aid)
        assert post(cl, "asg_resubmit", tok, aid=aid, sid=ali, note="کامل‌تر")[2] and row(app, "SELECT open FROM resubmit_requests WHERE assignment_id=?", aid)["open"] == 1
        assert post(cl, "asg_remind", tok, aid=aid)[2]
        # حذف ضمیمه و افزودن ضمیمه
        assert post(cl, "asg_file_del", tok, fid=fl[0]["id"])[2] and not os.path.exists(fl[0]["path"])
        assert mpost(cl, "asg_files", tok, {"aid": aid}, [("n.jpg", b"jpgdata")])[1]
        # لغو و بازگردانی
        assert post(cl, "asg_cancel", tok, aid=aid)[2] and row(app, "SELECT status FROM assignments WHERE id=?", aid)["status"] == "cancelled"
        assert post(cl, "asg_cancel", tok, aid=aid, restore=1)[2] and row(app, "SELECT status FROM assignments WHERE id=?", aid)["status"] == "active"
        # تکلیف امتیازی + گروهی
        gid = row(app, "SELECT id FROM groups LIMIT 1")["id"]
        ok, msg = mpost(cl, "asg_create", tok, {"title": "امتیازی ویژه", "kind": "bonus", "points": "۱۰", "target": "groups", "groups": [str(gid)],
                                                  "deadline": "فردا ۲۱:۳۰"})[1:]
        assert ok, msg
        b = row(app, "SELECT * FROM assignments WHERE title='امتیازی ویژه'")
        assert b["points"] == 10 and b["target_all"] == 0 and row(app, "SELECT 1 FROM assignment_groups WHERE assignment_id=?", b["id"])
        # ثبت در گزارش فعالیت با برچسب
        assert row(app, "SELECT COUNT(*) c FROM audit WHERE details LIKE '%(از پنل)'")["c"] > 5
    finally:
        srv.shutdown()


def test_feedback_broadcast_admins_books():
    app, bale, cfg, srv, cl = start()
    try:
        tok = token(cl, "/messages")
        ali = row(app, "SELECT id FROM students ORDER BY id")["id"]
        n = len(bale.texts(STU))
        assert post(cl, "feedback", tok, sid=ali, aid=1, text="آفرین، ادامه بده")[2]
        assert row(app, "SELECT 1 FROM feedback WHERE text='آفرین، ادامه بده'") and len(bale.texts(STU)) == n + 1
        assert not post(cl, "feedback", tok, sid=ali, aid=0, text="  ")[2]
        f1 = row(app, "SELECT * FROM feedback WHERE text='آفرین، ادامه بده'")
        assert f1["delivered"] == 1 and f1["delivered_ts"] and f1["source"] == "panel"
        # وقتی بله خطا بدهد، دروغ نمی‌گوییم: ثبت می‌شود ولی «نرسیده» می‌ماند و ارسال دوباره ممکن است
        chat = row(app, "SELECT chat_id FROM students WHERE id=?", ali)["chat_id"]
        bale.fail_chats = {chat}
        st_, loc, ok_, msg_ = post(cl, "feedback", tok, sid=ali, aid=0, text="بازخورد دوم")
        assert ok_ and "نرسیده" in msg_
        f2 = row(app, "SELECT * FROM feedback WHERE text='بازخورد دوم'")
        assert f2["delivered"] == 0 and f2["delivered_ts"] is None
        page = cl.req("GET", "/feedback")[2].decode()
        assert "نرسیده" in page and "بازخورد دوم" in page and "ارسال دوباره" in page
        assert not post(cl, "feedback_resend", tok, fid=f2["id"])[2]            # هنوز بله خطا می‌دهد
        bale.fail_chats = set()
        assert post(cl, "feedback_resend", tok, fid=f2["id"])[2]
        assert row(app, "SELECT delivered FROM feedback WHERE id=?", f2["id"])["delivered"] == 1
        assert any("بازخورد دوم" in t for t in bale.texts(STU))
        # تاریخچه‌ی کامل هر دانش‌آموز با تاریخ، در صفحه‌ی خودش
        sp = cl.req("GET", f"/student/{ali}")[2].decode()
        assert 'id="fb"' in sp and "آفرین، ادامه بده" in sp and "بازخورد دوم" in sp
        assert post(cl, "broadcast", tok, target="all", text="سلام به همه")[2]
        assert post(cl, "broadcast", tok, target=f"s{ali}", text="پیام شخصی")[2]
        assert any("پیام شخصی" in t for t in bale.texts(STU))
        assert not post(cl, "broadcast", tok, target="evil'; drop", text="x")[2]
        assert not post(cl, "broadcast", tok, target="g9", text="x")[2]               # گیرنده‌ای ندارد
        # مدیران
        assert post(cl, "admin_add", tok, uid="۵۵۵۵")[2] and row(app, "SELECT 1 FROM admins WHERE user_id=5555")
        assert not post(cl, "admin_add", tok, uid="abc")[2]
        assert not post(cl, "admin_remove", tok, uid=ADMIN)[2]                         # مدیر ثابت / خودش
        assert post(cl, "admin_remove", tok, uid=5555)[2] and not row(app, "SELECT 1 FROM admins WHERE user_id=5555")
        # کتابخوانی
        s9 = app.conn.execute("INSERT INTO students(full_name,code,created_ts,grade) VALUES('نهمی',?, ?,9)", ("zz11", app._t)).lastrowid
        app.conn.execute("INSERT INTO book_reports(student_id,day1_ts,day2_ts,book,from_page,to_page,pages,created_ts) VALUES(?,?,?,?,?,?,?,?)",
                         (s9, app._t - 86400, app._t, "کتاب الف", 1, 10, 10, app._t))
        app.conn.execute("INSERT INTO known_groups VALUES(-100,'گروه نهمی‌ها',?)", (app._t,))
        app.conn.commit()
        rid = row(app, "SELECT id FROM book_reports")["id"]
        assert cl.req("GET", "/books")[0] == 200 and "گروه نهمی‌ها" in cl.req("GET", "/books")[2].decode()
        assert post(cl, "book_edit", tok, rid=rid, book="کتاب ب", from_p="۵", to_p="۲۰")[2]
        r = row(app, "SELECT * FROM book_reports WHERE id=?", rid)
        assert r["book"] == "کتاب ب" and r["pages"] == 16 and r["edited_ts"]
        assert not post(cl, "book_edit", tok, rid=rid, book="کتاب ب", from_p="20", to_p="5")[2]
        assert not post(cl, "book_repost", tok, rid=rid)[2]                            # گروه تنظیم نشده
        assert post(cl, "book_group", tok, chat_id="-100")[2] and row(app, "SELECT value FROM settings WHERE key='book_group_chat_id'")[0] == "-100"
        assert not post(cl, "book_group", tok, chat_id="-999")[2]
        assert post(cl, "book_repost", tok, rid=rid)[2]
        assert post(cl, "book_delete", tok, rid=rid)[2] and row(app, "SELECT status FROM book_reports WHERE id=?", rid)["status"] == "deleted"
    finally:
        srv.shutdown()


def test_origin_null_multipart_and_size_limit():
    app, bale, cfg, srv, cl = start()
    try:
        tok = token(cl, "/assignments")
        ok = mpost(cl, "asg_create", tok, {"title": "با نال", "kind": "required", "target": "g6", "deadline": "فردا ۲۱:۳۰"}, origin="null")[1]
        assert ok
        assert not mpost(cl, "asg_create", tok, {"title": "از بیرون", "kind": "required", "target": "g6", "deadline": "فردا ۲۱:۳۰"}, origin="http://evil.example")[1]
        cfg.max_file_mb = 1
        big = mpost(cl, "asg_create", tok, {"title": "فایل بزرگ", "kind": "required", "target": "g6", "deadline": "فردا ۲۱:۳۰"}, [("big.pdf", b"0" * (2 * 1024 * 1024))])
        assert big[1] and "بزرگ‌تر" in big[2]                                          # تکلیف ساخته می‌شود، فایل رد می‌شود
        assert row(app, "SELECT COUNT(*) c FROM assignment_files WHERE name='big.pdf'")["c"] == 0
    finally:
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
