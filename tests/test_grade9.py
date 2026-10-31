"""آزمون پایه‌ی نهم: تکلیف (بدون نشان و امتیاز) کنار باشگاه کتابخوانی؛ تمرین بیشتر؛ تأخیر ۴ روزه."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from app import rules as R, reports, panel_ui as UI
from test_flow import upd, go, ADMIN
from test_grade7 import mk, sid, add_asg, submit_db, S6, S7, S9, H, D


def labels(bale, i=-1):
    return [b["text"] for row in (bale.out[i][2] or []) for b in row]


def test_grade9_menu_has_homework_and_book_club():
    app, bale = mk()
    go(app, upd(S9, "/start"))
    ls = labels(bale)
    assert any("تکالیف باز" in l for l in ls) and any("باشگاه کتابخوانی" in l for l in ls)
    assert not any("نشان" in l for l in ls)          # نهمی نشان ندارد
    go(app, upd(S9, data="b:home"))
    assert any("ثبت گزارش" in l for l in labels(bale)) and any("منوی اصلی" in l for l in labels(bale))
    go(app, upd(S9, data="s:home"))
    assert any("تکالیف باز" in l for l in labels(bale))


def test_targeting_includes_grade9_only_when_chosen():
    app, bale = mk()
    s6, s7, s9 = sid(app, "علی ششمی"), sid(app, "رضا هفتمی"), sid(app, "نیما نهمی")
    ids = lambda a: sorted(s["id"] for s in R.target_students(app.conn, a))
    only9 = add_asg(app, "فقط نهم", target_grade=9)
    allg = add_asg(app, "همه", target_grade=R.TARGET_ALL)
    legacy = add_asg(app, "قدیمی", target_grade=0)          # ششم و هفتم (تکالیف قبلی)
    assert ids(only9) == [s9] and ids(allg) == sorted([s6, s7, s9]) and ids(legacy) == [s6, s7]
    assert [a["title"] for a in R.targets_for_student(app.conn, s9)] == ["فقط نهم", "همه"]
    # مسیر مدیر: دکمه‌ی «فقط نهم»
    go(app, upd(ADMIN, data="a:new"), upd(ADMIN, "جبر"), upd(ADMIN, "x"), upd(ADMIN, data="a:nb"), upd(ADMIN, data="a:nk:required"))
    assert "فقط نهم" in labels(bale)
    go(app, upd(ADMIN, data="a:nt:g9"), upd(ADMIN, "فردا ۲۱:۳۰"))
    assert "همه‌ی پایه‌ی نهم" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, data="a:npub:1"))
    a = app.conn.execute("SELECT * FROM assignments ORDER BY id DESC").fetchone()
    assert (a["target_all"], a["target_grade"]) == (1, 9) and ids(a) == [s9]
    assert any("جبر" in t for t in bale.texts(S9)) and not any("جبر" in t for t in bale.texts(S6))


def test_grade9_submit_and_no_badges_or_points():
    app, bale = mk()
    s9 = sid(app, "نیما نهمی")
    for i in range(7):
        a = add_asg(app, f"ت{i}", dl=app._t - (10 - i) * D, target_grade=9)
        submit_db(app, a, s9, a["deadline_ts"] - H)
    b = add_asg(app, "امتیازی", kind="bonus", dl=app._t - D, target_grade=9, points=10)
    submit_db(app, b, s9, b["deadline_ts"] - H)
    R.award_auto(app.conn, s9, app._t, 6, 5, 10, 0)
    assert app.conn.execute("SELECT COUNT(*) FROM badges WHERE student_id=?", (s9,)).fetchone()[0] == 0
    assert app.conn.execute("SELECT COUNT(*) FROM points_ledger WHERE student_id=?", (s9,)).fetchone()[0] == 0
    # ارسال واقعی از بات (نهمی در حالت s:upload نباید به کتابخوانی برود)
    c = add_asg(app, "ارسالی", dl=app._t + 3 * H, target_grade=9)
    go(app, upd(S9, data=f"s:send:{c['id']}"), upd(S9, photo=True), upd(S9, data="s:fin"))
    assert R.current_final(app.conn, c["id"], s9) is not None
    # کتابخوانی هنوز کار می‌کند
    go(app, upd(S9, data="b:new"))
    assert "گزارش مطالعه" in bale.out[-1][1]
    # گزارش و پنل: هم تکلیف هم کتابخوانی، بدون نشان
    rep = reports.student_report(app, s9)
    assert "تکالیف الزامی" in rep and "امتیاز تأییدشده" not in rep
    pg = UI.student_page(app.conn, app.cfg, app._t, s9)
    assert "تکالیف" in pg and "باشگاه کتابخوانی" in pg and "مسیر نشان بعدی" not in pg


def test_more_practice_label():
    assert R.KIND_LABEL["optional"] == "تمرین بیشتر"
    app, bale = mk()
    go(app, upd(ADMIN, data="a:new"), upd(ADMIN, "ت"), upd(ADMIN, "x"), upd(ADMIN, data="a:nb"))
    assert any("تمرین بیشتر" in l for l in labels(bale)) and not any("اختیاری" in l for l in labels(bale))


def test_late_window_is_four_days():
    app, bale = mk()
    assert app.cfg.late_window_hours == 96
    go(app, upd(ADMIN, data="a:new"), upd(ADMIN, "ت"), upd(ADMIN, "x"), upd(ADMIN, data="a:nb"), upd(ADMIN, data="a:nk:required"),
       upd(ADMIN, data="a:nt:all"), upd(ADMIN, "فردا ۲۱:۳۰"))
    assert "۹۶ ساعت" in bale.texts(ADMIN)[-1]
    go(app, upd(ADMIN, data="a:npub:0"))
    a = app.conn.execute("SELECT * FROM assignments ORDER BY id DESC").fetchone()
    assert a["late_hours"] == 96
    s9 = sid(app, "نیما نهمی")
    ok, _ = R.can_submit(app.conn, a, s9, a["deadline_ts"] + 90 * H)     # روز چهارم: هنوز مجاز
    assert ok
    ok, _ = R.can_submit(app.conn, a, s9, a["deadline_ts"] + 97 * H)     # بعد از ۴ روز: بسته
    assert not ok


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
