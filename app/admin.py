"""پنل مدیر: تکلیف، دانش‌آموز، گروه، گزارش، بازخورد، پیام همگانی، نشان و مدیران.
مدیران به همه‌ی بخش‌ها دسترسی کامل دارند؛ فقط برای ردگیری اشتباه‌ها هر کار در جدول audit ثبت می‌شود."""
from __future__ import annotations

import logging
import secrets
import shutil
import time
from pathlib import Path

from . import books, points
from . import jalali as J
from . import reports
from . import rules as R
from .bale import BaleError, btn
from .core import App, Ctx
from .fa import clean, duration, en, fa
from .student import _extract

log = logging.getLogger("rosh")

MENU = [[btn("📝 تکلیف جدید", "a:new"), btn("📚 تکالیف", "a:alist:0")],
        [btn("👥 دانش‌آموزان", "a:slist:0"), btn("🗂 گروه‌ها", "a:glist")],
        [btn("📊 گزارش‌ها", "a:rep"), btn("📢 پیام همگانی", "a:bc")],
        [btn("⭐ تأیید امتیازها", "a:pts:0"), btn("📖 باشگاه کتابخوانی (نهم)", "a:book")],
        [btn("🏅 نشان دستی", "a:badge"), btn("⚙ مدیران", "a:adm")],
        [btn("🌐 ورود به پنل وب (فقط‌خواندنی)", "a:web")]]
HOME = [[btn("⬅ پنل مدیریت", "a:menu")]]
PAGE = 8
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


# ---------- ابزارهای مشترک ----------
def menu(app: App, ctx: Ctx):
    app.show(ctx, "پنل مدیریت «رشد» 🌱\nیکی را انتخاب کن:\n(برای لغو هر مرحله /menu را بفرست)", MENU)


def student_buttons(studs, prefix):
    rows, row = [], []
    for s in studs:
        row.append(btn(s["full_name"][:28], f"{prefix}:{s['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def tell(app: App, sid, text, rows=None):
    s = app.student(sid)
    if s and s["chat_id"]:
        app.send(s["chat_id"], text, rows)
        return True
    return False


def notify_new_badges(app: App, sid, titles):
    for t in titles:
        tell(app, sid, f"🎉 نشان تازه گرفتی!\n{t}")


def open_btn(aid):
    return [[btn("📖 باز کردن تکلیف", f"s:a:{aid}")]]


def notify_assignment(app: App, aid: int) -> int:
    a = app.assignment(aid)
    n = 0
    for s in R.target_students(app.conn, a):
        if s["chat_id"]:
            if app.send(s["chat_id"], f"📌 تکلیف جدید ({R.KIND_LABEL[a['kind']]})\n{a['title']}\n"
                                      f"⏰ مهلت: {J.fmt(a['deadline_ts'])}", open_btn(aid)):
                n += 1
            time.sleep(0.03)
    return n


def target_text(app: App, a) -> str:
    if a["target_all"]:
        return "همه‌ی دانش‌آموزان"
    names = [r["name"] for r in app.conn.execute(
        "SELECT g.name FROM groups g JOIN assignment_groups ag ON ag.group_id=g.id WHERE ag.assignment_id=?", (a["id"],))]
    return "گروه: " + "، ".join(names) if names else "گروه (بدون عضو)"


def group_rows_toggle(app: App, selected, prefix, done_cb):
    rows = []
    for g in app.conn.execute("SELECT * FROM groups ORDER BY name"):
        mark = "✅" if g["id"] in selected else "⬜"
        rows.append([btn(f"{mark} {g['name']}", f"{prefix}:{g['id']}")])
    rows.append([btn("✔ تأیید", done_cb)])
    return rows


# ---------- تکلیف جدید ----------
def new_start(app: App, ctx: Ctx):
    app.set_state(ctx.chat_id, "a:ntitle", {})
    app.send(ctx.chat_id, "📝 عنوان تکلیف را بنویس\n(مثلاً: «ریاضی — صفحه‌ی ۴۲ تا ۴۵»)")


def st_ntitle(app, ctx, msg, text, data):
    if not text:
        app.send(ctx.chat_id, "عنوان را به‌صورت متن بنویس.")
        return
    app.set_state(ctx.chat_id, "a:nbody", {"title": text, "desc": [], "files": []})
    app.send(ctx.chat_id,
             "حالا «متن تکلیف» و «عکس‌ها یا فایل‌ها» را بفرست (چند پیام هم می‌شود).\n"
             "وقتی تمام شد «ادامه» را بزن. اگر چیزی برای افزودن نداری، همین الان «ادامه» را بزن.",
             [[btn("➡ ادامه", "a:nb")]])


def st_nbody(app, ctx, msg, text, data):
    got = _extract(msg)
    if got:
        file_id, name, ext, size = got
        ext = ext or ".bin"
        dest = app.data / "tmp" / f"{ctx.chat_id}_{app.now()}_{len(data['files']) + 1}{ext}"
        try:
            app.bale.download(file_id, dest)
        except BaleError as e:
            log.warning("دانلود فایل تکلیف ناموفق: %s", e)
            app.send(ctx.chat_id, "دریافت فایل ناموفق بود؛ دوباره بفرست.")
            return
        data["files"].append({"path": str(dest), "kind": "photo" if ext in IMG_EXT else "document", "name": name})
        cap = (msg.get("caption") or "").strip()
        if cap:
            data["desc"].append(cap)
        note = f"✅ فایل {fa(len(data['files']))} ذخیره شد."
    elif (msg.get("text") or "").strip():
        data["desc"].append(msg["text"].strip())
        note = "✅ متن ذخیره شد."
    else:
        return
    app.set_state(ctx.chat_id, "a:nbody", data)
    app.send(ctx.chat_id, note + " موارد بیشتر را بفرست یا «ادامه» را بزن.", [[btn("➡ ادامه", "a:nb")]])


def new_kind(app, ctx):
    app.show(ctx, "نوع تکلیف چیست؟\n"
                  "• الزامی: در شمارنده‌ی نشان پشتکار حساب می‌شود\n"
                  "• اختیاری و امتیازی: جدا از شمارنده‌اند و نشان جدا دارند",
             [[btn("📘 الزامی", "a:nk:required")], [btn("🧩 اختیاری", "a:nk:optional"), btn("⭐ امتیازی", "a:nk:bonus")]])


def ask_points(app, ctx, data):
    app.set_state(ctx.chat_id, "a:npts", data)
    app.show(ctx, "⭐ امتیاز این تکلیف امتیازی چند باشد؟\n(بعد از تأیید شما به دانش‌آموز داده می‌شود)\nیکی را بزن یا عدد دلخواه را بنویس:",
             [[btn(fa(5), "a:np:5"), btn(fa(10), "a:np:10"), btn(fa(20), "a:np:20"), btn(fa(50), "a:np:50")]])


def st_npts(app, ctx, msg, text, data):
    v = en(text).strip()
    if not v.isdigit() or not (1 <= int(v) <= 1000):
        app.send(ctx.chat_id, "یک عدد بین ۱ تا ۱۰۰۰ بنویس.")
        return
    data["points"] = int(v)
    new_target(app, ctx, data, "bonus")


def new_target(app, ctx, data, kind):
    data["kind"] = kind
    app.set_state(ctx.chat_id, "a:nbody", data)
    app.show(ctx, "تکلیف برای چه کسانی است؟",
             [[btn("🌐 همه‌ی دانش‌آموزان", "a:nt:all")], [btn("👥 گروه‌های مشخص", "a:nt:groups")]])


def ask_deadline(app, ctx, data):
    app.set_state(ctx.chat_id, "a:ndl", data)
    app.send(ctx.chat_id, "⏰ مهلت ارسال را بنویس.\n\n" + J.DATE_HELP)


def st_ndl(app, ctx, msg, text, data):
    ts = J.parse(msg.get("text") or "", app.now())
    if ts is None:
        app.send(ctx.chat_id, "زمان را نفهمیدم.\n\n" + J.DATE_HELP)
        return
    if ts <= app.now():
        app.send(ctx.chat_id, "این زمان گذشته است. زمانی در آینده بنویس.")
        return
    data["deadline"] = ts
    app.set_state(ctx.chat_id, "a:nconfirm", data)
    if data.get("target_all", True):
        tgt = "همه‌ی دانش‌آموزان"
    else:
        names = [r["name"] for r in app.conn.execute("SELECT name FROM groups WHERE id IN (%s)" % ",".join("?" * len(data["groups"])), data["groups"])]
        tgt = "گروه: " + "، ".join(names)
    desc = "\n".join(data["desc"]) or "—"
    pts = f" (⭐ {fa(data.get('points', 0))} امتیاز)" if data["kind"] == "bonus" else ""
    app.send(ctx.chat_id,
             f"🔎 پیش‌نمایش تکلیف\n\nعنوان: {data['title']}\nنوع: {R.KIND_LABEL[data['kind']]}{pts}\nمخاطب: {tgt}\n"
             f"مهلت: {J.fmt(ts)}\nتاخیر مجاز: {fa(app.cfg.grace_minutes)} دقیقه | ارسال با تاخیر تا {fa(app.cfg.late_window_hours)} ساعت\n"
             f"فایل‌ها: {fa(len(data['files']))}\n\nمتن:\n{desc}",
             [[btn("✅ انتشار و اطلاع به دانش‌آموزان", "a:npub:1")], [btn("📌 انتشار بدون اطلاع", "a:npub:0")],
              [btn("❌ لغو", "a:ncancel")]])


def publish(app: App, ctx: Ctx, notify: bool):
    state, d = app.get_state(ctx.chat_id)
    if state != "a:nconfirm":
        app.send(ctx.chat_id, "تکلیف آماده‌ی انتشاری نیست.", HOME)
        return
    cur = app.conn.execute(
        "INSERT INTO assignments(title,description,kind,deadline_ts,grace_min,late_hours,target_all,created_ts,points) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (d["title"], "\n".join(d["desc"]), d["kind"], d["deadline"], app.cfg.grace_minutes,
         app.cfg.late_window_hours, 1 if d.get("target_all", True) else 0, app.now(),
         int(d.get("points", 0)) if d["kind"] == "bonus" else 0))
    aid = cur.lastrowid
    for gid in d.get("groups", []):
        app.conn.execute("INSERT OR IGNORE INTO assignment_groups VALUES(?,?)", (aid, gid))
    folder = app.data / "assignments" / str(aid)
    folder.mkdir(parents=True, exist_ok=True)
    for f in d["files"]:
        src = Path(f["path"])
        if src.exists():
            dest = folder / src.name
            shutil.move(str(src), str(dest))
            app.conn.execute("INSERT INTO assignment_files(assignment_id,path,kind,name) VALUES(?,?,?,?)",
                             (aid, str(dest), f["kind"], f["name"]))
    app.conn.commit()
    app.audit(ctx.user_id, "assignment_create", f"{aid}:{d['title']}")
    app.clear_state(ctx.chat_id)
    n = notify_assignment(app, aid) if notify else 0
    app.send(ctx.chat_id, f"✅ تکلیف منتشر شد." + (f"\nبه {fa(n)} دانش‌آموز اطلاع داده شد." if notify else ""),
             [[btn("📋 مشاهده‌ی تکلیف", f"a:as:{aid}")], [btn("⬅ پنل مدیریت", "a:menu")]])


def new_cancel(app, ctx):
    state, d = app.get_state(ctx.chat_id)
    for f in (d or {}).get("files", []):
        Path(f["path"]).unlink(missing_ok=True)
    app.clear_state(ctx.chat_id)
    app.show(ctx, "ساخت تکلیف لغو شد.", HOME)


# ---------- فهرست و مدیریت تکالیف ----------
def alist(app: App, ctx: Ctx, offset: int):
    total = app.conn.execute("SELECT COUNT(*) c FROM assignments WHERE status='active'").fetchone()["c"]
    rows_db = app.conn.execute("SELECT * FROM assignments WHERE status='active' ORDER BY deadline_ts DESC LIMIT ? OFFSET ?",
                               (PAGE, offset)).fetchall()
    if not rows_db:
        app.show(ctx, "هنوز تکلیفی ثبت نشده است.", [[btn("📝 تکلیف جدید", "a:new")], [btn("⬅ پنل مدیریت", "a:menu")]])
        return
    rows = [[btn(f"{R.KIND_ICON[a['kind']]} {a['title']} — {J.fmt_short(a['deadline_ts'])}"[:60], f"a:as:{a['id']}")] for a in rows_db]
    nav = []
    if offset > 0:
        nav.append(btn("◀ جدیدتر", f"a:alist:{max(0, offset - PAGE)}"))
    if offset + PAGE < total:
        nav.append(btn("قدیمی‌تر ▶", f"a:alist:{offset + PAGE}"))
    if nav:
        rows.append(nav)
    rows.append([btn("⬅ پنل مدیریت", "a:menu")])
    app.show(ctx, f"📚 تکالیف ({fa(total)} مورد، جدیدترین مهلت اول)", rows)


def tally(app, a):
    now = app.now()
    c = {"on_time": [], "late": [], "none": [], "excused": []}
    for s in R.target_students(app.conn, a):
        st = R.student_status(app.conn, a, s["id"], now)
        key = {"on_time": "on_time", "late": "late", "excused": "excused"}.get(st["code"], "none")
        c[key].append((s, st))
    return c


def aview(app: App, ctx: Ctx, aid: int):
    a = app.assignment(aid)
    if not a:
        app.show(ctx, "تکلیف پیدا نشد.", HOME)
        return
    c = tally(app, a)
    total = sum(len(v) for v in c.values())
    desc = f"\n\n{a['description']}" if a["description"] else ""
    text = (f"{R.KIND_ICON[a['kind']]} {a['title']}\nنوع: {R.KIND_LABEL[a['kind']]}{(' | ⭐ ' + fa(a['points']) + ' امتیاز') if a['kind'] == 'bonus' else ''} | مخاطب: {target_text(app, a)}\n"
            f"⏰ مهلت: {J.fmt(a['deadline_ts'])}\nتاخیر مجاز: {fa(a['grace_min'])} دقیقه | ارسال با تاخیر تا {fa(a['late_hours'])} ساعت{desc}\n\n"
            f"✅ به‌موقع: {fa(len(c['on_time']))}   ⏰ با تاخیر: {fa(len(c['late']))}\n"
            f"❌ ارسال‌نشده: {fa(len(c['none']))}   🙏 عذر موجه: {fa(len(c['excused']))}\n(از {fa(total)} نفر)")
    rows = [[btn("📋 وضعیت کامل", f"a:ast:{aid}"), btn("🔍 دیدن پاسخ یک نفر", f"a:aview:{aid}")],
            [btn("📥 دانلود همه‌ی پاسخ‌ها", f"a:azip:{aid}"), btn("🔔 یادآوری به ارسال‌نشده‌ها", f"a:arem:{aid}")],
            [btn("⏱ تمدید برای همه", f"a:aext:{aid}"), btn("👤 تمدید برای یک نفر", f"a:aext1:{aid}")],
            [btn("🙏 عذر موجه", f"a:aexc:{aid}"), btn("🔁 درخواست ارسال مجدد", f"a:ars:{aid}")],
            [btn("✏ ویرایش", f"a:aedit:{aid}"), btn("🗑 لغو تکلیف", f"a:adel:{aid}")],
            [btn("⬅ فهرست تکالیف", "a:alist:0")]]
    app.show(ctx, text, rows)


def astatus(app: App, ctx: Ctx, aid: int):
    a = app.assignment(aid)
    c = tally(app, a)
    lines = [f"📋 وضعیت «{a['title']}»", ""]
    lines.append(f"✅ به‌موقع ({fa(len(c['on_time']))}): " + ("، ".join(s["full_name"] for s, _ in c["on_time"]) or "—"))
    lines.append("")
    lines.append(f"⏰ با تاخیر ({fa(len(c['late']))}): " + ("، ".join(f"{s['full_name']} ({duration(st['over'])})" for s, st in c["late"]) or "—"))
    lines.append("")
    lines.append(f"❌ ارسال‌نشده ({fa(len(c['none']))}): " + ("، ".join(s["full_name"] for s, _ in c["none"]) or "—"))
    lines.append("")
    lines.append(f"🙏 عذر موجه ({fa(len(c['excused']))}): " + ("، ".join(s["full_name"] for s, _ in c["excused"]) or "—"))
    app.send_long(ctx.chat_id, "\n".join(lines), [[btn("⬅ بازگشت", f"a:as:{aid}")]])


def aview_pick(app: App, ctx: Ctx, aid: int):
    a = app.assignment(aid)
    studs = [s for s, _ in tally(app, a)["on_time"] + tally(app, a)["late"]]
    if not studs:
        app.show(ctx, "هنوز کسی پاسخ نفرستاده است.", [[btn("⬅ بازگشت", f"a:as:{aid}")]])
        return
    app.show(ctx, "پاسخ کدام دانش‌آموز را ببینم؟", student_buttons(studs, f"a:asub:{aid}") + [[btn("⬅ بازگشت", f"a:as:{aid}")]])


def asub_view(app: App, ctx: Ctx, aid: int, sid: int):
    a, s = app.assignment(aid), app.student(sid)
    sub = R.current_final(app.conn, aid, sid)
    if not sub:
        app.send(ctx.chat_id, "پاسخی ثبت نشده است.", [[btn("⬅ بازگشت", f"a:as:{aid}")]])
        return
    st = R.student_status(app.conn, a, sid, app.now())
    cap = f"{s['full_name']} — {a['title']}\n{reports.cell_text(st)} | {J.fmt_short(sub['submitted_ts'])}"
    for f in app.conn.execute("SELECT * FROM submission_files WHERE submission_id=? ORDER BY id", (sub["id"],)):
        app.send_file(ctx.chat_id, f["path"], cap)
        cap = None
    app.send(ctx.chat_id, f"{s['full_name']} — {reports.cell_text(st)}",
             [[btn("💬 بازخورد", f"a:fbs:{sid}:{aid}"), btn("🔁 درخواست ارسال مجدد", f"a:arss:{aid}:{sid}")],
              [btn("⬅ بازگشت", f"a:as:{aid}")]])


def azip(app: App, ctx: Ctx, aid: int):
    a = app.assignment(aid)
    out = app.data / "exports" / f"asg_{aid}"
    shutil.rmtree(out, ignore_errors=True)
    app.send(ctx.chat_id, "⏳ در حال آماده‌سازی فایل‌ها...")
    parts = reports.build_zips(app, out, aid=aid, label=f"{a['title']}")
    if not parts:
        app.send(ctx.chat_id, "هنوز پاسخی برای دانلود نیست.", [[btn("⬅ بازگشت", f"a:as:{aid}")]])
        return
    for i, p in enumerate(parts, 1):
        try:
            app.bale.send_document(ctx.chat_id, p, f"📥 پاسخ‌های «{a['title']}» — بخش {fa(i)} از {fa(len(parts))}")
        except BaleError as e:
            app.send(ctx.chat_id, f"ارسال بخش {fa(i)} ناموفق بود ({e}).")
    app.audit(ctx.user_id, "zip_assignment", str(aid))
    app.send(ctx.chat_id, "تمام شد ✅", [[btn("⬅ بازگشت", f"a:as:{aid}")]])


def aremind(app: App, ctx: Ctx, aid: int):
    a = app.assignment(aid)
    n = 0
    for s, st in tally(app, a)["none"]:
        if s["chat_id"]:
            dl = R.effective_deadline(app.conn, a, s["id"])
            app.send(s["chat_id"], f"🔔 یادآوری تکلیف «{a['title']}»\n⏰ مهلت: {J.fmt(dl)}", open_btn(aid))
            n += 1
            time.sleep(0.03)
    app.audit(ctx.user_id, "remind", f"{aid}:{n}")
    app.show(ctx, f"🔔 برای {fa(n)} نفر یادآوری فرستاده شد.", [[btn("⬅ بازگشت", f"a:as:{aid}")]])


# ----- تمدید / ویرایش / عذر / ارسال مجدد
def ask_ext_all(app, ctx, aid):
    app.set_state(ctx.chat_id, "a:aextv", {"aid": aid})
    app.send(ctx.chat_id, "⏱ مهلت جدید برای همه را بنویس.\n\n" + J.DATE_HELP)


def st_aextv(app, ctx, msg, text, data):
    ts = J.parse(msg.get("text") or "", app.now())
    if ts is None:
        app.send(ctx.chat_id, "زمان را نفهمیدم.\n\n" + J.DATE_HELP)
        return
    a = app.assignment(data["aid"])
    app.conn.execute("UPDATE assignments SET deadline_ts=? WHERE id=?", (ts, a["id"]))
    app.conn.commit()
    app.audit(ctx.user_id, "extend_all", f"{a['id']}:{ts}")
    app.clear_state(ctx.chat_id)
    n = 0
    for s, _ in tally(app, app.assignment(a["id"]))["none"]:
        if tell(app, s["id"], f"⏱ مهلت تکلیف «{a['title']}» تغییر کرد.\nمهلت جدید: {J.fmt(ts)}", open_btn(a["id"])):
            n += 1
    app.send(ctx.chat_id, f"✅ مهلت جدید ثبت شد: {J.fmt(ts)}\nبه {fa(n)} نفرِ ارسال‌نشده اطلاع داده شد.",
             [[btn("⬅ بازگشت", f"a:as:{a['id']}")]])


def st_aext1v(app, ctx, msg, text, data):
    ts = J.parse(msg.get("text") or "", app.now())
    if ts is None:
        app.send(ctx.chat_id, "زمان را نفهمیدم.\n\n" + J.DATE_HELP)
        return
    a = app.assignment(data["aid"])
    app.conn.execute("INSERT OR REPLACE INTO student_deadlines VALUES(?,?,?)", (a["id"], data["sid"], ts))
    app.conn.commit()
    app.audit(ctx.user_id, "extend_one", f"{a['id']}:{data['sid']}:{ts}")
    app.clear_state(ctx.chat_id)
    s = app.student(data["sid"])
    tell(app, s["id"], f"⏱ برای تو مهلت تکلیف «{a['title']}» تا {J.fmt(ts)} تمدید شد.", open_btn(a["id"]))
    app.send(ctx.chat_id, f"✅ مهلت {s['full_name']} تا {J.fmt(ts)} تمدید شد.", [[btn("⬅ بازگشت", f"a:as:{a['id']}")]])


def st_aedit(app, ctx, msg, text, data):
    raw = (msg.get("text") or "").strip()
    if not raw:
        app.send(ctx.chat_id, "متن را بنویس.")
        return
    if data["field"] == "p":
        v = en(raw).strip()
        if not v.isdigit() or not (1 <= int(v) <= 1000):
            app.send(ctx.chat_id, "یک عدد بین ۱ تا ۱۰۰۰ بنویس.")
            return
        col, raw = "points", int(v)
    else:
        col = "title" if data["field"] == "t" else "description"
    app.conn.execute(f"UPDATE assignments SET {col}=? WHERE id=?", (raw, data["aid"]))
    app.conn.commit()
    app.audit(ctx.user_id, "assignment_edit", f"{data['aid']}:{col}")
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, "✅ ویرایش شد. اگر لازم است دانش‌آموزان باخبر شوند از «🔔 یادآوری» استفاده کن.",
             [[btn("⬅ بازگشت", f"a:as:{data['aid']}")]])


def st_aexc(app, ctx, msg, text, data):
    reason = "" if (msg.get("text") or "").strip() in ("-", "—") else (msg.get("text") or "").strip()
    a, s = app.assignment(data["aid"]), app.student(data["sid"])
    app.conn.execute("INSERT OR REPLACE INTO excuses VALUES(?,?,?,?,?)", (a["id"], s["id"], reason, ctx.user_id, app.now()))
    app.conn.commit()
    app.audit(ctx.user_id, "excuse", f"{a['id']}:{s['id']}")
    app.clear_state(ctx.chat_id)
    tell(app, s["id"], f"🙏 برای تکلیف «{a['title']}» عذر موجهت ثبت شد و روی شمارنده‌ی نشانت اثر منفی ندارد.")
    notify_new_badges(app, s["id"], app.award(s["id"]))
    app.send(ctx.chat_id, f"✅ عذر موجه برای {s['full_name']} ثبت شد.", [[btn("⬅ بازگشت", f"a:as:{a['id']}")]])


def st_ars(app, ctx, msg, text, data):
    note = "" if (msg.get("text") or "").strip() in ("-", "—") else (msg.get("text") or "").strip()
    a, s = app.assignment(data["aid"]), app.student(data["sid"])
    app.conn.execute("INSERT OR REPLACE INTO resubmit_requests(assignment_id,student_id,note,ts,open) VALUES(?,?,?,?,1)",
                     (a["id"], s["id"], note, app.now()))
    app.conn.commit()
    app.audit(ctx.user_id, "resubmit_request", f"{a['id']}:{s['id']}")
    app.clear_state(ctx.chat_id)
    tell(app, s["id"], f"🔁 مدیر از تو خواسته پاسخ تکلیف «{a['title']}» را دوباره بفرستی." + (f"\n\nتوضیح: {note}" if note else "")
         + "\n(وضعیت به‌موقع/تاخیر ارسال اولت تغییر نمی‌کند.)", open_btn(a["id"]))
    app.send(ctx.chat_id, f"✅ درخواست ارسال مجدد برای {s['full_name']} فرستاده شد.", [[btn("⬅ بازگشت", f"a:as:{a['id']}")]])


# ---------- دانش‌آموزان ----------
def slist(app: App, ctx: Ctx, offset: int):
    total = app.conn.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    studs = app.conn.execute("SELECT * FROM students ORDER BY active DESC, full_name LIMIT ? OFFSET ?", (PAGE + 4, offset)).fetchall()
    step = PAGE + 4
    rows = []
    for s in studs:
        mark = "⏸" if not s["active"] else ("✔" if s["chat_id"] else "🕓")
        rows.append([btn(f"{mark} {s['full_name']} ({'نهم' if s['grade'] == 9 else 'ششم'})", f"a:st:{s['id']}")])
    nav = []
    if offset > 0:
        nav.append(btn("◀ قبلی", f"a:slist:{max(0, offset - step)}"))
    if offset + step < total:
        nav.append(btn("بعدی ▶", f"a:slist:{offset + step}"))
    if nav:
        rows.append(nav)
    rows.append([btn("➕ افزودن دانش‌آموز", "a:sadd"), btn("📄 کدهای ورود", "a:codes")])
    rows.append([btn("⬅ پنل مدیریت", "a:menu")])
    app.show(ctx, f"👥 دانش‌آموزان ({fa(total)} نفر)\n✔ وارد شده | 🕓 هنوز وارد نشده | ⏸ غیرفعال", rows)


def new_code(app: App) -> str:
    while True:
        code = str(100000 + secrets.randbelow(900000))
        if not app.conn.execute("SELECT 1 FROM students WHERE code=?", (code,)).fetchone():
            return code


def st_sadd(app, ctx, msg, text, data):
    lines = [clean(l) for l in (msg.get("text") or "").split("\n") if clean(l)][:60]
    if not lines:
        app.send(ctx.chat_id, "حداقل یک نام بنویس.")
        return
    out = []
    grade = 9 if data.get("grade") == 9 else 6
    for line in lines:
        name, _, grp = line.partition("|")
        name, grp = clean(name), clean(grp)
        if not name:
            continue
        code = new_code(app)
        cur = app.conn.execute("INSERT INTO students(full_name,code,created_ts,grade) VALUES(?,?,?,?)", (name, code, app.now(), grade))
        if grp:
            app.conn.execute("INSERT OR IGNORE INTO groups(name) VALUES(?)", (grp,))
            gid = app.conn.execute("SELECT id FROM groups WHERE name=?", (grp,)).fetchone()["id"]
            app.conn.execute("INSERT OR IGNORE INTO student_groups VALUES(?,?)", (cur.lastrowid, gid))
        out.append(f"{name} — کد: {fa(code)}" + (f" — گروه: {grp}" if grp else ""))
    app.conn.commit()
    app.audit(ctx.user_id, "students_add", str(len(out)))
    app.clear_state(ctx.chat_id)
    app.send_long(ctx.chat_id, f"✅ {fa(len(out))} دانش‌آموز اضافه شد. کدها محرمانه‌اند؛ هر کد را فقط به خود همان دانش‌آموز بده:\n\n" + "\n".join(out),
                  [[btn("👥 دانش‌آموزان", "a:slist:0")]])


def codes(app: App, ctx: Ctx):
    rows = app.conn.execute("SELECT * FROM students WHERE active=1 ORDER BY full_name").fetchall()
    if not rows:
        app.send(ctx.chat_id, "دانش‌آموزی نیست.", HOME)
        return
    app.send_long(ctx.chat_id, "🔑 کدهای ورود (محرمانه)\n\n" + "\n".join(
        f"{s['full_name']} ({'نهم' if s['grade'] == 9 else 'ششم'}) — {fa(s['code'])} {'✔' if s['chat_id'] else '🕓'}" for s in rows), [[btn("⬅ بازگشت", "a:slist:0")]])


def sview(app: App, ctx: Ctx, sid: int):
    s = app.student(sid)
    if not s:
        app.show(ctx, "پیدا نشد.", HOME)
        return
    text = (f"👤 {s['full_name']}\nگروه‌ها: {reports.group_names(app.conn, sid) or '—'}\n"
            f"وضعیت: {'فعال' if s['active'] else 'غیرفعال'} | ورود به بات: {'انجام شده' if s['chat_id'] else 'هنوز نه'}")
    text += f"\nپایه: {'نهم' if s['grade'] == 9 else 'ششم'}"
    if s["grade"] == 9:
        top = [[btn("📊 گزارش کامل", f"a:strep:{sid}"), btn("💬 بازخورد", f"a:fbs:{sid}")],
               [btn("📖 گزارش‌های مطالعه", f"a:book:st:{sid}")]]
    else:
        top = [[btn("📊 گزارش کامل", f"a:strep:{sid}"), btn("💬 بازخورد", f"a:fbs:{sid}")],
               [btn("🗂 گروه‌ها", f"a:stgrp:{sid}"), btn("🏅 مدیریت نشان‌ها", f"a:sbd:{sid}")],
               [btn("⭐ امتیاز", f"a:spts:{sid}")]]
    rows = top + [
            [btn("📥 همه‌ی پاسخ‌هایش", f"a:stzip:{sid}"), btn("✏ تغییر نام", f"a:stname:{sid}")] if s["grade"] != 9 else
            [btn("✏ تغییر نام", f"a:stname:{sid}")],
            [btn("🔑 کد جدید (بازنشانی ورود)", f"a:streset:{sid}")],
            [btn("▶ فعال‌سازی" if not s["active"] else "⏸ غیرفعال‌سازی", f"a:sttog:{sid}")],
            [btn("⬅ فهرست", "a:slist:0")]]
    app.show(ctx, text, rows)


def stgrp(app: App, ctx: Ctx, sid: int):
    sel = {r["group_id"] for r in app.conn.execute("SELECT group_id FROM student_groups WHERE student_id=?", (sid,))}
    if not app.conn.execute("SELECT 1 FROM groups").fetchone():
        app.show(ctx, "هنوز گروهی نساخته‌ای.", [[btn("🗂 گروه‌ها", "a:glist")]])
        return
    rows = group_rows_toggle(app, sel, f"a:stg:{sid}", f"a:st:{sid}")
    app.show(ctx, f"گروه‌های {app.student(sid)['full_name']} (برای تغییر لمس کن):", rows)


def stg_toggle(app, ctx, sid, gid):
    if app.conn.execute("SELECT 1 FROM student_groups WHERE student_id=? AND group_id=?", (sid, gid)).fetchone():
        app.conn.execute("DELETE FROM student_groups WHERE student_id=? AND group_id=?", (sid, gid))
    else:
        app.conn.execute("INSERT INTO student_groups VALUES(?,?)", (sid, gid))
    app.conn.commit()
    app.audit(ctx.user_id, "student_group_toggle", f"{sid}:{gid}")
    stgrp(app, ctx, sid)


def st_stname(app, ctx, msg, text, data):
    if not text:
        app.send(ctx.chat_id, "نام را بنویس.")
        return
    app.conn.execute("UPDATE students SET full_name=? WHERE id=?", (text, data["sid"]))
    app.conn.commit()
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, "✅ نام تغییر کرد.", [[btn("⬅ بازگشت", f"a:st:{data['sid']}")]])


def streset(app, ctx, sid):
    code = new_code(app)
    app.conn.execute("UPDATE students SET code=?, chat_id=NULL, joined_ts=NULL WHERE id=?", (code, sid))
    app.conn.commit()
    app.audit(ctx.user_id, "student_reset", str(sid))
    app.show(ctx, f"🔑 کد جدید {app.student(sid)['full_name']}: {fa(code)}\nحساب قبلی از بات جدا شد.", [[btn("⬅ بازگشت", f"a:st:{sid}")]])


def sttog(app, ctx, sid):
    app.conn.execute("UPDATE students SET active=1-active WHERE id=?", (sid,))
    app.conn.commit()
    app.audit(ctx.user_id, "student_toggle", str(sid))
    sview(app, ctx, sid)


def stzip(app, ctx, sid):
    s = app.student(sid)
    out = app.data / "exports" / f"stu_{sid}"
    shutil.rmtree(out, ignore_errors=True)
    app.send(ctx.chat_id, "⏳ در حال آماده‌سازی...")
    parts = reports.build_zips(app, out, sid=sid, label=s["full_name"])
    if not parts:
        app.send(ctx.chat_id, "این دانش‌آموز هنوز پاسخی ارسال نکرده.", [[btn("⬅ بازگشت", f"a:st:{sid}")]])
        return
    for i, p in enumerate(parts, 1):
        try:
            app.bale.send_document(ctx.chat_id, p, f"📥 پاسخ‌های {s['full_name']} — بخش {fa(i)} از {fa(len(parts))}")
        except BaleError as e:
            app.send(ctx.chat_id, f"ارسال بخش {fa(i)} ناموفق بود ({e}).")
    app.send(ctx.chat_id, "تمام شد ✅", [[btn("⬅ بازگشت", f"a:st:{sid}")]])


# ---------- گروه‌ها ----------
def glist(app: App, ctx: Ctx):
    rows = []
    for g in app.conn.execute("SELECT g.*, (SELECT COUNT(*) FROM student_groups sg WHERE sg.group_id=g.id) n FROM groups g ORDER BY name"):
        rows.append([btn(f"🗂 {g['name']} ({fa(g['n'])} نفر)", f"a:g:{g['id']}")])
    rows.append([btn("➕ گروه جدید", "a:gnew")])
    rows.append([btn("⬅ پنل مدیریت", "a:menu")])
    app.show(ctx, "🗂 گروه‌ها\nتکلیف اختصاصی برای «گروه» تعریف می‌شود؛ هر کس به گروه اضافه شود، تکالیف آن را هم می‌بیند.", rows)


def st_gnew(app, ctx, msg, text, data):
    if not text:
        app.send(ctx.chat_id, "نام گروه را بنویس.")
        return
    app.conn.execute("INSERT OR IGNORE INTO groups(name) VALUES(?)", (text,))
    app.conn.commit()
    app.audit(ctx.user_id, "group_create", text)
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, f"✅ گروه «{text}» ساخته شد.", [[btn("🗂 گروه‌ها", "a:glist")]])


def gview(app, ctx, gid):
    g = app.conn.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
    if not g:
        app.show(ctx, "گروه پیدا نشد.", HOME)
        return
    names = [r["full_name"] for r in app.conn.execute(
        "SELECT s.full_name FROM students s JOIN student_groups sg ON sg.student_id=s.id WHERE sg.group_id=? ORDER BY s.full_name", (gid,))]
    app.show(ctx, f"🗂 {g['name']}\nاعضا ({fa(len(names))}): " + ("، ".join(names) or "—"),
             [[btn("👥 تعیین اعضا", f"a:gadd:{gid}")], [btn("🗑 حذف گروه", f"a:gdel:{gid}")], [btn("⬅ گروه‌ها", "a:glist")]])


def gmembers(app, ctx, gid):
    sel = {r["student_id"] for r in app.conn.execute("SELECT student_id FROM student_groups WHERE group_id=?", (gid,))}
    rows, row = [], []
    for s in app.conn.execute("SELECT * FROM students WHERE active=1 ORDER BY full_name"):
        row.append(btn(f"{'✅' if s['id'] in sel else '⬜'} {s['full_name']}"[:30], f"a:gt:{gid}:{s['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([btn("✔ تأیید", f"a:g:{gid}")])
    app.show(ctx, "اعضای گروه (برای افزودن/حذف لمس کن):", rows)


def gt_toggle(app, ctx, gid, sid):
    if app.conn.execute("SELECT 1 FROM student_groups WHERE student_id=? AND group_id=?", (sid, gid)).fetchone():
        app.conn.execute("DELETE FROM student_groups WHERE student_id=? AND group_id=?", (sid, gid))
    else:
        app.conn.execute("INSERT INTO student_groups VALUES(?,?)", (sid, gid))
    app.conn.commit()
    app.audit(ctx.user_id, "group_member_toggle", f"{gid}:{sid}")
    gmembers(app, ctx, gid)


def gdel(app, ctx, gid, confirm):
    g = app.conn.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
    if not confirm:
        used = app.conn.execute("SELECT COUNT(*) c FROM assignment_groups ag JOIN assignments a ON a.id=ag.assignment_id "
                                "WHERE ag.group_id=? AND a.status='active'", (gid,)).fetchone()["c"]
        app.show(ctx, f"گروه «{g['name']}» حذف شود؟\n" + (f"⚠ {fa(used)} تکلیف فعال برای این گروه تعریف شده و بعد از حذف، مخاطبی نخواهد داشت.\n" if used else ""),
                 [[btn("✅ بله، حذف شود", f"a:gdely:{gid}"), btn("↩ انصراف", f"a:g:{gid}")]])
        return
    app.conn.execute("DELETE FROM student_groups WHERE group_id=?", (gid,))
    app.conn.execute("DELETE FROM groups WHERE id=?", (gid,))
    app.conn.commit()
    app.audit(ctx.user_id, "group_delete", g["name"])
    glist(app, ctx)


# ---------- گزارش‌ها ----------
def rep_menu(app, ctx):
    app.show(ctx, "📊 گزارش‌ها", [
        [btn("📋 خلاصه‌ی کل کلاس", "a:rall"), btn("📗 اکسل کامل", "a:rxlsx")],
        [btn("🔍 گزارش یک دانش‌آموز", "a:rone"), btn("🆕 آخرین ارسال‌ها", "a:rrecent")],
        [btn("🏆 جدول نشان‌ها", "a:rbadges")], [btn("⬅ پنل مدیریت", "a:menu")]])


def rep_xlsx(app, ctx):
    app.send(ctx.chat_id, "⏳ در حال ساخت اکسل...")
    p = reports.build_xlsx(app, app.data / "exports" / f"report_{app.now()}.xlsx")
    try:
        app.bale.send_document(ctx.chat_id, p, f"📗 گزارش کامل — {J.fmt_short(app.now())}")
    except BaleError as e:
        app.send(ctx.chat_id, f"ارسال اکسل ناموفق بود ({e}).")
    app.audit(ctx.user_id, "report_xlsx", "")
    for old in sorted((app.data / "exports").glob("report_*.xlsx"))[:-5]:
        old.unlink(missing_ok=True)


def rep_recent(app, ctx):
    rows = app.conn.execute(
        "SELECT s.*, st.full_name, a.title FROM submissions s JOIN students st ON st.id=s.student_id "
        "JOIN assignments a ON a.id=s.assignment_id WHERE s.state='final' ORDER BY s.submitted_ts DESC LIMIT 15").fetchall()
    if not rows:
        app.send(ctx.chat_id, "هنوز ارسالی نیست.", [[btn("⬅ گزارش‌ها", "a:rep")]])
        return
    lines = ["🆕 آخرین ارسال‌ها", ""]
    for r in rows:
        mark = "✅" if r["on_time"] else f"⏰ ({duration(r['over_minutes'])})"
        lines.append(f"{mark} {r['full_name']} — {r['title']} — {J.fmt_short(r['submitted_ts'])}")
    app.send_long(ctx.chat_id, "\n".join(lines), [[btn("⬅ گزارش‌ها", "a:rep")]])


def rep_badges(app, ctx):
    rows = app.conn.execute("SELECT s.full_name, COUNT(b.id) n FROM students s LEFT JOIN badges b ON b.student_id=s.id "
                            "WHERE s.active=1 GROUP BY s.id ORDER BY n DESC, s.full_name").fetchall()
    app.send_long(ctx.chat_id, "🏆 جدول نشان‌ها\n\n" + "\n".join(f"{r['full_name']}: 🏅 {fa(r['n'])}" for r in rows),
                  [[btn("⬅ گزارش‌ها", "a:rep")]])


def strep(app, ctx, sid):
    app.send_long(ctx.chat_id, reports.student_report(app, sid),
                  [[btn("💬 بازخورد", f"a:fbs:{sid}"), btn("📥 پاسخ‌هایش", f"a:stzip:{sid}")], [btn("⬅ بازگشت", f"a:st:{sid}")]])


# ---------- بازخورد ----------
def ask_feedback(app, ctx, sid, aid=None):
    app.set_state(ctx.chat_id, "a:fb", {"sid": sid, "aid": aid})
    app.send(ctx.chat_id, f"💬 متن بازخورد برای {app.student(sid)['full_name']} را بنویس:")


def st_fb(app, ctx, msg, text, data):
    raw = (msg.get("text") or "").strip()
    if not raw:
        app.send(ctx.chat_id, "بازخورد را به‌صورت متن بنویس.")
        return
    s = app.student(data["sid"])
    a = app.assignment(data["aid"]) if data.get("aid") else None
    app.conn.execute("INSERT INTO feedback(student_id,assignment_id,text,admin_id,ts) VALUES(?,?,?,?,?)",
                     (s["id"], a["id"] if a else None, raw, ctx.user_id, app.now()))
    app.conn.commit()
    app.audit(ctx.user_id, "feedback", f"{s['id']}")
    app.clear_state(ctx.chat_id)
    delivered = tell(app, s["id"], "💬 بازخورد مدیر" + (f" برای «{a['title']}»" if a else "") + f":\n\n{raw}")
    app.send(ctx.chat_id, "✅ بازخورد ثبت و برای دانش‌آموز فرستاده شد." if delivered else "✅ بازخورد ثبت شد (دانش‌آموز هنوز وارد بات نشده؛ بعداً در «بازخوردها» می‌بیند).",
             [[btn("⬅ پنل مدیریت", "a:menu")]])


# ---------- پیام همگانی ----------
def bc_start(app, ctx):
    rows = [[btn("🌐 همه‌ی دانش‌آموزان", "a:bct:all")], [btn("پایه‌ی ششم", "a:bct:g6"), btn("پایه‌ی نهم", "a:bct:g9")]]
    for g in app.conn.execute("SELECT * FROM groups ORDER BY name"):
        rows.append([btn(f"🗂 {g['name']}", f"a:bct:{g['id']}")])
    rows.append([btn("⬅ پنل مدیریت", "a:menu")])
    app.show(ctx, "📢 پیام برای چه کسانی ارسال شود؟", rows)


def bc_recipients(app, target):
    if target == "all":
        return app.conn.execute("SELECT * FROM students WHERE active=1 AND chat_id IS NOT NULL").fetchall()
    if target in ("g6", "g9"):
        return app.conn.execute("SELECT * FROM students WHERE active=1 AND chat_id IS NOT NULL AND grade=?", (int(target[1:]),)).fetchall()
    return app.conn.execute("SELECT s.* FROM students s JOIN student_groups sg ON sg.student_id=s.id "
                            "WHERE sg.group_id=? AND s.active=1 AND s.chat_id IS NOT NULL", (int(target),)).fetchall()


def st_bct(app, ctx, msg, text, data):
    raw = (msg.get("text") or "").strip()
    if not raw:
        app.send(ctx.chat_id, "متن پیام را بنویس.")
        return
    n = len(bc_recipients(app, data["target"]))
    app.set_state(ctx.chat_id, "a:bcconfirm", {"target": data["target"], "text": raw})
    app.send(ctx.chat_id, f"🔎 پیش‌نمایش (به {fa(n)} نفر ارسال می‌شود):\n\n📢 پیام مجموعه رشد\n\n{raw}",
             [[btn("✅ ارسال", "a:bcsend"), btn("❌ لغو", "a:menu")]])


def bc_send(app, ctx):
    state, d = app.get_state(ctx.chat_id)
    if state != "a:bcconfirm":
        return
    n = 0
    for s in bc_recipients(app, d["target"]):
        if app.send(s["chat_id"], f"📢 پیام مجموعه رشد\n\n{d['text']}"):
            n += 1
        time.sleep(0.04)
    app.audit(ctx.user_id, "broadcast", f"{d['target']}:{n}")
    app.clear_state(ctx.chat_id)
    app.show(ctx, f"✅ پیام برای {fa(n)} نفر ارسال شد.", HOME)


# ---------- نشان دستی ----------
def st_bds(app, ctx, msg, text, data):
    if not text:
        app.send(ctx.chat_id, "عنوان نشان را بنویس.")
        return
    s = app.student(data["sid"])
    title = f"🎖 {text}"
    R.give_badge(app.conn, s["id"], "manual", f"{app.now()}", title, app.now())
    app.audit(ctx.user_id, "badge_manual", f"{s['id']}:{text}")
    app.clear_state(ctx.chat_id)
    tell(app, s["id"], f"🎉 مدیر یک نشان ویژه به تو داد!\n{title}")
    app.send(ctx.chat_id, f"✅ نشان به {s['full_name']} داده شد.", HOME)


# ---------- مدیران ----------
def adm_view(app, ctx):
    rows = [[btn("➕ افزودن مدیر", "a:admadd")]]
    lines = ["⚙ مدیران", "", "مدیران ثابت (از فایل تنظیمات): " + ("، ".join(fa(i) for i in sorted(app.cfg.admin_ids)) or "—")]
    extra = app.conn.execute("SELECT user_id FROM admins ORDER BY added_ts").fetchall()
    for r in extra:
        rows.append([btn(f"🗑 حذف {fa(r['user_id'])}", f"a:admdel:{r['user_id']}")])
    lines.append("مدیران افزوده‌شده: " + ("، ".join(fa(r["user_id"]) for r in extra) or "—"))
    lines.append("\nشناسه‌ی عددی هر نفر را با دستور /myid در بات می‌گیرد.")
    rows.append([btn("⬅ پنل مدیریت", "a:menu")])
    app.show(ctx, "\n".join(lines), rows)


def st_admadd(app, ctx, msg, text, data):
    v = en(text).replace(" ", "")
    if not v.isdigit():
        app.send(ctx.chat_id, "شناسه باید فقط عدد باشد.")
        return
    app.conn.execute("INSERT OR IGNORE INTO admins VALUES(?,?)", (int(v), app.now()))
    app.conn.commit()
    app.audit(ctx.user_id, "admin_add", v)
    app.clear_state(ctx.chat_id)
    app.send(ctx.chat_id, "✅ مدیر اضافه شد.", [[btn("⚙ مدیران", "a:adm")]])


# ---------- پنل وب ----------
WEB_CODE_TTL = 300  # ثانیه


def web_login(app: App, ctx: Ctx):
    """کد یک‌بارمصرف ۸ رقمی برای ورود به پنل وب می‌سازد (فقط هش آن ذخیره می‌شود)."""
    import hashlib
    import hmac
    now = app.now()
    app.conn.execute("DELETE FROM web_logins WHERE expires_ts<?", (now,))
    code = f"{secrets.randbelow(10 ** 8):08d}"
    h = hmac.new(app.cfg.token.encode(), code.encode(), hashlib.sha256).hexdigest()
    app.conn.execute("INSERT INTO web_logins(code_hash,admin_id,created_ts,expires_ts) VALUES(?,?,?,?)",
                     (h, ctx.user_id, now, now + WEB_CODE_TTL))
    app.conn.commit()
    app.audit(ctx.user_id, "web_login_code", "")
    where = f"\nنشانی پنل: {app.cfg.panel_url}" if app.cfg.panel_url else \
        f"\nنشانی پنل (روی همین سیستم): http://localhost:{app.cfg.panel_port}"
    app.send(ctx.chat_id,
             f"🌐 کد ورود به پنل وب: {fa(code)}\n\n⏳ فقط {fa(WEB_CODE_TTL // 60)} دقیقه اعتبار دارد و یک‌بار مصرف است."
             f"{where}\n\nپنل فقط‌خواندنی است؛ هیچ تغییری از آن‌جا ممکن نیست. کد را به کسی نده.",
             [[btn("⬅ پنل مدیریت", "a:menu")]])


# ---------- مسیریابی ----------
STATE_HANDLERS = {
    "a:ntitle": st_ntitle, "a:nbody": st_nbody, "a:ndl": st_ndl,
    "a:aextv": st_aextv, "a:aext1v": st_aext1v, "a:aedit": st_aedit, "a:aexc": st_aexc, "a:ars": st_ars,
    "a:sadd": st_sadd, "a:stname": st_stname, "a:gnew": st_gnew, "a:fb": st_fb, "a:bct": st_bct,
    "a:bds": st_bds, "a:admadd": st_admadd,
    "a:npts": st_npts, "a:padj": points.st_padj, "a:sbde": points.st_sbde,
    "a:bke": books.st_edit_book, "a:bkp": books.st_edit_pages,
}


def on_message(app: App, ctx: Ctx, msg):
    state, data = app.get_state(ctx.chat_id)
    h = STATE_HANDLERS.get(state)
    if h:
        h(app, ctx, msg, clean(msg.get("text") or ""), data)
    else:
        menu(app, ctx)


def _pending(app, aid):
    return [s for s, _ in tally(app, app.assignment(aid))["none"]]


def on_callback(app: App, ctx: Ctx, parts):
    c = parts[1]
    arg = parts[2:] 
    i = lambda k: int(arg[k])
    state, data = app.get_state(ctx.chat_id)
    if c == "menu":
        app.clear_state(ctx.chat_id)
        menu(app, ctx)
    # تکلیف جدید
    elif c == "new":
        new_start(app, ctx)
    elif c == "nb" and state == "a:nbody":
        new_kind(app, ctx)
    elif c == "nk" and state == "a:nbody":
        if arg[0] == "bonus":
            ask_points(app, ctx, data)
        else:
            data["points"] = 0
            new_target(app, ctx, data, arg[0])
    elif c == "np" and state in ("a:npts", "a:nbody"):
        data["points"] = i(0)
        new_target(app, ctx, data, "bonus")
    elif c == "nt" and state == "a:nbody":
        if arg[0] == "all":
            data["target_all"], data["groups"] = True, []
            ask_deadline(app, ctx, data)
        else:
            if not app.conn.execute("SELECT 1 FROM groups").fetchone():
                app.show(ctx, "هنوز گروهی نساخته‌ای؛ اول گروه بساز یا «همه» را انتخاب کن.",
                         [[btn("🌐 همه‌ی دانش‌آموزان", "a:nt:all")]])
                return
            data["target_all"] = False
            data.setdefault("groups", [])
            app.set_state(ctx.chat_id, "a:nbody", data)
            app.show(ctx, "گروه‌ها را انتخاب کن (می‌شود چندتا باشد):", group_rows_toggle(app, set(data["groups"]), "a:ng", "a:ngd"))
    elif c == "ng" and state == "a:nbody":
        gid = i(0)
        g = set(data.get("groups", []))
        g.symmetric_difference_update({gid})
        data["groups"] = sorted(g)
        app.set_state(ctx.chat_id, "a:nbody", data)
        app.show(ctx, "گروه‌ها را انتخاب کن (می‌شود چندتا باشد):", group_rows_toggle(app, g, "a:ng", "a:ngd"))
    elif c == "ngd" and state == "a:nbody":
        if not data.get("groups"):
            app.send(ctx.chat_id, "حداقل یک گروه انتخاب کن.")
        else:
            ask_deadline(app, ctx, data)
    elif c == "npub":
        publish(app, ctx, arg[0] == "1")
    elif c == "ncancel":
        new_cancel(app, ctx)
    # تکالیف
    elif c == "alist":
        alist(app, ctx, i(0))
    elif c == "as":
        aview(app, ctx, i(0))
    elif c == "ast":
        astatus(app, ctx, i(0))
    elif c == "aview":
        aview_pick(app, ctx, i(0))
    elif c == "asub":
        asub_view(app, ctx, i(0), i(1))
    elif c == "azip":
        azip(app, ctx, i(0))
    elif c == "arem":
        aremind(app, ctx, i(0))
    elif c == "aext":
        ask_ext_all(app, ctx, i(0))
    elif c == "aext1":
        studs = _pending(app, i(0))
        if studs:
            app.show(ctx, "مهلت چه کسی تمدید شود؟", student_buttons(studs, f"a:aext1s:{i(0)}") + [[btn("⬅ بازگشت", f"a:as:{i(0)}")]])
        else:
            app.show(ctx, "همه ارسال کرده‌اند یا عذر موجه دارند.", [[btn("⬅ بازگشت", f"a:as:{i(0)}")]])
    elif c == "aext1s":
        app.set_state(ctx.chat_id, "a:aext1v", {"aid": i(0), "sid": i(1)})
        app.send(ctx.chat_id, f"⏱ مهلت جدید {app.student(i(1))['full_name']} را بنویس.\n\n" + J.DATE_HELP)
    elif c == "aedit":
        rows = [[btn("✏ عنوان", f"a:aedf:{i(0)}:t"), btn("📝 متن تکلیف", f"a:aedf:{i(0)}:d")]]
        if app.assignment(i(0))["kind"] == "bonus":
            rows.append([btn("⭐ امتیاز", f"a:aedf:{i(0)}:p")])
        app.show(ctx, "کدام را ویرایش کنم؟", rows + [[btn("⬅ بازگشت", f"a:as:{i(0)}")]])
    elif c == "aedf":
        app.set_state(ctx.chat_id, "a:aedit", {"aid": i(0), "field": arg[1]})
        app.send(ctx.chat_id, "متن جدید را بنویس:")
    elif c == "aexc":
        studs = _pending(app, i(0))
        if studs:
            app.show(ctx, "برای چه کسی عذر موجه ثبت شود؟", student_buttons(studs, f"a:aexcs:{i(0)}") + [[btn("⬅ بازگشت", f"a:as:{i(0)}")]])
        else:
            app.show(ctx, "کسی در انتظار ارسال نیست.", [[btn("⬅ بازگشت", f"a:as:{i(0)}")]])
    elif c == "aexcs":
        app.set_state(ctx.chat_id, "a:aexc", {"aid": i(0), "sid": i(1)})
        app.send(ctx.chat_id, "دلیل عذر را بنویس (یا «-» برای بدون توضیح):")
    elif c == "ars":
        t = tally(app, app.assignment(i(0)))
        studs = [s for s, _ in t["on_time"] + t["late"]]
        if studs:
            app.show(ctx, "از چه کسی ارسال مجدد خواسته شود؟", student_buttons(studs, f"a:arss:{i(0)}") + [[btn("⬅ بازگشت", f"a:as:{i(0)}")]])
        else:
            app.show(ctx, "هنوز کسی پاسخ نفرستاده است.", [[btn("⬅ بازگشت", f"a:as:{i(0)}")]])
    elif c == "arss":
        app.set_state(ctx.chat_id, "a:ars", {"aid": i(0), "sid": i(1)})
        app.send(ctx.chat_id, "توضیح برای دانش‌آموز را بنویس (مثلاً «عکس خوانا نبود»؛ یا «-»):")
    elif c == "adel":
        app.show(ctx, "این تکلیف لغو شود؟ (فایل‌ها و پاسخ‌ها حذف نمی‌شوند، فقط از لیست و شمارنده خارج می‌شود)",
                 [[btn("✅ بله، لغو شود", f"a:adely:{i(0)}"), btn("↩ انصراف", f"a:as:{i(0)}")]])
    elif c == "adely":
        app.conn.execute("UPDATE assignments SET status='cancelled' WHERE id=?", (i(0),))
        app.conn.commit()
        app.audit(ctx.user_id, "assignment_cancel", str(i(0)))
        alist(app, ctx, 0)
    # دانش‌آموزان
    elif c == "slist":
        slist(app, ctx, i(0))
    elif c == "sadd":
        if not arg:
            app.show(ctx, "دانش‌آموزان کدام پایه را اضافه می‌کنی؟\n(پایه‌ی ششم: تکالیف | پایه‌ی نهم: باشگاه کتابخوانی)",
                     [[btn("پایه‌ی ششم", "a:sadd:6"), btn("پایه‌ی نهم", "a:sadd:9")], [btn("⬅ فهرست", "a:slist:0")]])
        else:
            app.set_state(ctx.chat_id, "a:sadd", {"grade": 9 if arg[0] == "9" else 6})
            app.send(ctx.chat_id, f"نام دانش‌آموزان «پایه‌ی {'نهم' if arg[0] == '9' else 'ششم'}» را بفرست؛ هر نفر در یک خط."
                                  "\nاگر می‌خواهی هم‌زمان گروهش را بدهی بنویس: «نام | گروه»\n(حداکثر ۶۰ نفر در هر پیام)")
    elif c == "codes":
        codes(app, ctx)
    elif c == "st":
        sview(app, ctx, i(0))
    elif c == "strep":
        strep(app, ctx, i(0))
    elif c == "stgrp":
        stgrp(app, ctx, i(0))
    elif c == "stg":
        stg_toggle(app, ctx, i(0), i(1))
    elif c == "stname":
        app.set_state(ctx.chat_id, "a:stname", {"sid": i(0)})
        app.send(ctx.chat_id, "نام جدید را بنویس:")
    elif c == "streset":
        streset(app, ctx, i(0))
    elif c == "sttog":
        sttog(app, ctx, i(0))
    elif c == "stzip":
        stzip(app, ctx, i(0))
    # گروه‌ها
    elif c == "glist":
        glist(app, ctx)
    elif c == "gnew":
        app.set_state(ctx.chat_id, "a:gnew", {})
        app.send(ctx.chat_id, "نام گروه را بنویس:")
    elif c == "g":
        gview(app, ctx, i(0))
    elif c == "gadd":
        gmembers(app, ctx, i(0))
    elif c == "gt":
        gt_toggle(app, ctx, i(0), i(1))
    elif c == "gdel":
        gdel(app, ctx, i(0), False)
    elif c == "gdely":
        gdel(app, ctx, i(0), True)
    # گزارش
    elif c == "rep":
        rep_menu(app, ctx)
    elif c == "rall":
        app.send_long(ctx.chat_id, reports.class_lines(app), [[btn("⬅ گزارش‌ها", "a:rep")]])
    elif c == "rxlsx":
        rep_xlsx(app, ctx)
    elif c == "rone":
        studs = app.conn.execute("SELECT * FROM students WHERE active=1 ORDER BY grade, full_name").fetchall()
        app.show(ctx, "گزارش کدام دانش‌آموز؟", student_buttons(studs, "a:strep") + [[btn("⬅ گزارش‌ها", "a:rep")]])
    elif c == "rrecent":
        rep_recent(app, ctx)
    elif c == "rbadges":
        rep_badges(app, ctx)
    # بازخورد
    elif c == "fbs":
        ask_feedback(app, ctx, i(0), i(1) if len(arg) > 1 else None)
    # پیام همگانی
    elif c == "bc":
        bc_start(app, ctx)
    elif c == "bct":
        app.set_state(ctx.chat_id, "a:bct", {"target": arg[0]})
        app.send(ctx.chat_id, "متن پیام را بنویس:")
    elif c == "bcsend":
        bc_send(app, ctx)
    # نشان دستی
    elif c == "badge":
        studs = app.conn.execute("SELECT * FROM students WHERE active=1 AND grade=6 ORDER BY full_name").fetchall()
        app.show(ctx, "نشان به چه کسی داده شود؟", student_buttons(studs, "a:bds") + [[btn("⬅ پنل مدیریت", "a:menu")]])
    elif c == "bds":
        app.set_state(ctx.chat_id, "a:bds", {"sid": i(0)})
        app.send(ctx.chat_id, "عنوان نشان را بنویس (مثلاً «بهترین توضیح هفته»):")
    # مدیران
    elif c == "web":
        web_login(app, ctx)
    elif c == "adm":
        adm_view(app, ctx)
    # باشگاه کتابخوانی، امتیاز و نشان‌ها
    elif c == "book":
        books.admin_callback(app, ctx, arg)
    elif c == "pts":
        points.pending_view(app, ctx, i(0) if arg else 0)
    elif c == "pok":
        points.approve(app, ctx, i(0))
    elif c == "pno":
        points.reject(app, ctx, i(0))
    elif c == "pall":
        points.approve_all(app, ctx)
    elif c == "spts":
        points.student_points(app, ctx, i(0))
    elif c == "padj":
        app.set_state(ctx.chat_id, "a:padj", {"sid": i(0)})
        app.send(ctx.chat_id, "تغییر امتیاز را بنویس: عدد (با + یا −) و دلیل.\nمثال: +5 مشارکت عالی در کلاس\nیا: -3 بی‌نظمی")
    elif c == "sbd":
        points.badges_view(app, ctx, i(0))
    elif c == "sbde":
        app.set_state(ctx.chat_id, "a:sbde", {"bid": i(0)})
        app.send(ctx.chat_id, "عنوان جدید نشان را بنویس:")
    elif c == "sbdd":
        points.badge_delete(app, ctx, i(0), False)
    elif c == "sbddy":
        points.badge_delete(app, ctx, i(0), True)
    elif c == "admadd":
        app.set_state(ctx.chat_id, "a:admadd", {})
        app.send(ctx.chat_id, "شناسه‌ی عددی بله‌ی مدیر جدید را بنویس (با /myid در بات گرفته می‌شود):")
    elif c == "admdel":
        app.conn.execute("DELETE FROM admins WHERE user_id=?", (i(0),))
        app.conn.commit()
        app.audit(ctx.user_id, "admin_del", str(i(0)))
        adm_view(app, ctx)
