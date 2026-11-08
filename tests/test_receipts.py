"""آزمون رسید واریزی: دانش‌آموز می‌فرستد، مدیر در بات و پنل می‌بیند و «دریافت شد» می‌زند."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from test_flow import upd, go, ADMIN, STU
from test_panel import setup
from test_panel_edit import start, token, post, row


def cbs(bale):
    return [b["callback_data"] for r in bale.out[-1][2] for b in r] if bale.out[-1][2] else []


def test_student_sends_receipt_and_admin_handles_it():
    app, bale, cfg = setup()
    go(app, upd(STU, "/start"))
    assert any(b["callback_data"] == "s:rcpt" for r in bale.out[-1][2] for b in r)         # دکمه کنار بقیه
    go(app, upd(STU, data="s:rcpt"))
    assert app.get_state(STU)[0] == "s:rcpt"
    go(app, upd(STU, "؟"))                                                               # متن خیلی کوتاه ← هنوز منتظر
    assert app.get_state(STU)[0] == "s:rcpt"
    n_admin = len(bale.texts(ADMIN))
    go(app, upd(STU, photo=True))
    r = row(app, "SELECT * FROM receipts")
    assert r and r["status"] == "new" and os.path.exists(r["path"]) and app.get_state(STU)[0] == ""
    assert any("رسیدت دریافت شد" in t for t in bale.texts(STU))
    assert len(bale.texts(ADMIN)) > n_admin and any("رسید تازه" in t for t in bale.texts(ADMIN))
    # مدیر: منو شمارنده دارد ← فهرست ← دیدن ← دریافت شد
    go(app, upd(ADMIN, "/menu"))
    assert any("رسیدها (۱)" in b["text"] for r_ in bale.out[-1][2] for b in r_)
    go(app, upd(ADMIN, data="a:rcp:0"))
    assert f"a:rcv:{r['id']}" in cbs(bale)
    go(app, upd(ADMIN, data=f"a:rcv:{r['id']}"))
    assert f"a:rco:{r['id']}" in cbs(bale)
    n_stu = len(bale.texts(STU))
    go(app, upd(ADMIN, data=f"a:rco:{r['id']}"))
    assert row(app, "SELECT status FROM receipts")["status"] == "seen" and len(bale.texts(STU)) == n_stu + 1
    assert row(app, "SELECT COUNT(*) c FROM audit WHERE action='receipt_seen'")["c"] == 1
    # فقط مدیر به بخش مدیر دسترسی دارد
    n = len(bale.out)
    go(app, upd(STU, data="a:rcp:0"))
    assert "مخصوص مدیران" in bale.texts(STU)[-1]
    # رسید فقط متنی هم قبول است (شماره‌ی پیگیری) و مدیر آن را می‌بیند
    go(app, upd(STU, data="s:rcpt"), upd(STU, "شماره پیگیری ۱۲۳۴۵۶ مبلغ ۵۰۰ هزار تومان"))
    t = row(app, "SELECT * FROM receipts WHERE path=''")
    assert t and "۱۲۳۴۵۶" in t["note"] and t["status"] == "new" and app.get_state(STU)[0] == ""
    go(app, upd(ADMIN, data=f"a:rcv:{t['id']}"))
    assert any("رسید متنی" in x for x in bale.texts(ADMIN)) and any("۱۲۳۴۵۶" in x for x in bale.texts(ADMIN))
    ali = row(app, "SELECT id FROM students ORDER BY id")["id"]
    go(app, upd(ADMIN, data=f"a:rcp:0:{ali}"))
    assert f"a:rcv:{t['id']}" in cbs(bale) and any(b["callback_data"] == f"a:st:{ali}" for r_ in bale.out[-1][2] for b in r_)
    go(app, upd(ADMIN, data=f"a:st:{ali}"))
    assert any(b["callback_data"] == f"a:rcp:0:{ali}" for r_ in bale.out[-1][2] for b in r_)
    # /start وسط ارسال رسید آن را لغو می‌کند
    go(app, upd(STU, data="s:rcpt"), upd(STU, "/start"))
    assert app.get_state(STU)[0] == ""


def test_panel_receipts_page():
    app, bale, cfg, srv, cl = start()
    try:
        go(app, upd(STU, data="s:rcpt"), upd(STU, photo=True))
        rid = row(app, "SELECT id FROM receipts")["id"]
        st, _, body = cl.req("GET", "/receipts")
        assert st == 200 and f"/rfile/{rid}" in body.decode() and "بررسی‌نشده" in body.decode()
        assert cl.req("GET", f"/rfile/{rid}")[0] == 200
        assert cl.req("GET", "/rfile/999")[0] == 404
        ali = row(app, "SELECT id FROM students ORDER BY id")["id"]
        assert "رسیدهای واریزی" in cl.req("GET", f"/student/{ali}")[2].decode()          # در صفحه‌ی دانش‌آموز هم دیده می‌شود
        go(app, upd(STU, data="s:rcpt"), upd(STU, "پیگیری ۹۸۷۶۵۴"))
        assert "رسید متنی" in cl.req("GET", "/receipts")[2].decode()
        tok = token(cl, "/receipts")
        n = len(bale.texts(STU))
        assert post(cl, "receipt_seen", tok, back="/receipts", rid=rid)[2]
        assert row(app, "SELECT status FROM receipts")["status"] == "seen" and len(bale.texts(STU)) == n + 1
        assert not post(cl, "receipt_seen", tok, back="/receipts", rid=999)[2]
    finally:
        srv.shutdown()


def test_broadcast_with_files_bot_and_panel():
    from test_panel_phase2 import mpost
    app, bale, cfg = setup()
    go(app, upd(STU, "/start"))
    # --- بات: فایل، بعد متن، پیش‌نمایش، ارسال
    go(app, upd(ADMIN, data="a:bct:all"), upd(ADMIN, photo=True))
    assert app.get_state(ADMIN)[0] == "a:bct" and len(app.get_state(ADMIN)[1]["files"]) == 1
    paths = list(app.get_state(ADMIN)[1]["files"])
    go(app, upd(ADMIN, "درس امروز را ببینید"))
    assert app.get_state(ADMIN)[0] == "a:bcconfirm" and "1 فایل" in bale.texts(ADMIN)[-1].translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    go(app, upd(ADMIN, data="a:bcmore"), upd(ADMIN, doc={"file_name": "a.pdf", "file_id": "d1", "file_size": 10}), upd(ADMIN, data="a:bcgo"))
    assert len(app.get_state(ADMIN)[1]["files"]) == 2 and app.get_state(ADMIN)[0] == "a:bcconfirm"
    go(app, upd(ADMIN, doc={"file_name": "x.exe", "file_id": "d2", "file_size": 10}))       # در حالت تایید، فایل جدید نمی‌پذیرد
    go(app, upd(ADMIN, data="a:bcmore"), upd(ADMIN, doc={"file_name": "x.exe", "file_id": "d2", "file_size": 10}))
    assert "نوع فایل" in bale.texts(ADMIN)[-1] and len(app.get_state(ADMIN)[1]["files"]) == 2
    nf, nt = len(bale.files), len(bale.texts(STU))
    go(app, upd(ADMIN, data="a:bcgo"), upd(ADMIN, data="a:bcsend"))
    assert len(bale.files) == nf + 2 and len(bale.texts(STU)) == nt + 1 and "درس امروز" in bale.texts(STU)[-1]
    assert not any(os.path.exists(x) for x in paths)                                         # فایل موقت پاک شد
    # فقط فایل، بدون متن: توضیح فایل به‌عنوان متن
    go(app, upd(ADMIN, data="a:bct:all"), upd(ADMIN, photo=True), upd(ADMIN, data="a:bccancel"))
    assert app.get_state(ADMIN)[0] == ""
    # --- پنل
    app2, bale2, cfg2, srv, cl = start()
    try:
        go(app2, upd(STU, "/start"))
        tok = token(cl, "/messages")
        n = len(bale2.files)
        st_, ok_, msg_ = mpost(cl, "broadcast", tok, {"target": "all", "text": ""}, [("w.pdf", b"%PDF"), ("bad.exe", b"MZ")], back="/messages")
        assert ok_ and "bad.exe" in msg_ and len(bale2.files) == n + 1                        # بدون متن هم قبول، فایل بد رد شد
        assert not mpost(cl, "broadcast", tok, {"target": "all", "text": ""}, [], back="/messages")[1]
        assert not mpost(cl, "broadcast", tok, {"target": "all", "text": ""}, [("bad.exe", b"MZ")], back="/messages")[1]
        assert mpost(cl, "broadcast", tok, {"target": "all", "text": "سلام"}, [("p.png", b"\x89PNG")], back="/messages")[1]
        assert not any(True for _ in (app2.data / "broadcasts").glob("*/*"))                  # چیزی روی دیسک نمانده
    finally:
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
