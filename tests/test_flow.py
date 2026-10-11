"""آزمون سرتاسری با بله‌ی جعلی: مدیر تکلیف می‌سازد، دانش‌آموز وارد می‌شود و پاسخ می‌فرستد."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, router, rules as R, scheduler, reports, jalali as J
from app.config import Config
from app.core import App
from app.bale import BaleError

H = 3600
ADMIN, STU = 1000, 2000
_uid = [0]


class FakeBale:
    def __init__(self):
        self.out = []      # (chat, text)
        self.files = []
        self.fail_chats = set()   # چت‌هایی که ارسال به آن‌ها خطا می‌دهد

    def send_message(self, chat_id, text, rows=None):
        if chat_id in self.fail_chats:
            raise BaleError("Forbidden: bot is not a member")
        self.out.append((chat_id, text, rows)); return {"message_id": len(self.out)}

    def edit_text(self, *a, **k):
        raise BaleError("edit unsupported")        # مسیر جایگزین (ارسال پیام تازه) را هم آزمایش می‌کند

    def send_photo(self, chat_id, path, caption=None, rows=None):
        self.files.append((chat_id, str(path))); return {}

    send_document = send_photo

    def answer_callback(self, *a, **k): pass

    def delete_message(self, chat_id, message_id):
        self.deleted = getattr(self, "deleted", []) + [(chat_id, message_id)]

    def download(self, file_id, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"fake-image-bytes")
        return 16

    def texts(self, chat):
        return [t for c, t, _ in self.out if c == chat]


def make_app():
    d = Path(tempfile.mkdtemp())
    cfg = Config(token="x", admin_ids={ADMIN}, data_dir=d)
    bale = FakeBale()
    app = App(cfg, bale, db.connect(d / "t.db"))
    app.clock = lambda: app._t
    app._t = int(J.from_jalali(1405, 7, 16, 12, 0))
    return app, bale


def upd(chat, text=None, photo=False, data=None, doc=None):
    _uid[0] += 1
    if data is not None:
        return {"update_id": _uid[0], "callback_query": {"id": "c", "from": {"id": chat}, "data": data,
                "message": {"chat": {"id": chat}, "message_id": 5}}}
    m = {"chat": {"id": chat, "type": "private"}, "from": {"id": chat}}
    if text is not None: m["text"] = text
    if photo: m["photo"] = [{"file_id": "p1", "file_size": 100}, {"file_id": "p2", "file_size": 200}]
    if doc: m["document"] = doc
    return {"update_id": _uid[0], "message": m}


def go(app, *updates):
    for u in updates:
        router.handle(app, u)


def test_full_flow():
    app, bale = make_app()
    # مدیر: افزودن دانش‌آموز با گروه
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "علی رضایی | گروه الف\nمحمد کریمی"))
    studs = app.conn.execute("SELECT * FROM students ORDER BY id").fetchall()
    assert len(studs) == 2 and studs[0]["code"].isdigit() and len(studs[0]["code"]) == 6
    ali = studs[0]
    # دانش‌آموز: کد اشتباه، سپس درست (با ارقام فارسی)
    go(app, upd(STU, "/start"), upd(STU, "123456"))
    assert any("درست نیست" in t for t in bale.texts(STU))
    from app.fa import fa
    go(app, upd(STU, fa(ali["code"])))
    assert app.student_by_chat(STU)["id"] == ali["id"]
    # مدیر: ساخت تکلیف (مهلت: فردا ۲۱:۳۰)
    go(app, upd(ADMIN, data="a:new"), upd(ADMIN, "ریاضی — صفحه ۴۲"), upd(ADMIN, "حل تمرین‌های ۱ تا ۵"),
       upd(ADMIN, photo=True), upd(ADMIN, data="a:nb"), upd(ADMIN, data="a:nk:required"), upd(ADMIN, data="a:nt:all"),
       upd(ADMIN, "بعدازظهر"), upd(ADMIN, "فردا ۲۱:۳۰"), upd(ADMIN, data="a:npub:1"))
    a = app.conn.execute("SELECT * FROM assignments").fetchone()
    assert a["title"] == "ریاضی — صفحه ۴۲" and a["target_all"] == 1 and a["grace_min"] == 20
    assert app.conn.execute("SELECT COUNT(*) c FROM assignment_files").fetchone()["c"] == 1
    assert any("تکلیف جدید" in t for t in bale.texts(STU))          # اطلاع‌رسانی
    # دانش‌آموز: مشاهده، ارسال با ۲ عکس، نهایی (به‌موقع)
    app._t = a["deadline_ts"] - 5 * H
    go(app, upd(STU, data=f"s:a:{a['id']}"), upd(STU, data=f"s:send:{a['id']}"), upd(STU, photo=True),
       upd(STU, doc={"file_id": "d", "file_name": "answer.pdf", "mime_type": "application/pdf", "file_size": 1000}),
       upd(STU, data="s:fin"))
    sub = R.current_final(app.conn, a["id"], ali["id"])
    assert sub["on_time"] == 1
    assert app.conn.execute("SELECT COUNT(*) c FROM submission_files WHERE submission_id=?", (sub["id"],)).fetchone()["c"] == 2
    assert any("به‌موقع بود" in t for t in bale.texts(STU))
    assert app.conn.execute("SELECT COUNT(*) c FROM badges WHERE student_id=?", (ali["id"],)).fetchone()["c"] >= 1  # اولین قدم


def test_late_and_closed_via_bot():
    app, bale = make_app()
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "علی"))
    ali = app.conn.execute("SELECT * FROM students").fetchone()
    app.conn.execute("UPDATE students SET chat_id=? WHERE id=?", (STU, ali["id"])); app.conn.commit()
    dl = app._t + H
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ت','required',?,20,24,1,?)", (dl, app._t)); app.conn.commit()
    aid = 1
    app._t = dl + 135 * 60
    go(app, upd(STU, data=f"s:send:{aid}"), upd(STU, photo=True), upd(STU, data="s:fin"))
    assert any("۲ ساعت و ۱۵ دقیقه بعد از مهلت" in t for t in bale.texts(STU)), bale.texts(STU)[-3:]
    # بعد از ۲۴ ساعت: بسته
    app.conn.execute("DELETE FROM submissions"); app.conn.commit()
    app._t = dl + 25 * H
    go(app, upd(STU, data=f"s:send:{aid}"))
    assert any("بسته" in t for t in bale.texts(STU)[-2:])


def test_admin_tools_excuse_resubmit_zip_xlsx():
    app, bale = make_app()
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "علی"))
    ali = app.conn.execute("SELECT * FROM students").fetchone()
    app.conn.execute("UPDATE students SET chat_id=? WHERE id=?", (STU, ali["id"])); app.conn.commit()
    dl = app._t + 2 * H
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ت۱','required',?,20,24,1,?)", (dl, app._t))
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ت۲','required',?,20,24,1,?)", (dl, app._t)); app.conn.commit()
    go(app, upd(STU, data="s:send:1"), upd(STU, photo=True), upd(STU, data="s:fin"))
    # عذر موجه برای تکلیف ۲
    go(app, upd(ADMIN, data="a:aexc:2"), upd(ADMIN, data=f"a:aexcs:2:{ali['id']}"), upd(ADMIN, "بیماری"))
    assert R.is_excused(app.conn, 2, ali["id"])
    # درخواست ارسال مجدد
    go(app, upd(ADMIN, data=f"a:arss:1:{ali['id']}"), upd(ADMIN, "عکس خوانا نبود"))
    assert R.open_resubmit(app.conn, 1, ali["id"]) is not None
    assert any("دوباره بفرستی" in t for t in bale.texts(STU))
    # تمدید مهلت برای یک نفر
    go(app, upd(ADMIN, data=f"a:aext1s:2:{ali['id']}"), upd(ADMIN, "پس‌فردا ۱۰:۰۰"))
    assert app.conn.execute("SELECT COUNT(*) c FROM student_deadlines").fetchone()["c"] == 1
    # بازخورد
    go(app, upd(ADMIN, data=f"a:fbs:{ali['id']}:1"), upd(ADMIN, "کارت عالی بود"))
    assert any("کارت عالی بود" in t for t in bale.texts(STU))
    # گزارش‌ها و دانلود
    go(app, upd(ADMIN, data="a:rall"), upd(ADMIN, data=f"a:strep:{ali['id']}"), upd(ADMIN, data="a:azip:1"),
       upd(ADMIN, data="a:rxlsx"), upd(ADMIN, data="a:rrecent"), upd(ADMIN, data="a:bc"), upd(ADMIN, data="a:bct:all"),
       upd(ADMIN, "جلسه فردا برگزار نمی‌شود"), upd(ADMIN, data="a:bcsend"))
    assert any("جلسه فردا" in t for t in bale.texts(STU))
    assert any(f.endswith(".zip") for _, f in bale.files) and any(f.endswith(".xlsx") for _, f in bale.files)


def test_permissions():
    app, bale = make_app()
    go(app, upd(STU, data="a:menu"))
    assert any("مخصوص مدیران" in t for t in bale.texts(STU))


def test_login_lockout():
    app, bale = make_app()
    for _ in range(5):
        go(app, upd(STU, "000000"))
    go(app, upd(STU, "000000"))
    assert any("دقیقه" in t for t in bale.texts(STU)[-2:])


def test_reminder_once():
    app, bale = make_app()
    go(app, upd(ADMIN, "/start"), upd(ADMIN, data="a:sadd:6"), upd(ADMIN, "علی"))
    app.conn.execute("UPDATE students SET chat_id=?", (STU,)); app.conn.commit()
    app.conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) VALUES('ت','required',?,20,24,1,?)", (app._t + 2 * H, app._t)); app.conn.commit()
    scheduler.reminders(app); scheduler.reminders(app)
    assert sum("یادآوری" in t for t in bale.texts(STU)) == 1
    scheduler.daily_backup(app)
    assert list((app.data / "backups").glob("rosh-*.db"))


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
