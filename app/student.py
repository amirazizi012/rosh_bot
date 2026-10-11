"""بخش دانش‌آموز: ورود با کد، دیدن تکالیف، ارسال پاسخ، پیشرفت و نشان‌ها."""
from __future__ import annotations

import logging
from pathlib import Path

from . import jalali as J
from . import rules as R
from .bale import BaleError, btn
from .core import App, Ctx
from .fa import clean, duration, en, fa

log = logging.getLogger("rosh")

MENU = [[btn("📚 تکالیف باز", "s:open"), btn("✅ ارسال‌های من", "s:done")],
        [btn("🏅 نشان‌ها و پیشرفت", "s:prog"), btn("💬 بازخوردها", "s:fb")]]
BACK = [[btn("⬅ منوی اصلی", "s:home")]]
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}


# ---------- ورود ----------
def ask_code(app: App, ctx: Ctx):
    app.set_state(ctx.chat_id, "s:code", {})
    logo = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
    welcome = ("به بات تکالیف «مجموعه تربیتی، آموزشی رشد» خوش آمدی 🌱\n\n"
               "برای ورود، «کد ۶ رقمی شخصی‌ات» را بفرست.\n"
               "کد را نداری؟ از مدیر مجموعه بگیر.")
    if logo.exists():
        try:
            app.bale.send_photo(ctx.chat_id, logo, welcome)
            return
        except BaleError:
            pass
    app.send(ctx.chat_id, welcome)


def on_code(app: App, ctx: Ctx, text: str):
    _, data = app.get_state(ctx.chat_id)
    now = app.now()
    if data.get("lock_until", 0) > now:
        app.send(ctx.chat_id, f"چند بار کد اشتباه فرستادی. {duration((data['lock_until'] - now) // 60 + 1)} دیگر دوباره امتحان کن.")
        return
    code = en(clean(text)).replace(" ", "")
    st = app.conn.execute("SELECT * FROM students WHERE code=? AND active=1", (code,)).fetchone() if code.isdigit() else None
    if not st:
        fails = data.get("fails", 0) + 1
        if fails >= 5:
            app.set_state(ctx.chat_id, "s:code", {"fails": 0, "lock_until": now + 600})
            app.send(ctx.chat_id, "کد پنج بار اشتباه بود؛ ۱۰ دقیقه بعد دوباره امتحان کن. اگر کدت را گم کرده‌ای از مدیر بپرس.")
        else:
            app.set_state(ctx.chat_id, "s:code", {"fails": fails})
            app.send(ctx.chat_id, "این کد درست نیست. دوباره بفرست (ارقام فارسی یا انگلیسی مشکلی ندارد).")
        return
    if st["chat_id"] and st["chat_id"] != ctx.chat_id:
        app.send(ctx.chat_id, "این کد قبلاً روی حساب دیگری فعال شده است. اگر اشتباهی شده به مدیر بگو تا کد جدید بدهد.")
        return
    app.conn.execute("UPDATE students SET chat_id=?, joined_ts=? WHERE id=?", (ctx.chat_id, now, st["id"]))
    app.conn.commit()
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, f"خوش آمدی {st['full_name']} 🎉\nاز اینجا تکالیف را می‌بینی و پاسخ‌هایت را می‌فرستی.")
    home(app, ctx, st)


def home(app: App, ctx: Ctx, st):
    if st["grade"] == 9:
        from . import books
        books.home(app, ctx, st)
        return
    app.show(ctx, f"سلام {st['full_name']} 👋\nچه کاری می‌خواهی انجام بدهی؟", MENU)


# ---------- لیست‌ها ----------
def list_open(app: App, ctx: Ctx, st):
    now, rows = app.now(), []
    for a in R.targets_for_student(app.conn, st["id"]):
        s = R.student_status(app.conn, a, st["id"], now)
        req = R.open_resubmit(app.conn, a["id"], st["id"])
        if s["code"] in ("excused", "missed") or (s["sub"] and not req):
            continue
        icon = "🔁" if req else ("⚠️" if s["code"] == "overdue" else R.KIND_ICON[a["kind"]])
        dl = R.effective_deadline(app.conn, a, st["id"])
        rows.append([btn(f"{icon} {a['title']} — {J.fmt_short(dl)}"[:60], f"s:a:{a['id']}")])
    if not rows:
        app.show(ctx, "الان تکلیف بازی نداری 🎉", BACK)
        return
    app.show(ctx, "📚 تکالیف باز (نزدیک‌ترین مهلت اول):", rows[:25] + BACK)


def list_done(app: App, ctx: Ctx, st):
    now, lines = app.now(), []
    for a in reversed(R.targets_for_student(app.conn, st["id"])):
        s = R.student_status(app.conn, a, st["id"], now)
        if s["sub"]:
            mark = "✅" if s["code"] == "on_time" else f"⏰ ({duration(s['over'])} تاخیر)"
            lines.append(f"{mark} {a['title']} — {J.fmt_short(s['sub']['submitted_ts'])}")
        elif s["code"] == "excused":
            lines.append(f"🙏 {a['title']} — عذر موجه")
    text = "✅ ارسال‌های تو:\n\n" + "\n".join(lines[:40]) if lines else "هنوز چیزی ارسال نکرده‌ای."
    app.show(ctx, text, BACK)


def progress(app: App, ctx: Ctx, st):
    now, n = app.now(), app.cfg.streak_size
    t = R.student_stats(app.conn, st["id"], now, n)
    bd = app.conn.execute("SELECT title FROM badges WHERE student_id=? ORDER BY awarded_ts", (st["id"],)).fetchall()
    bar = "🟩" * t["current"] + "⬜" * max(0, n - t["current"])
    lines = ["🏅 پیشرفت تو", "",
             f"تکالیف الزامی: ✅ {fa(t['on_time'])} به‌موقع | ⏰ {fa(t['late'])} با تاخیر | ❌ {fa(t['missed'])} ارسال‌نشده",
             "", f"مسیر نشان بعدی: {fa(t['current'])} از {fa(n)}", bar,
             f"(هر {fa(n)} تکلیف الزامی پشت‌سرهم و به‌موقع = یک نشان. یک تاخیر یا ارسال‌نشدن، شمارش را از صفر شروع می‌کند.)",
             "", f"⭐ امتیاز تو: {fa(t['points'])}" + (f"  (در انتظار تأیید مدیر: {fa(t['points_pending'])})" if t["points_pending"] else ""),
             f"(هر {fa(app.cfg.extra_streak_size)} تکلیف اختیاری/امتیازی پشت‌سرهم و به‌موقع = یک نشان کوشا با {fa(app.cfg.extra_streak_points)} امتیاز)",
             "", "نشان‌های تو:"]
    lines += [f"• {b['title']}" for b in bd] or ["هنوز نشانی نگرفته‌ای؛ اولین‌ش نزدیک است 💪"]
    app.show(ctx, "\n".join(lines), BACK)


def feedbacks(app: App, ctx: Ctx, st):
    rows = app.conn.execute("SELECT f.*, a.title FROM feedback f LEFT JOIN assignments a ON a.id=f.assignment_id "
                            "WHERE f.student_id=? ORDER BY f.ts DESC LIMIT 10", (st["id"],)).fetchall()
    if not rows:
        app.show(ctx, "هنوز بازخوردی ثبت نشده است.", BACK)
        return
    parts = []
    for r in rows:
        head = f"💬 {J.fmt_short(r['ts'])}" + (f" — {r['title']}" if r["title"] else "")
        parts.append(f"{head}\n{r['text']}")
    app.show(ctx, "\n\n".join(parts), BACK)


# ---------- نمایش و ارسال تکلیف ----------
def view_assignment(app: App, ctx: Ctx, st, aid: int):
    a = app.assignment(aid)
    if not a or a["status"] != "active" or not R.is_target(app.conn, a, st["id"]):
        app.send(ctx.chat_id, "این تکلیف پیدا نشد.", BACK)
        return
    now = app.now()
    s = R.student_status(app.conn, a, st["id"], now)
    dl = R.effective_deadline(app.conn, a, st["id"])
    for f in app.conn.execute("SELECT * FROM assignment_files WHERE assignment_id=? ORDER BY id", (aid,)):
        app.send_file(ctx.chat_id, f["path"])
    closes = f"\n(آخرین زمان ارسال با تاخیر: {J.fmt(dl + a['late_hours'] * 3600)})" if s["code"] == "overdue" else ""
    lines = [f"{R.KIND_ICON[a['kind']]} {a['title']}", f"نوع: {R.KIND_LABEL[a['kind']]}" +
             (f" | ⭐ {fa(a['points'])} امتیاز (بعد از تأیید مدیر)" if a["kind"] == "bonus" and a["points"] else "")]
    if a["description"]:
        lines += ["", a["description"]]
    lines += ["", f"⏰ مهلت: {J.fmt(dl)}"]
    if s["code"] == "waiting":
        lines.append(f"باقی‌مانده: {duration((dl - now) // 60)}")
    lines += [f"تاخیر مجاز: {fa(a['grace_min'])} دقیقه", "", R.describe_for_student(s, closes)]
    ok, _ = R.can_submit(app.conn, a, st["id"], now)
    rows = []
    if ok:
        label = "📤 ارسال پاسخ" if not s["sub"] else "🔁 ارسال پاسخ جدید"
        rows.append([btn(label, f"s:send:{aid}")])
    rows.append([btn("⬅ تکالیف باز", "s:open")])
    app.send(ctx.chat_id, "\n".join(lines), rows)


def start_upload(app: App, ctx: Ctx, st, aid: int):
    a = app.assignment(aid)
    if not a or not R.is_target(app.conn, a, st["id"]):
        return
    ok, why = R.can_submit(app.conn, a, st["id"], app.now())
    if not ok:
        app.send(ctx.chat_id, f"⛔ {why}", BACK)
        return
    _discard_drafts(app, aid, st["id"])
    cur = app.conn.execute("INSERT INTO submissions(assignment_id,student_id,state,created_ts) VALUES(?,?,'draft',?)",
                           (aid, st["id"], app.now()))
    app.conn.commit()
    app.set_state(ctx.chat_id, "s:upload", {"aid": aid, "draft": cur.lastrowid})
    app.send(ctx.chat_id,
             f"📤 پاسخ «{a['title']}» را بفرست.\n\n"
             "• عکس یا PDF؛ چند فایل هم می‌شود.\n"
             "• برای کیفیت بهتر، عکس را «به‌صورت فایل» بفرست (آیکون ✚ ← فایل).\n"
             "• وقتی همه‌ی فایل‌ها را فرستادی، «ارسال نهایی» را بزن؛ زمان ثبت از همان لحظه حساب می‌شود.",
             [[btn("✅ ارسال نهایی", "s:fin"), btn("❌ لغو", "s:cancel")]])


def _discard_drafts(app: App, aid, sid):
    for d in app.conn.execute("SELECT id FROM submissions WHERE assignment_id=? AND student_id=? AND state='draft'",
                              (aid, sid)).fetchall():
        for f in app.conn.execute("SELECT path FROM submission_files WHERE submission_id=?", (d["id"],)):
            Path(f["path"]).unlink(missing_ok=True)
        app.conn.execute("DELETE FROM submission_files WHERE submission_id=?", (d["id"],))
        app.conn.execute("DELETE FROM submissions WHERE id=?", (d["id"],))
    app.conn.commit()


def _extract(msg):
    """(file_id, نام، پسوند، اندازه) یا None"""
    if msg.get("photo"):
        p = msg["photo"][-1]
        return p.get("file_id"), "photo.jpg", ".jpg", p.get("file_size") or 0
    d = msg.get("document")
    if d:
        name = d.get("file_name") or "file"
        ext = Path(name).suffix.lower()
        mime = (d.get("mime_type") or "").lower()
        if not ext:
            ext = ".pdf" if mime == "application/pdf" else (".jpg" if mime.startswith("image/") else "")
        return d.get("file_id"), name, ext, d.get("file_size") or 0
    return None


def on_upload_message(app: App, ctx: Ctx, st, msg, data):
    got = _extract(msg)
    controls = [[btn("✅ ارسال نهایی", "s:fin"), btn("❌ لغو", "s:cancel")]]
    if not got:
        app.send(ctx.chat_id, "لطفاً «عکس» یا «فایل PDF» بفرست. وقتی تمام شد «ارسال نهایی» را بزن.", controls)
        return
    file_id, name, ext, size = got
    if ext not in ALLOWED_EXT:
        app.send(ctx.chat_id, "فقط عکس (jpg، png، webp، heic) یا فایل PDF قبول است.", controls)
        return
    if size and size > app.cfg.max_file_mb * 1024 * 1024:
        app.send(ctx.chat_id, f"حجم فایل بیشتر از {fa(app.cfg.max_file_mb)} مگابایت است. کوچک‌ترش کن و دوباره بفرست.", controls)
        return
    count = app.conn.execute("SELECT COUNT(*) c FROM submission_files WHERE submission_id=?", (data["draft"],)).fetchone()["c"]
    if count >= app.cfg.max_files_per_submission:
        app.send(ctx.chat_id, f"حداکثر {fa(app.cfg.max_files_per_submission)} فایل در هر ارسال مجاز است. «ارسال نهایی» را بزن.", controls)
        return
    dest = app.data / "submissions" / str(data["aid"]) / str(st["id"]) / f"{data['draft']}_{count + 1}{ext}"
    try:
        real = app.bale.download(file_id, dest)
    except BaleError as e:
        log.warning("دانلود فایل ناموفق: %s", e)
        app.send(ctx.chat_id, "دریافت فایل ناموفق بود. دوباره بفرست.", controls)
        return
    if real > app.cfg.max_file_mb * 1024 * 1024:
        dest.unlink(missing_ok=True)
        app.send(ctx.chat_id, f"حجم فایل بیشتر از {fa(app.cfg.max_file_mb)} مگابایت است. کوچک‌ترش کن و دوباره بفرست.", controls)
        return
    app.conn.execute("INSERT INTO submission_files(submission_id,path,name,size) VALUES(?,?,?,?)",
                     (data["draft"], str(dest), name, real))
    app.conn.commit()
    app.send(ctx.chat_id, f"✅ فایل {fa(count + 1)} ذخیره شد. فایل دیگری هست؟ بفرست؛ وگرنه «ارسال نهایی» را بزن.", controls)


def finish(app: App, ctx: Ctx, st):
    state, data = app.get_state(ctx.chat_id)
    if state != "s:upload":
        app.send(ctx.chat_id, "ارسال فعالی نداری. از «تکالیف باز» یک تکلیف را انتخاب کن.", MENU)
        return
    a = app.assignment(data["aid"])
    n = app.conn.execute("SELECT COUNT(*) c FROM submission_files WHERE submission_id=?", (data["draft"],)).fetchone()["c"]
    if n == 0:
        app.send(ctx.chat_id, "هنوز فایلی نفرستاده‌ای. اول عکس یا PDF پاسخ را بفرست.",
                 [[btn("❌ لغو", "s:cancel")]])
        return
    now = app.now()
    try:
        on_time, over, was_req = R.finalize(app.conn, a, st["id"], data["draft"], now)
    except ValueError:
        app.clear_state(ctx.chat_id)
        _discard_drafts(app, a["id"], st["id"])
        app.send(ctx.chat_id, "⛔ مهلت ارسال این تکلیف همین الان بسته شد. اگر دلیل موجهی داری با مدیر صحبت کن.", MENU)
        return
    app.clear_state(ctx.chat_id)
    if was_req:
        head = "🔁 پاسخ جدیدت جایگزین پاسخ قبلی شد."
    elif on_time and over == 0:
        head = "✅ پاسخت ثبت شد و به‌موقع بود. آفرین! 👏"
    elif on_time:
        head = "✅ پاسخت ثبت شد. چند دقیقه از مهلت گذشته بود، اما در «تاخیر مجاز» بود و به‌موقع حساب شد."
    else:
        head = f"⏰ پاسخت ثبت شد، اما {duration(over)} بعد از مهلت بود و با تاخیر ثبت شد."
    app.send(ctx.chat_id, f"{head}\n\n📎 تعداد فایل: {fa(n)}\n🕒 زمان ثبت: {J.fmt(now)}")
    new = app.award(st["id"])
    for t in new:
        app.send(ctx.chat_id, f"🎉 نشان تازه گرفتی!\n{t}")
    if a["kind"] == "bonus" and a["points"]:
        app.send(ctx.chat_id, f"⭐ این تکلیف امتیازی است؛ {fa(a['points'])} امتیاز بعد از تأیید مدیر به تو داده می‌شود.")
    home(app, ctx, st)


def cancel(app: App, ctx: Ctx, st):
    state, data = app.get_state(ctx.chat_id)
    if state == "s:upload":
        _discard_drafts(app, data["aid"], st["id"])
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, "ارسال لغو شد.", MENU)


# ---------- مسیریابی ----------
def on_callback(app: App, ctx: Ctx, st, parts):
    cmd = parts[1]
    if cmd == "home":
        app.clear_state(ctx.chat_id)
        home(app, ctx, st)
    elif cmd == "open":
        list_open(app, ctx, st)
    elif cmd == "done":
        list_done(app, ctx, st)
    elif cmd == "prog":
        progress(app, ctx, st)
    elif cmd == "fb":
        feedbacks(app, ctx, st)
    elif cmd == "a":
        view_assignment(app, ctx, st, int(parts[2]))
    elif cmd == "send":
        start_upload(app, ctx, st, int(parts[2]))
    elif cmd == "fin":
        finish(app, ctx, st)
    elif cmd == "cancel":
        cancel(app, ctx, st)


def on_message(app: App, ctx: Ctx, st, msg):
    state, data = app.get_state(ctx.chat_id)
    if state == "s:upload":
        on_upload_message(app, ctx, st, msg, data)
    else:
        home(app, ctx, st)
