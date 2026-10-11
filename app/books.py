"""باشگاه کتابخوانی پایه‌ی نهم: ثبت گزارش مطالعه، ارسال خودکار به گروه بله، و بخش مدیریت.

قالب پیام گروه (مقدارها پررنگ؛ طبق مستندات بله «*متن*» با فاصله پیش و پس از ستاره‌ها):
    نام: *...*
    گزارش روز: *دوشنبه و سه‌شنبه ۱۳ و ۱۴ مهر*
    نام کتاب: *...*
    از صفحه *۴۵۱* تا صفحه *۴۷۰* *(۲۰ صفحه)*
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from . import jalali as J
from .bale import btn
from .core import App, Ctx
from .fa import clean, en, fa

log = logging.getLogger("rosh")
DAY = 86400
BOOK_MENU = [[btn("📖 ثبت گزارش مطالعه", "b:new")], [btn("🗂 گزارش‌های من", "b:mine")]]
BACK = [[btn("⬅ منوی اصلی", "s:home")]]


# ---------- ابزارهای متن و تاریخ ----------
def md_safe(s) -> str:
    """نویسه‌هایی که بله به‌عنوان قالب‌بندی می‌خواند از متن کاربر حذف می‌شود تا پیام به‌هم نریزد."""
    return clean(clean(s).translate(str.maketrans({"*": "", "_": " ", "`": "'", "[": "(", "]": ")", "\n": " ", "\r": " "})))


noon = J.noon


def pair_label(d1: int, d2: int) -> str:
    """«دوشنبه و سه‌شنبه ۱۳ و ۱۴ مهر» (اگر ماه فرق کند: «... ۳۰ مهر و ۱ آبان»)"""
    j1, j2 = J.jdate(d1), J.jdate(d2)
    w1, w2 = J.weekday_name(d1), J.weekday_name(d2)
    if j1[:2] == j2[:2]:
        return fa(f"{w1} و {w2} {j1[2]} و {j2[2]} {J.MONTHS[j1[1] - 1]}")
    return fa(f"{w1} و {w2} {j1[2]} {J.MONTHS[j1[1] - 1]} و {j2[2]} {J.MONTHS[j2[1] - 1]}")


def report_text(name, d1, d2, book, a, b) -> str:
    return (f"نام: *{md_safe(name)}*\n"
            f"گزارش روز: *{pair_label(d1, d2)}*\n"
            f"نام کتاب: *{md_safe(book)}*\n"
            f"از صفحه *{fa(a)}* تا صفحه *{fa(b)}* *({fa(b - a + 1)} صفحه)*")


def recent_pairs(now: int, n: int = 6):
    today = noon(now)
    return [(today - i * DAY - DAY, today - i * DAY) for i in range(n)]


def _int(text, lo=1, hi=99999):
    t = en(clean(text)).replace(",", "").replace("٬", "")
    return int(t) if t.isdigit() and lo <= int(t) <= hi else None


def prev_books(conn, sid, n=3):
    seen, out = set(), []
    for r in conn.execute("SELECT book FROM book_reports WHERE student_id=? AND status='active' ORDER BY id DESC LIMIT 20", (sid,)):
        k = clean(r["book"]).replace(" ", "")
        if k not in seen:
            seen.add(k)
            out.append(r["book"])
        if len(out) == n:
            break
    return out


def has_report(conn, sid, d1) -> bool:
    return conn.execute("SELECT 1 FROM book_reports WHERE student_id=? AND day1_ts=? AND status='active'", (sid, d1)).fetchone() is not None


# ---------- ارسال به گروه ----------
def group_id(app: App):
    v = app.get_setting("book_group_chat_id")
    return int(v) if v and re.fullmatch(r"-?\d+", v) else None


def post_report(app: App, rid: int, prefix: str = "") -> bool:
    gid = group_id(app)
    r = app.conn.execute("SELECT b.*, s.full_name FROM book_reports b JOIN students s ON s.id=b.student_id WHERE b.id=?", (rid,)).fetchone()
    if not gid or not r:
        return False
    text = prefix + report_text(r["full_name"], r["day1_ts"], r["day2_ts"], r["book"], r["from_page"], r["to_page"])
    ok = app.send(gid, text) is not None
    if ok:
        app.conn.execute("UPDATE book_reports SET posted=1 WHERE id=?", (rid,))
        app.conn.commit()
    return ok


def record_group(app: App, chat_id: int, title: str):
    r = app.conn.execute("SELECT title, last_seen_ts FROM known_groups WHERE chat_id=?", (chat_id,)).fetchone()
    if r and r["title"] == (title or "") and app.now() - r["last_seen_ts"] < 3600:
        return  # گروه شلوغ باشد، برای هر پیام در دیتابیس نمی‌نویسیم
    app.conn.execute("INSERT INTO known_groups(chat_id,title,last_seen_ts) VALUES(?,?,?) "
                     "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, last_seen_ts=excluded.last_seen_ts",
                     (chat_id, title or "", app.now()))
    app.conn.commit()


# ---------- پایه‌ی نهم: ثبت گزارش ----------
def start(app: App, ctx: Ctx, st):
    app.clear_state(ctx.chat_id)
    rows = [[btn(pair_label(d1, d2), f"b:d:{i}")] for i, (d1, d2) in enumerate(recent_pairs(app.now()))]
    rows.append([btn("📅 تاریخ دلخواه", "b:dx")])
    rows.append([btn("⬅ منوی اصلی", "s:home")])
    app.show(ctx, "📖 گزارش مطالعه برای کدام «دو روز» است؟", rows)


def _choose_pair(app, ctx, st, d1, d2):
    if has_report(app.conn, st["id"], d1):
        app.send(ctx.chat_id, "برای این دو روز قبلاً گزارش ثبت کرده‌ای. اگر اشتباهی شده، از مدیر بخواه اصلاحش کند.", BACK)
        return
    app.set_state(ctx.chat_id, "b:book", {"d1": d1, "d2": d2})
    rows = [[btn(f"📕 {b}"[:50], f"b:pb:{i}")] for i, b in enumerate(prev_books(app.conn, st["id"]))]
    rows.append([btn("❌ لغو", "b:cancel")])
    app.send(ctx.chat_id, f"روز گزارش: {pair_label(d1, d2)}\n\n📕 نام کتاب را بنویس" +
             ("؛ یا یکی از کتاب‌های قبلی را بزن:" if len(rows) > 1 else ":"), rows)


def _ask_from(app, ctx, data):
    app.set_state(ctx.chat_id, "b:from", data)
    app.send(ctx.chat_id, "از صفحه‌ی چند؟ (فقط عدد)", [[btn("❌ لغو", "b:cancel")]])


def _preview(app, ctx, st, data):
    app.set_state(ctx.chat_id, "b:confirm", data)
    app.send(ctx.chat_id, "🔎 پیش‌نمایش گزارش:\n\n" + report_text(st["full_name"], data["d1"], data["d2"], data["book"], data["from"], data["to"]),
             [[btn("✅ ثبت نهایی", "b:ok")], [btn("✏ شروع دوباره", "b:new"), btn("❌ لغو", "b:cancel")]])


def on_callback(app: App, ctx: Ctx, st, parts):
    c = parts[1] if len(parts) > 1 else ""
    state, data = app.get_state(ctx.chat_id)
    if c == "new":
        start(app, ctx, st)
    elif c == "d":
        i = int(parts[2])
        pairs = recent_pairs(app.now())
        if 0 <= i < len(pairs):
            _choose_pair(app, ctx, st, *pairs[i])
    elif c == "dx":
        app.set_state(ctx.chat_id, "b:date", {})
        app.send(ctx.chat_id, "تاریخ «روز اول» را بنویس؛ روز دوم خودکار روز بعدش است.\nمثال: ۱۴۰۵/۰۷/۱۳", [[btn("❌ لغو", "b:cancel")]])
    elif c == "pb" and state == "b:book":
        books = prev_books(app.conn, st["id"])
        i = int(parts[2])
        if 0 <= i < len(books):
            data["book"] = books[i]
            _ask_from(app, ctx, data)
    elif c == "ok":
        finish(app, ctx, st)
    elif c == "cancel":
        app.clear_state(ctx.chat_id)
        app.show(ctx, "لغو شد.", BOOK_MENU)
    elif c == "mine":
        mine(app, ctx, st)


def on_message(app: App, ctx: Ctx, st, msg):
    state, data = app.get_state(ctx.chat_id)
    text = clean(msg.get("text") or "")
    cap = app.cfg
    if state == "b:date":
        d1 = J.parse_date(text)
        today = noon(app.now())
        if d1 is None:
            app.send(ctx.chat_id, "تاریخ را نفهمیدم. مثال: ۱۴۰۵/۰۷/۱۳")
        elif d1 + DAY > today:
            app.send(ctx.chat_id, "روز دوم نباید در آینده باشد. تاریخ زودتری بنویس.")
        elif d1 < today - cap.book_max_days_back * DAY:
            app.send(ctx.chat_id, f"بیش از {fa(cap.book_max_days_back)} روز گذشته را نمی‌شود ثبت کرد. با مدیر صحبت کن.")
        else:
            _choose_pair(app, ctx, st, noon(d1), noon(d1) + DAY)
    elif state == "b:book":
        if not (2 <= len(text) <= 80):
            app.send(ctx.chat_id, "نام کتاب را بنویس (۲ تا ۸۰ حرف).")
            return
        data["book"] = text
        _ask_from(app, ctx, data)
    elif state == "b:from":
        v = _int(text)
        if v is None:
            app.send(ctx.chat_id, "فقط یک عدد بنویس (مثلاً ۴۵۱).")
            return
        data["from"] = v
        app.set_state(ctx.chat_id, "b:to", data)
        app.send(ctx.chat_id, "تا صفحه‌ی چند؟ (فقط عدد)", [[btn("❌ لغو", "b:cancel")]])
    elif state == "b:to":
        v = _int(text)
        if v is None:
            app.send(ctx.chat_id, "فقط یک عدد بنویس (مثلاً ۴۷۰).")
        elif v < data["from"]:
            app.send(ctx.chat_id, "«تا صفحه» نباید کمتر از «از صفحه» باشد. دوباره بنویس.")
        elif v - data["from"] + 1 > cap.book_max_pages:
            app.send(ctx.chat_id, f"در دو روز بیشتر از {fa(cap.book_max_pages)} صفحه ثبت نمی‌شود. اگر درست است، با مدیر هماهنگ کن.")
        else:
            data["to"] = v
            _preview(app, ctx, st, data)
    else:
        home(app, ctx, st)


def home(app: App, ctx: Ctx, st):
    app.show(ctx, f"سلام {st['full_name']} 👋\nباشگاه کتابخوانی رشد", BOOK_MENU)


def finish(app: App, ctx: Ctx, st):
    state, d = app.get_state(ctx.chat_id)
    if state != "b:confirm":
        app.send(ctx.chat_id, "گزارشی برای ثبت نیست.", BOOK_MENU)
        return
    if has_report(app.conn, st["id"], d["d1"]):
        app.clear_state(ctx.chat_id)
        app.send(ctx.chat_id, "این گزارش قبلاً ثبت شده است.", BOOK_MENU)
        return
    cur = app.conn.execute(
        "INSERT INTO book_reports(student_id,day1_ts,day2_ts,book,from_page,to_page,pages,created_ts) VALUES(?,?,?,?,?,?,?,?)",
        (st["id"], d["d1"], d["d2"], clean(d["book"]), d["from"], d["to"], d["to"] - d["from"] + 1, app.now()))
    app.conn.commit()
    app.clear_state(ctx.chat_id)
    rid = cur.lastrowid
    posted = post_report(app, rid)
    app.send(ctx.chat_id, "✅ گزارشت ثبت شد. آفرین، ادامه بده! 📚" + ("\nدر گروه هم ارسال شد." if posted else ""), BOOK_MENU)
    if not posted:
        for aid in app.admin_ids():
            app.send(aid, "⚠️ گزارش کتابخوانی ثبت شد ولی در گروه ارسال نشد (گروه تنظیم نشده یا بات در گروه نیست).\n"
                          "پنل مدیریت ← باشگاه کتابخوانی ← «انتخاب گروه»", [[btn("📖 باشگاه کتابخوانی", "a:book")]])


def mine(app: App, ctx: Ctx, st):
    rows = app.conn.execute("SELECT * FROM book_reports WHERE student_id=? AND status='active' ORDER BY day2_ts DESC, id DESC LIMIT 10", (st["id"],)).fetchall()
    tot = app.conn.execute("SELECT COUNT(*) n, COALESCE(SUM(pages),0) p FROM book_reports WHERE student_id=? AND status='active'", (st["id"],)).fetchone()
    if not rows:
        app.show(ctx, "هنوز گزارشی ثبت نکرده‌ای.", BOOK_MENU)
        return
    lines = [f"🗂 گزارش‌های تو — مجموع: {fa(tot['n'])} گزارش، {fa(tot['p'])} صفحه", ""]
    for r in rows:
        lines.append(f"📕 {r['book']} — {pair_label(r['day1_ts'], r['day2_ts'])} — {fa(r['pages'])} صفحه")
    app.show(ctx, "\n".join(lines), BOOK_MENU)


# ====================== بخش مدیر ======================
from . import reports  # noqa: E402
from .bale import BaleError  # noqa: E402

A_BACK = [[btn("⬅ باشگاه کتابخوانی", "a:book")]]


def a_menu(app: App, ctx: Ctx):
    gid = group_id(app)
    title = ""
    if gid:
        r = app.conn.execute("SELECT title FROM known_groups WHERE chat_id=?", (gid,)).fetchone()
        title = f" ({r['title']})" if r and r["title"] else ""
    unposted = app.conn.execute("SELECT COUNT(*) c FROM book_reports WHERE status='active' AND posted=0").fetchone()["c"]
    text = ("📖 باشگاه کتابخوانی (پایه‌ی نهم)\n\n"
            f"گروه گزارش‌ها: {'✅ تنظیم شده' + title if gid else '❌ هنوز تنظیم نشده'}\n"
            f"گزارش‌های ارسال‌نشده به گروه: {fa(unposted)}")
    rows = [[btn("📊 گزارش کلی", "a:book:sum"), btn("🆕 آخرین گزارش‌ها", "a:book:recent")],
            [btn("📗 اکسل کامل", "a:book:xlsx"), btn("✏ ویرایش/حذف گزارش", "a:book:list:0")],
            [btn("👥 انتخاب گروه نهمی‌ها", "a:book:grp"), btn("🔁 ارسال مجدد به گروه", "a:book:retry")],
            [btn("⬅ پنل مدیریت", "a:menu")]]
    app.show(ctx, text, rows)


def a_group_pick(app: App, ctx: Ctx):
    gs = app.conn.execute("SELECT * FROM known_groups ORDER BY last_seen_ts DESC LIMIT 10").fetchall()
    text = ("👥 انتخاب گروه نهمی‌ها\n\n۱) بات را به گروه نهمی‌ها اضافه کن.\n"
            "۲) داخل همان گروه یک مدیر دستور /setgroup را بفرستد؛ یا همین‌جا گروه را از فهرست انتخاب کنید.\n\n")
    rows = [[btn(f"👥 {g['title'] or g['chat_id']}"[:50], f"a:book:gs:{g['chat_id']}")] for g in gs]
    text += "گروه‌هایی که بات دیده است:" if gs else "هنوز گروهی دیده نشده؛ بعد از اضافه‌کردن بات یک پیام در گروه بفرستید و دوباره بزنید."
    rows.append([btn("🔄 تازه‌سازی", "a:book:grp")])
    rows.append([btn("⬅ باشگاه کتابخوانی", "a:book")])
    app.show(ctx, text, rows)


def set_group(app: App, chat_id: int) -> bool:
    app.set_setting("book_group_chat_id", chat_id)
    return app.send(chat_id, "✅ این گروه برای دریافت گزارش‌های «باشگاه کتابخوانی رشد» تنظیم شد. 📚") is not None


def _report_line(r) -> str:
    return f"{r['full_name']} — {r['book']} — {fa(r['pages'])} صفحه — {J.fmt_short(r['day2_ts']).split(' ')[0]}"


def a_list(app: App, ctx: Ctx, offset: int, sid=None):
    q = "SELECT b.*, s.full_name FROM book_reports b JOIN students s ON s.id=b.student_id WHERE b.status='active'"
    args = []
    if sid:
        q += " AND b.student_id=?"
        args.append(sid)
    rows_db = app.conn.execute(q + " ORDER BY b.day2_ts DESC, b.id DESC LIMIT 8 OFFSET ?", args + [offset]).fetchall()
    if not rows_db:
        app.show(ctx, "گزارشی نیست.", A_BACK)
        return
    rows = [[btn(_report_line(r)[:60], f"a:book:r:{r['id']}")] for r in rows_db]
    if len(rows_db) == 8:
        rows.append([btn("قدیمی‌تر ▶", f"a:book:list:{offset + 8}")])
    if offset:
        rows.append([btn("◀ جدیدتر", f"a:book:list:{max(0, offset - 8)}")])
    rows += A_BACK
    app.show(ctx, "کدام گزارش؟", rows)


def a_view(app: App, ctx: Ctx, rid: int):
    r = app.conn.execute("SELECT b.*, s.full_name FROM book_reports b JOIN students s ON s.id=b.student_id WHERE b.id=?", (rid,)).fetchone()
    if not r or r["status"] != "active":
        app.show(ctx, "گزارش پیدا نشد.", A_BACK)
        return
    text = (report_text(r["full_name"], r["day1_ts"], r["day2_ts"], r["book"], r["from_page"], r["to_page"]) +
            f"\n\nزمان ثبت: {J.fmt(r['created_ts'])}\nارسال به گروه: {'✅' if r['posted'] else '❌'}" +
            (f"\nآخرین ویرایش مدیر: {J.fmt_short(r['edited_ts'])}" if r["edited_ts"] else ""))
    app.show(ctx, text, [[btn("✏ نام کتاب", f"a:book:eb:{rid}"), btn("✏ صفحه‌ها", f"a:book:ep:{rid}")],
                         [btn("📤 ارسال دوباره به گروه", f"a:book:rp:{rid}"), btn("🗑 حذف", f"a:book:del:{rid}")],
                         [btn("⬅ فهرست", "a:book:list:0")]])


def st_edit_book(app, ctx, msg, text, data):
    if not (2 <= len(text) <= 80):
        app.send(ctx.chat_id, "نام کتاب را بنویس (۲ تا ۸۰ حرف).")
        return
    app.conn.execute("UPDATE book_reports SET book=?, edited_ts=? WHERE id=?", (text, app.now(), data["id"]))
    app.conn.commit()
    app.audit(ctx.user_id, "book_edit", f"{data['id']}:book")
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, "✅ نام کتاب ویرایش شد (در گروه پیام اصلاحیه نمی‌رود؛ اگر لازم است «ارسال دوباره به گروه» را بزن).",
             [[btn("⬅ گزارش", f"a:book:r:{data['id']}")]])


def st_edit_pages(app, ctx, msg, text, data):
    nums = re.findall(r"\d+", en(text))
    if len(nums) != 2:
        app.send(ctx.chat_id, "دو عدد بنویس؛ مثلاً: ۴۵۱ ۴۷۰")
        return
    a, b = int(nums[0]), int(nums[1])
    if a < 1 or b < a or b - a + 1 > max(app.cfg.book_max_pages * 3, 900):
        app.send(ctx.chat_id, "اعداد معتبر نیست (تا صفحه نباید کمتر از از صفحه باشد).")
        return
    app.conn.execute("UPDATE book_reports SET from_page=?, to_page=?, pages=?, edited_ts=? WHERE id=?", (a, b, b - a + 1, app.now(), data["id"]))
    app.conn.commit()
    app.audit(ctx.user_id, "book_edit", f"{data['id']}:pages")
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, f"✅ صفحه‌ها ویرایش شد: {fa(a)} تا {fa(b)} ({fa(b - a + 1)} صفحه).", [[btn("⬅ گزارش", f"a:book:r:{data['id']}")]])


def admin_callback(app: App, ctx: Ctx, arg):
    c = arg[0] if arg else "menu"
    i = lambda k: int(arg[k])  # noqa: E731
    if c == "menu":
        app.clear_state(ctx.chat_id)
        a_menu(app, ctx)
    elif c == "sum":
        app.send_long(ctx.chat_id, reports.book_summary_text(app.conn, app.now()), A_BACK)
    elif c == "recent":
        rows = app.conn.execute("SELECT b.*, s.full_name FROM book_reports b JOIN students s ON s.id=b.student_id "
                                "WHERE b.status='active' ORDER BY b.id DESC LIMIT 15").fetchall()
        app.send_long(ctx.chat_id, "🆕 آخرین گزارش‌ها\n\n" + ("\n".join("• " + _report_line(r) for r in rows) or "هنوز گزارشی نیست."), A_BACK)
    elif c == "xlsx":
        app.send(ctx.chat_id, "⏳ در حال ساخت اکسل...")
        p = reports.build_books_xlsx(app, app.data / "exports" / f"books_{app.now()}.xlsx")
        try:
            app.bale.send_document(ctx.chat_id, p, f"📗 گزارش باشگاه کتابخوانی — {J.fmt_short(app.now())}")
        except BaleError as e:
            app.send(ctx.chat_id, f"ارسال اکسل ناموفق بود ({e}).")
        for old in sorted((app.data / "exports").glob("books_*.xlsx"))[:-5]:
            old.unlink(missing_ok=True)
    elif c == "list":
        a_list(app, ctx, i(1))
    elif c == "st":
        a_list(app, ctx, 0, sid=i(1))
    elif c == "r":
        a_view(app, ctx, i(1))
    elif c == "eb":
        app.set_state(ctx.chat_id, "a:bke", {"id": i(1)})
        app.send(ctx.chat_id, "نام جدید کتاب را بنویس:")
    elif c == "ep":
        app.set_state(ctx.chat_id, "a:bkp", {"id": i(1)})
        app.send(ctx.chat_id, "صفحه‌ی شروع و پایان را بنویس؛ مثلاً: ۴۵۱ ۴۷۰")
    elif c == "rp":
        r = app.conn.execute("SELECT edited_ts FROM book_reports WHERE id=?", (i(1),)).fetchone()
        ok = post_report(app, i(1), "✏ گزارش اصلاح‌شده\n" if r and r["edited_ts"] else "")
        app.show(ctx, "✅ در گروه ارسال شد." if ok else "⚠️ ارسال نشد؛ گروه تنظیم نشده یا بات در گروه نیست.",
                 [[btn("⬅ گزارش", f"a:book:r:{i(1)}")]])
    elif c == "del":
        app.show(ctx, "این گزارش حذف شود؟ (از آمار هم خارج می‌شود؛ پیام گروه پاک نمی‌شود)",
                 [[btn("✅ بله، حذف شود", f"a:book:dely:{i(1)}"), btn("↩ انصراف", f"a:book:r:{i(1)}")]])
    elif c == "dely":
        app.conn.execute("UPDATE book_reports SET status='deleted', edited_ts=? WHERE id=?", (app.now(), i(1)))
        app.conn.commit()
        app.audit(ctx.user_id, "book_delete", str(i(1)))
        a_list(app, ctx, 0)
    elif c == "grp":
        a_group_pick(app, ctx)
    elif c == "gs":
        ok = set_group(app, i(1))
        app.audit(ctx.user_id, "book_group_set", str(i(1)))
        app.show(ctx, "✅ گروه تنظیم شد و پیام آزمایشی ارسال شد." if ok else
                 "⚠️ گروه ذخیره شد، اما ارسال پیام آزمایشی ناموفق بود؛ مطمئن شوید بات در گروه عضو است.", A_BACK)
    elif c == "retry":
        n = ok = 0
        for r in app.conn.execute("SELECT id FROM book_reports WHERE status='active' AND posted=0 ORDER BY id").fetchall():
            n += 1
            ok += 1 if post_report(app, r["id"]) else 0
        app.show(ctx, f"🔁 {fa(ok)} از {fa(n)} گزارش ارسال شد.", A_BACK)
