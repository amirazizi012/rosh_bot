"""آزمون ویرایش از پنل وب (ADR 0009): CSRF، Origin، مدیر بودن، عمل‌ها، اطلاع‌رسانی به دانش‌آموز، ثبت «(از پنل)»."""
import http.client, os, re, sys, threading
from urllib.parse import urlencode, urlparse, parse_qs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app import panel
from test_flow import upd, go, ADMIN, STU
from test_panel import setup, web_code, Client


def start():
    app, bale, cfg = setup()
    srv = panel.make_server(cfg, "127.0.0.1", 0)
    srv._bale = bale                                     # اطلاع‌رسانی به دانش‌آموز با بله‌ی جعلی
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cl = Client(srv.server_address[1])
    assert cl.login(web_code(app, bale))[0] == 303
    return app, bale, cfg, srv, cl


def token(cl, path="/students"):
    html = cl.req("GET", path)[2].decode()
    m = re.search(r'name="_csrf" value="([0-9a-f]{40})"', html)
    assert m, "توکن CSRF در صفحه نیست"
    return m.group(1)


def post(cl, act, tok, back="/students", origin=None, **f):
    data = {"_csrf": tok, "back": back}
    data.update(f)
    body = urlencode(data, doseq=True)
    c = http.client.HTTPConnection("127.0.0.1", cl.port, timeout=10)
    h = {"Cookie": cl.cookie, "Content-Type": "application/x-www-form-urlencoded"}
    if origin:
        h["Origin"] = origin
    c.request("POST", f"/act/{act}", body=body, headers=h)
    r = c.getresponse(); r.read()
    loc = r.getheader("Location") or ""
    q = parse_qs(urlparse(loc).query)
    return r.status, loc, (q.get("k", [""])[0] == "ok"), (q.get("m", [""])[0])


def row(app, sql, *a):
    return app.conn.execute(sql, a).fetchone()


def test_csrf_origin_and_admin_checks():
    app, bale, cfg, srv, cl = start()
    try:
        tok = token(cl)
        n = row(app, "SELECT COUNT(*) c FROM students")["c"]
        # بدون توکن / توکن اشتباه
        for bad in ("", "0" * 40):
            st, loc, ok, msg = post(cl, "students_add", bad, text="نفر جدید", grade="6")
            assert st == 303 and not ok and "معتبر نیست" in msg
        assert row(app, "SELECT COUNT(*) c FROM students")["c"] == n
        # Origin دیگر
        st, loc, ok, msg = post(cl, "students_add", tok, origin="http://evil.example", text="نفر جدید", grade="6")
        assert not ok and row(app, "SELECT COUNT(*) c FROM students")["c"] == n
        # بدون نشست: هدایت به ورود و بدون تغییر
        anon = Client(cl.port)
        c = http.client.HTTPConnection("127.0.0.1", cl.port, timeout=10)
        c.request("POST", "/act/students_add", body=urlencode({"_csrf": tok, "text": "x", "grade": "6"}),
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
        r = c.getresponse(); r.read()
        assert r.status == 303 and r.getheader("Location") == "/login"
        # برگشت به نشانیِ بیرونی (open redirect) ممکن نیست
        st, loc, ok, msg = post(cl, "group_create", tok, back="//evil.example/x", name="گروه ب")
        assert loc.startswith("/?") and "evil" not in loc
        # عمل ناشناخته
        st, *_ = post(cl, "drop_everything", tok)
        assert st == 404
        # مدیر بودن هر بار دوباره بررسی می‌شود
        srv.cfg.admin_ids = set()
        st, loc, ok, msg = post(cl, "group_create", tok, name="گروه ج")
        assert not ok and "دسترسی" in msg and not row(app, "SELECT 1 FROM groups WHERE name='گروه ج'")
    finally:
        srv.shutdown()


def test_students_and_groups_from_panel():
    app, bale, cfg, srv, cl = start()
    try:
        tok = token(cl)
        st, loc, ok, msg = post(cl, "students_add", tok, text="مهدی نهمی | @Mahdi_9 | تقویتی\nرضا هفتمی", grade="9")
        assert ok and "۲ دانش‌آموز" in msg
        m9 = row(app, "SELECT * FROM students WHERE full_name='مهدی نهمی'")
        assert m9["grade"] == 9 and m9["username"] == "mahdi_9" and len(m9["code"]) == 6
        assert row(app, "SELECT g.name FROM groups g JOIN student_groups sg ON sg.group_id=g.id WHERE sg.student_id=?", m9["id"])["name"] == "تقویتی"
        sid = m9["id"]
        # صفحه‌ی دانش‌آموز: فرم مدیریت و پیام موفقیت
        html = cl.req("GET", f"/student/{sid}")[2].decode()
        assert "مدیریت دانش‌آموز" in html and "ذخیره‌ی گروه‌ها" in html
        assert "{{CSRF}}" not in html
        assert post(cl, "student_rename", tok, back=f"/student/{sid}", sid=sid, name="مهدی نهمی‌پور")[2]
        assert row(app, "SELECT full_name FROM students WHERE id=?", sid)["full_name"] == "مهدی نهمی‌پور"
        # یوزرنیم تکراری رد، معتبر قبول، خالی پاک می‌کند
        ali = row(app, "SELECT * FROM students WHERE full_name='علی رضایی'")
        app.conn.execute("UPDATE students SET username='ali_01' WHERE id=?", (ali["id"],)); app.conn.commit()
        ok, msg = post(cl, "student_username", tok, sid=sid, username="@ALI_01")[2:]
        assert not ok and "ثبت شده" in msg
        assert post(cl, "student_username", tok, sid=sid, username="@mahdi_9x")[2]
        assert row(app, "SELECT username FROM students WHERE id=?", sid)["username"] == "mahdi_9x"
        assert post(cl, "student_username", tok, sid=sid, username="")[2] and row(app, "SELECT username FROM students WHERE id=?", sid)["username"] is None
        # فعال/غیرفعال و بازنشانی ورود
        app.conn.execute("UPDATE students SET chat_id=777 WHERE id=?", (sid,)); app.conn.commit()
        assert post(cl, "student_toggle", tok, sid=sid)[2] and row(app, "SELECT active FROM students WHERE id=?", sid)["active"] == 0
        assert post(cl, "student_toggle", tok, sid=sid)[2] and row(app, "SELECT active FROM students WHERE id=?", sid)["active"] == 1
        old = m9["code"]
        assert post(cl, "student_reset", tok, sid=sid)[2]
        r = row(app, "SELECT * FROM students WHERE id=?", sid)
        assert r["chat_id"] is None and r["code"] != old
        # گروه‌ها: ساخت، عضویت از صفحه‌ی دانش‌آموز، اعضا از صفحه‌ی گروه، حذف با تأیید
        assert not post(cl, "group_create", tok, name="")[2]
        assert post(cl, "group_create", tok, back="/groups", name="گروه ب")[2]
        assert not post(cl, "group_create", tok, back="/groups", name="گروه ب")[2]       # تکراری
        gb = row(app, "SELECT id FROM groups WHERE name='گروه ب'")["id"]
        gt = row(app, "SELECT id FROM groups WHERE name='تقویتی'")["id"]
        assert post(cl, "student_groups", tok, sid=sid, groups=[gb])[2]
        assert [r["group_id"] for r in app.conn.execute("SELECT group_id FROM student_groups WHERE student_id=?", (sid,))] == [gb]
        assert post(cl, "group_members", tok, back=f"/group/{gb}", gid=gb, students=[sid, ali["id"], 99999])[2]
        assert {r["student_id"] for r in app.conn.execute("SELECT student_id FROM student_groups WHERE group_id=?", (gb,))} == {sid, ali["id"]}
        assert "گروه ب" in cl.req("GET", "/groups")[2].decode() and "ذخیره‌ی اعضا" in cl.req("GET", f"/group/{gb}")[2].decode()
        assert not post(cl, "group_delete", tok, gid=gb)[2] and row(app, "SELECT 1 FROM groups WHERE id=?", gb)       # بدون تیک تأیید
        assert post(cl, "group_delete", tok, gid=gb, confirm="1")[2]
        assert not row(app, "SELECT 1 FROM groups WHERE id=?", gb) and not row(app, "SELECT 1 FROM student_groups WHERE group_id=?", gb)
        # همه‌ی تغییرها با برچسب «(از پنل)» در گزارش فعالیت
        marked = {r["action"] for r in app.conn.execute("SELECT action FROM audit WHERE details LIKE '%(از پنل)'")}
        assert {"students_add", "group_create", "student_toggle", "student_reset", "group_delete", "username_set"} <= marked, marked
        assert "از پنل" in cl.req("GET", "/audit")[2].decode()
    finally:
        srv.shutdown()


def test_review_points_and_badges_from_panel():
    app, bale, cfg, srv, cl = start()
    try:
        ali = row(app, "SELECT * FROM students WHERE full_name='علی رضایی'")["id"]
        tok = token(cl, f"/student/{ali}")
        # وضعیت پاسخ: ناقص با توضیح ← دانش‌آموز خبردار و اجازه‌ی ارسال مجدد
        assert "ویرایش وضعیت" in cl.req("GET", f"/student/{ali}")[2].decode()
        n = len(bale.texts(STU))
        ok, msg = post(cl, "status", tok, back=f"/student/{ali}", aid=1, sid=ali, code="inc", note="مسئله ۳ ناقص است")[2:]
        assert ok
        assert row(app, "SELECT status, note FROM status_overrides WHERE assignment_id=1 AND student_id=?", ali)["status"] == "incomplete"
        assert row(app, "SELECT open FROM resubmit_requests WHERE assignment_id=1 AND student_id=?", ali)["open"] == 1
        assert any("ناقص" in t and "مسئله ۳" in t for t in bale.texts(STU)[n:])
        assert not post(cl, "status", tok, aid=1, sid=ali, code="zzz")[2]               # وضعیت نامعتبر
        assert not post(cl, "status", tok, aid=999, sid=ali, code="ok")[2]              # تکلیف نامعتبر
        assert post(cl, "status", tok, aid=1, sid=ali, code="auto")[2]                  # برگشت به خودکار
        assert not row(app, "SELECT 1 FROM status_overrides WHERE assignment_id=1 AND student_id=?", ali)
        # امتیاز در انتظار: تأیید، رد، تأیید همه
        from app import rules as R
        for i in (1, 2, 3):
            R.add_points(app.conn, ali, 10, f"تمرین {i}", "bonus", "asg", 50 + i, app._t, "pending")
        ids = [r["id"] for r in app.conn.execute("SELECT id FROM points_ledger ORDER BY id")]
        html = cl.req("GET", "/points")[2].decode()
        assert "تأیید همه" in html and html.count('action="/act/item_ok"') == 3
        n = len(bale.texts(STU))
        assert post(cl, "item_ok", tok, back="/points", kind="points", id=ids[0])[2]
        assert row(app, "SELECT status FROM points_ledger WHERE id=?", ids[0])["status"] == "approved"
        assert any("امتیاز" in t and "تأیید شد" in t for t in bale.texts(STU)[n:])
        assert not post(cl, "item_ok", tok, kind="points", id=ids[0])[2]               # دوباره: دیگر در انتظار نیست
        assert post(cl, "item_no", tok, kind="points", id=ids[1])[2]
        assert row(app, "SELECT status FROM points_ledger WHERE id=?", ids[1])["status"] == "rejected"
        assert post(cl, "items_all", tok, back="/points")[2]
        assert row(app, "SELECT status FROM points_ledger WHERE id=?", ids[2])["status"] == "approved"
        # تغییر دستی امتیاز
        assert not post(cl, "points_adjust", tok, sid=ali, delta="0", reason="x")[2]
        assert not post(cl, "points_adjust", tok, sid=ali, delta="abc", reason="x")[2]
        ok, msg = post(cl, "points_adjust", tok, sid=ali, delta="+5", reason="مشارکت خوب")[2:]
        assert ok and R.points_total(app.conn, ali)[0] == 25
        assert post(cl, "points_adjust", tok, sid=ali, delta="-3", reason="")[2] and R.points_total(app.conn, ali)[0] == 22
        # نشان در انتظار: رد = حذف و مسدود؛ حذف نشان دیگر
        R.give_badge(app.conn, ali, "streak", "1", "🏅 پشتکار ۱", app._t)
        app.conn.execute("UPDATE badges SET status='pending' WHERE code='streak'"); app.conn.commit()
        bid = row(app, "SELECT id FROM badges WHERE code='streak'")["id"]
        assert post(cl, "item_no", tok, kind="badge", id=bid)[2]
        assert not row(app, "SELECT 1 FROM badges WHERE id=?", bid) and row(app, "SELECT 1 FROM badge_blocks WHERE student_id=? AND code='streak'", ali)
        R.give_badge(app.conn, ali, "manual", "k", "🎖 ویژه", app._t)
        b2 = row(app, "SELECT id FROM badges WHERE code='manual'")["id"]
        assert post(cl, "badge_delete", tok, sid=ali, bid=b2)[2] and not row(app, "SELECT 1 FROM badges WHERE id=?", b2)
        # دانش‌آموز بدون نشان/امتیاز (هفتم): تغییر امتیاز رد می‌شود
        post(cl, "students_add", tok, text="هفتمی نمونه", grade="7")
        s7 = row(app, "SELECT id FROM students WHERE full_name='هفتمی نمونه'")["id"]
        ok, msg = post(cl, "points_adjust", tok, sid=s7, delta="5", reason="x")[2:]
        assert not ok and "نشان و امتیاز" in msg
        # صفحه‌ی ششمی هنوز درست باز می‌شود
        assert cl.req("GET", f"/student/{ali}")[0] == 200 and cl.req("GET", "/points")[0] == 200
        # GET هیچ‌وقت چیزی را تغییر نمی‌دهد
        before = row(app, "SELECT COUNT(*) c FROM audit")["c"]
        cl.req("GET", "/act/items_all"); cl.req("GET", "/students?m=x")
        assert row(app, "SELECT COUNT(*) c FROM audit")["c"] == before
    finally:
        srv.shutdown()


def test_flash_message_is_escaped():
    app, bale, cfg, srv, cl = start()
    try:
        st, r, body = cl.req("GET", "/students?m=%3Cscript%3Ealert(1)%3C/script%3E&k=err")
        t = body.decode()
        assert "<script>alert" not in t and "&lt;script&gt;" in t and 'class="flash err"' in t
    finally:
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
