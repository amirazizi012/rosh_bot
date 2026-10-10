import sys, time, tempfile, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, rules as R

T0 = 1_790_000_000  # یک لحظه‌ی دلخواه
H = 3600


def mk():
    conn = db.connect(tempfile.mktemp(suffix=".db"))
    conn.execute("INSERT INTO students(full_name,code,created_ts) VALUES('علی','111111',?)", (T0 - 100 * H,))
    conn.commit()
    return conn


def add_asg(conn, deadline, kind="required", title="ت"):
    cur = conn.execute("INSERT INTO assignments(title,kind,deadline_ts,grace_min,late_hours,target_all,created_ts) "
                       "VALUES(?,?,?,?,?,1,?)", (title, kind, deadline, 20, 24, T0 - 50 * H))
    conn.commit()
    return conn.execute("SELECT * FROM assignments WHERE id=?", (cur.lastrowid,)).fetchone()


def submit(conn, a, now, sid=1):
    cur = conn.execute("INSERT INTO submissions(assignment_id,student_id,state,created_ts) VALUES(?,?,'draft',?)",
                       (a["id"], sid, now))
    conn.commit()
    return R.finalize(conn, a, sid, cur.lastrowid, now)


def test_verdict_boundaries():
    a = {"grace_min": 20, "late_hours": 24}
    d = T0
    assert R.verdict(a, d, d - 5)[0] == "on_time"
    assert R.verdict(a, d, d)[0] == "on_time"
    assert R.verdict(a, d, d + 20 * 60)[0] == "on_time"          # دقیقاً آخر تاخیر مجاز
    assert R.verdict(a, d, d + 20 * 60 + 1) == ("late", 21)       # ۲۰ دقیقه و ۱ ثانیه → ۲۱ دقیقه
    assert R.verdict(a, d, d + 135 * 60) == ("late", 135)
    assert R.verdict(a, d, d + 24 * H)[0] == "late"
    assert R.verdict(a, d, d + 24 * H + 1)[0] == "closed"


def test_submit_on_time_late_closed():
    conn = mk()
    a = add_asg(conn, T0 + H)
    assert submit(conn, a, T0) == (True, 0, False)
    conn2 = mk(); a2 = add_asg(conn2, T0)
    assert submit(conn2, a2, T0 + 10 * 60)[0] is True            # در تاخیر مجاز
    conn3 = mk(); a3 = add_asg(conn3, T0)
    on, over, _ = submit(conn3, a3, T0 + 135 * 60)
    assert on is False and over == 135
    conn4 = mk(); a4 = add_asg(conn4, T0)
    ok, _ = R.can_submit(conn4, a4, 1, T0 + 25 * H)
    assert not ok


def test_extension_per_student():
    conn = mk(); a = add_asg(conn, T0)
    conn.execute("INSERT INTO student_deadlines VALUES(?,?,?)", (a["id"], 1, T0 + 48 * H)); conn.commit()
    assert submit(conn, a, T0 + 30 * H)[0] is True


def test_replace_before_deadline_only():
    conn = mk(); a = add_asg(conn, T0 + 5 * H)
    submit(conn, a, T0)
    assert R.can_submit(conn, a, 1, T0 + 1)[0]
    assert not R.can_submit(conn, a, 1, T0 + 6 * H)[0]


def test_resubmit_inherits_lateness():
    conn = mk(); a = add_asg(conn, T0)
    on, over, _ = submit(conn, a, T0 + 60 * 60)
    assert on is False
    conn.execute("INSERT INTO resubmit_requests(assignment_id,student_id,note,ts) VALUES(?,?,?,?)", (a["id"], 1, "", T0)); conn.commit()
    assert R.can_submit(conn, a, 1, T0 + 40 * H)[0]               # حتی بعد از بسته‌شدن
    on2, over2, was = submit(conn, a, T0 + 40 * H)
    assert (on2, over2, was) == (False, over, True)
    assert R.open_resubmit(conn, a["id"], 1) is None
    # فقط یک نسخه‌ی final باقی می‌ماند
    assert conn.execute("SELECT COUNT(*) c FROM submissions WHERE state='final'").fetchone()["c"] == 1


def test_streak_rules():
    conn = mk()
    asg = [add_asg(conn, T0 - (30 - i) * H * 2, title=f"ت{i}") for i in range(8)]  # همه گذشته
    # پنج‌تای اول به‌موقع، ششم با تاخیر → شمارنده صفر، نشان نمی‌گیرد
    for i in range(5):
        submit(conn, asg[i], asg[i]["deadline_ts"] - 60)
    submit(conn, asg[5], asg[5]["deadline_ts"] + 30 * 60)
    submit(conn, asg[6], asg[6]["deadline_ts"] - 60)
    blocks, cur = R.streak_state(conn, 1, T0, 6)
    assert (blocks, cur) == (0, 1) or (blocks, cur) == (0, 0)   # هفتم به‌موقع، هشتم ارسال‌نشده
    assert R.streak_state(conn, 1, T0, 6) == (0, 0)             # هشتم (ارسال‌نشده) شمارنده را صفر می‌کند


def test_streak_block_and_excuse():
    conn = mk()
    asg = [add_asg(conn, T0 - (30 - i) * H * 2, title=f"ت{i}") for i in range(7)]
    for i in (0, 1, 2):
        submit(conn, asg[i], asg[i]["deadline_ts"] - 60)
    # چهارم: عذر موجه (نادیده)
    conn.execute("INSERT INTO excuses(assignment_id,student_id,reason,ts) VALUES(?,?,?,?)", (asg[3]["id"], 1, "بیماری", T0)); conn.commit()
    for i in (4, 5, 6):
        submit(conn, asg[i], asg[i]["deadline_ts"] - 60)
    assert R.streak_state(conn, 1, T0, 6) == (1, 0)
    new = R.award_auto(conn, 1, T0, 6)
    assert any("پشتکار" in t for t in new)
    assert R.award_auto(conn, 1, T0, 6) == []                    # تکراری ثبت نمی‌شود


def test_waiting_stops_counting():
    conn = mk()
    a1 = add_asg(conn, T0 - 5 * H); a2 = add_asg(conn, T0 + 5 * H); a3 = add_asg(conn, T0 + 9 * H)
    submit(conn, a1, T0 - 6 * H); submit(conn, a3, T0)           # a2 هنوز نیامده
    assert R.streak_state(conn, 1, T0, 6) == (0, 1)


def test_optional_not_in_streak_and_bonus_badge():
    conn = mk()
    b = add_asg(conn, T0 + H, kind="bonus", title="مسئله‌ی ویژه")
    submit(conn, b, T0)
    new = R.award_auto(conn, 1, T0, 6)
    assert any("ستاره" in t for t in new)
    assert R.streak_state(conn, 1, T0, 6) == (0, 0)


def test_new_student_not_penalized_for_old():
    conn = mk()
    conn.execute("INSERT INTO students(full_name,code,created_ts) VALUES('نو','222222',?)", (T0,)); conn.commit()
    a = add_asg(conn, T0 - 40 * H)                                # خیلی قبل از عضویت بسته شده
    assert R.targets_for_student(conn, 2) == []
    assert len(R.targets_for_student(conn, 1)) == 1


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("✓", k)
