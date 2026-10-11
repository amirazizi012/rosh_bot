"""صفحه‌های پنل وب فقط‌خواندنی: همه‌ی متن‌ها فارسی، راست‌چین و با ارقام فارسی.
هیچ تابعی در این فایل چیزی در دیتابیس نمی‌نویسد."""
from __future__ import annotations

import html
import re
from pathlib import Path

from . import jalali as J
from . import reports
from . import rules as R
from .fa import duration, fa

ACTION_LABELS = {
    "assignment_create": "ساخت تکلیف", "assignment_edit": "ویرایش تکلیف", "assignment_cancel": "لغو تکلیف",
    "extend_all": "تمدید مهلت برای همه", "extend_one": "تمدید مهلت برای یک نفر", "excuse": "ثبت عذر موجه",
    "resubmit_request": "درخواست ارسال مجدد", "remind": "یادآوری", "feedback": "بازخورد",
    "broadcast": "پیام همگانی", "badge_manual": "نشان دستی", "students_add": "افزودن دانش‌آموز",
    "student_reset": "بازنشانی کد ورود", "student_toggle": "فعال/غیرفعال‌سازی دانش‌آموز",
    "student_group_toggle": "تغییر گروه دانش‌آموز", "group_create": "ساخت گروه", "group_delete": "حذف گروه",
    "group_member_toggle": "تغییر اعضای گروه", "admin_add": "افزودن مدیر", "admin_del": "حذف مدیر",
    "zip_assignment": "دانلود پاسخ‌های تکلیف", "report_xlsx": "دریافت اکسل", "web_login_code": "کد ورود به پنل وب",
}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


CSS = """
@font-face{font-family:Vazirmatn;src:url(/static/Vazirmatn-Regular.woff2) format('woff2');font-weight:400;font-display:swap}
@font-face{font-family:Vazirmatn;src:url(/static/Vazirmatn-Bold.woff2) format('woff2');font-weight:700;font-display:swap}
:root{--g:#2E7D4F;--gd:#1f5a38;--gl:#e7f3ea;--bg:#f5f8f4;--card:#fff;--line:#dfe7dc;--tx:#1d2b22;--mut:#5f6f64;
--ok:#1f6b3b;--okb:#e1f3e7;--lt:#8a5a00;--ltb:#fff0d1;--ms:#a12a1d;--msb:#fde3df;--ex:#455a64;--exb:#eceff1;--wt:#245a9c;--wtb:#e3eefb}
*{box-sizing:border-box}
html{direction:rtl}
body{margin:0;background:var(--bg);color:var(--tx);font-family:Vazirmatn,Tahoma,"Segoe UI",sans-serif;line-height:1.8;font-size:15px}
a{color:var(--gd);text-decoration:none}a:hover{text-decoration:underline}
header.top{background:var(--g);color:#fff;position:sticky;top:0;z-index:5;box-shadow:0 2px 8px rgba(0,0,0,.12)}
.bar-in{max-width:1180px;margin:auto;display:flex;align-items:center;gap:14px;padding:8px 16px}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:17px;white-space:nowrap;color:#fff}
.brand img{height:36px;width:auto;border-radius:6px;background:#fff;padding:2px}
nav{display:flex;gap:4px;overflow-x:auto;flex:1;scrollbar-width:none}
nav a{color:#e9f5ec;padding:6px 12px;border-radius:8px;white-space:nowrap}
nav a:hover{background:rgba(255,255,255,.14);text-decoration:none}
nav a.on{background:#fff;color:var(--gd);font-weight:700}
form.logout button{background:transparent;border:1px solid rgba(255,255,255,.55);color:#fff;border-radius:8px;padding:5px 12px;font:inherit;cursor:pointer}
main{max-width:1180px;margin:22px auto;padding:0 16px 40px}
h1{font-size:23px;margin:0 0 4px}h2{font-size:18px;margin:26px 0 10px}
.sub{color:var(--mut);margin:0 0 18px}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.stat b{display:block;font-size:26px;color:var(--gd);line-height:1.3}
.stat span{color:var(--mut);font-size:13px}
.tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:14px}
table{border-collapse:collapse;width:100%;min-width:560px}
th,td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line);vertical-align:middle}
th{background:var(--gl);color:var(--gd);font-weight:700;font-size:13.5px;position:sticky;top:0}
tr:last-child td{border-bottom:0}tbody tr:hover{background:#fafcf9}
.chip{display:inline-block;padding:1px 10px;border-radius:999px;font-size:12.5px;white-space:nowrap}
.ok{background:var(--okb);color:var(--ok)}.late{background:var(--ltb);color:var(--lt)}.miss{background:var(--msb);color:var(--ms)}
.exc{background:var(--exb);color:var(--ex)}.wait{background:var(--wtb);color:var(--wt)}
.kbar{display:flex;height:10px;width:150px;border-radius:6px;overflow:hidden;background:#e8ede6}
.kbar i{display:block;height:100%}.k-ok{background:#3aa066}.k-late{background:#e5a72b}.k-miss{background:#d9534f}.k-exc{background:#9aa9b0}
.prog{display:flex;gap:3px}.prog i{width:14px;height:14px;border-radius:4px;background:#e1e8de}.prog i.f{background:var(--g)}
.search{width:100%;max-width:340px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;font:inherit;margin:0 0 12px;background:#fff}
.btn{display:inline-block;background:var(--g);color:#fff;padding:7px 16px;border-radius:10px;font-weight:700}
.btn:hover{background:var(--gd);text-decoration:none}.btn.ghost{background:#fff;color:var(--gd);border:1px solid var(--g)}
.thumbs{display:flex;gap:6px;flex-wrap:wrap}.thumbs img{height:52px;width:52px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.pill{display:inline-block;background:var(--gl);color:var(--gd);border-radius:8px;padding:1px 9px;margin:2px;font-size:13px}
.muted{color:var(--mut)}.nowrap{white-space:nowrap}
.note{background:#fff9e6;border:1px solid #f0e2a8;border-radius:12px;padding:10px 14px;color:#6b5a14}
.login{max-width:400px;margin:9vh auto;text-align:center}
.login input{width:100%;padding:12px;font:inherit;font-size:22px;letter-spacing:6px;text-align:center;border:1px solid var(--line);border-radius:12px;margin:10px 0}
.login button{width:100%;padding:11px;font:inherit;font-weight:700;background:var(--g);color:#fff;border:0;border-radius:12px;cursor:pointer}
.err{background:var(--msb);color:var(--ms);border-radius:10px;padding:8px;margin:8px 0}
.two{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.row{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px dashed var(--line)}.row:last-child{border:0}
@media(max-width:640px){.bar-in{flex-wrap:wrap}nav{order:3;flex-basis:100%}.kbar{width:90px}.grid{grid-template-columns:repeat(2,1fr)}main{margin-top:14px}}
@media print{header.top,.search,form.logout,.btn{display:none}body{background:#fff}}
"""

JS = """
document.addEventListener('input',function(e){
  var t=e.target; if(!t.classList.contains('search')) return;
  var q=t.value.trim(); var tb=document.getElementById(t.getAttribute('data-table'));
  if(!tb) return;
  tb.querySelectorAll('tbody tr').forEach(function(r){r.style.display=(r.textContent.indexOf(q)>-1)?'':'none';});
});
"""

NAV = [("/", "داشبورد"), ("/students", "دانش‌آموزان"), ("/assignments", "تکالیف"), ("/points", "امتیازها"),
       ("/badges", "نشان‌ها"), ("/books", "باشگاه کتابخوانی"), ("/feedback", "بازخوردها"), ("/audit", "فعالیت مدیران")]


def has_logo(data_dir: Path) -> bool:
    return (Path(data_dir).parent / "assets" / "logo.png").exists() or (Path("assets") / "logo.png").exists()


_TEXT_NODE = re.compile(r">([^<>]+)<")
_ENTITY = re.compile(r"(&#?\w+;)")


def _fa_node(m) -> str:
    parts = _ENTITY.split(m.group(1))  # موجودیت‌هایی مثل &#x27; دست نمی‌خورند
    return ">" + "".join(p if i % 2 else fa(p) for i, p in enumerate(parts)) + "<"


def persian_digits(markup: str) -> str:
    """ارقام فقط در «متن» صفحه فارسی می‌شوند؛ نشانی‌ها، ویژگی‌ها و CSS دست نمی‌خورند."""
    return _TEXT_NODE.sub(_fa_node, markup)


def layout(title: str, body: str, active: str = "", logged: bool = True, logo: bool = False) -> str:
    links = "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{esc(t)}</a>' for h, t in NAV) if logged else ""
    out = ('<form class="logout" method="post" action="/logout"><button>خروج</button></form>' if logged else "")
    img = '<img src="/static/logo.png" alt="">' if logo else "🌱"
    return (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{esc(fa(title))} — پنل رشد</title>'
            f'<style>{CSS}</style></head><body>'
            f'<header class="top"><div class="bar-in"><a class="brand" href="/">{img}<span>مجموعه تربیتی، آموزشی رشد</span></a>'
            f'<nav>{links}</nav>{out}</div></header><main>{persian_digits(body)}</main>'
            f'<script src="/static/panel.js"></script></body></html>')


def login_page(error: str = "", logo: bool = False) -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    body = ('<div class="login card"><h1>ورود به پنل رشد</h1>'
            '<p class="sub">این پنل فقط برای مشاهده است و هیچ چیزی را تغییر نمی‌دهد.</p>'
            f'{err}<form method="post" action="/login">'
            '<input name="code" inputmode="numeric" autocomplete="off" maxlength="12" placeholder="کد ۸ رقمی" autofocus>'
            '<button>ورود</button></form>'
            '<p class="muted" style="font-size:13px;margin-top:14px">در بات بله: پنل مدیریت ← «🌐 ورود به پنل وب» را بزن و کد را اینجا وارد کن. '
            'کد ۵ دقیقه اعتبار دارد و یک‌بار مصرف است.</p></div>')
    return layout("ورود", body, logged=False, logo=logo)


# ---------- اجزای مشترک ----------
def chip(code: str, over: int = 0) -> str:
    cls = {"on_time": "ok", "late": "late", "excused": "exc", "waiting": "wait", "overdue": "miss", "missed": "miss"}[code]
    label = {"on_time": "به‌موقع", "late": f"تاخیر {duration(over)}", "excused": "عذر موجه",
             "waiting": "در انتظار", "overdue": "ارسال‌نشده", "missed": "ارسال‌نشده"}[code]
    return f'<span class="chip {cls}">{esc(label)}</span>'


def stat_bar(t: dict) -> str:
    total = t["on_time"] + t["late"] + t["missed"] + t["excused"]
    if not total:
        return '<span class="muted">—</span>'
    def w(x): return f"{x * 100 / total:.1f}%"
    return ('<div class="kbar" title="به‌موقع / با تاخیر / ارسال‌نشده / عذر">'
            f'<i class="k-ok" style="width:{w(t["on_time"])}"></i><i class="k-late" style="width:{w(t["late"])}"></i>'
            f'<i class="k-miss" style="width:{w(t["missed"])}"></i><i class="k-exc" style="width:{w(t["excused"])}"></i></div>')


def progress(cur: int, n: int) -> str:
    return '<div class="prog" title="%s از %s">%s</div>' % (fa(cur), fa(n), "".join(f'<i class="{"f" if i < cur else ""}"></i>' for i in range(n)))


def table(headers, rows, tid: str = "") -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    idattr = f' id="{tid}"' if tid else ""
    return f'<div class="tw"><table{idattr}><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def link(href, text) -> str:
    return f'<a href="{esc(href)}">{esc(text)}</a>'


def students_active(conn, grade=6):
    return conn.execute("SELECT * FROM students WHERE active=1 AND grade=? ORDER BY full_name", (grade,)).fetchall()


def groups_of(conn, sid) -> str:
    g = reports.group_names(conn, sid)
    return "".join(f'<span class="pill">{esc(x)}</span>' for x in g.split("، ")) if g else '<span class="muted">—</span>'


def tally(conn, a, now):
    c = {"on_time": [], "late": [], "none": [], "excused": []}
    for s in R.target_students(conn, a):
        st = R.student_status(conn, a, s["id"], now)
        key = {"on_time": "on_time", "late": "late", "excused": "excused"}.get(st["code"], "none")
        c[key].append((s, st))
    return c


def files_html(conn, sub) -> str:
    if not sub:
        return '<span class="muted">—</span>'
    rows = conn.execute("SELECT * FROM submission_files WHERE submission_id=? ORDER BY id", (sub["id"],)).fetchall()
    out = []
    for f in rows:
        if Path(f["path"]).suffix.lower() in IMG_EXT:
            out.append(f'<a href="/file/{f["id"]}" target="_blank"><img loading="lazy" src="/file/{f["id"]}" alt="پاسخ"></a>')
        else:
            out.append(f'<a class="pill" href="/file/{f["id"]}" target="_blank">{esc(Path(f["path"]).suffix.upper().lstrip(".") or "فایل")}</a>')
    return f'<div class="thumbs">{"".join(out)}</div>' if out else '<span class="muted">—</span>'


# ---------- صفحه‌ها ----------
def dashboard(conn, cfg, now, logo=False) -> str:
    n = cfg.streak_size
    studs = students_active(conn)
    stats = {s["id"]: R.student_stats(conn, s["id"], now, n) for s in studs}
    joined = sum(1 for s in studs if s["chat_id"])
    n_asg = conn.execute("SELECT COUNT(*) c FROM assignments WHERE status='active'").fetchone()["c"]
    day = J.to_dt(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today = conn.execute("SELECT COUNT(*) c FROM submissions WHERE state='final' AND submitted_ts>=?", (int(day),)).fetchone()["c"]
    n_badges = conn.execute("SELECT COUNT(*) c FROM badges").fetchone()["c"]
    n_pending = conn.execute("SELECT COUNT(*) c FROM points_ledger WHERE status='pending'").fetchone()["c"]
    cards = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(t)}</span></div>' for v, t in [
        (f"{joined} از {len(studs)}", "دانش‌آموز ششم وارد شده به بات"), (n_asg, "تکلیف فعال"),
        (today, "ارسال امروز"), (n_badges, "نشان صادرشده"), (n_pending, "امتیاز در انتظار تأیید مدیر")])

    up = conn.execute("SELECT * FROM assignments WHERE status='active' AND deadline_ts>? ORDER BY deadline_ts LIMIT 5", (now,)).fetchall()
    up_rows = []
    for a in up:
        c = tally(conn, a, now)
        done = len(c["on_time"]) + len(c["late"])
        total = sum(len(v) for v in c.values())
        up_rows.append([link(f"/assignment/{a['id']}", a["title"]), esc(R.KIND_LABEL[a["kind"]]),
                        f'<span class="nowrap">{esc(J.fmt_short(a["deadline_ts"]))}</span>', f"{fa(done)} از {fa(total)}"])
    up_html = table(["تکلیف", "نوع", "مهلت", "ارسال‌شده"], up_rows) if up_rows else '<div class="card muted">مهلت پیش‌رویی ثبت نشده است.</div>'

    need = sorted([s for s in studs if stats[s["id"]]["missed"] > 0], key=lambda s: -stats[s["id"]]["missed"])[:6]
    need_rows = [[link(f"/student/{s['id']}", s["full_name"]), fa(stats[s["id"]]["missed"]), fa(stats[s["id"]]["late"])] for s in need]
    need_html = table(["دانش‌آموز", "ارسال‌نشده", "با تاخیر"], need_rows) if need_rows else '<div class="card muted">همه‌چیز مرتب است ✅</div>'

    rows = []
    for s in studs:
        t = stats[s["id"]]
        rows.append([link(f"/student/{s['id']}", s["full_name"]), groups_of(conn, s["id"]), stat_bar(t),
                     f'{fa(t["on_time"])} / {fa(t["late"])} / {fa(t["missed"])}', progress(t["current"], n), fa(t["badges"]),
                     fa(t["points"]) + (f' <span class="muted">(+{fa(t["points_pending"])})</span>' if t["points_pending"] else "")])
    main_tbl = (f'<input class="search" data-table="t-class" placeholder="جست‌وجوی نام یا گروه…">' +
                table(["دانش‌آموز", "گروه", "توزیع وضعیت", "به‌موقع / تاخیر / ارسال‌نشده", f"مسیر نشان بعدی ({fa(n)})", "نشان", "امتیاز"], rows, "t-class")) if rows \
        else '<div class="card muted">هنوز دانش‌آموزی ثبت نشده است.</div>'

    rec = conn.execute("SELECT s.*, st.full_name, a.title FROM submissions s JOIN students st ON st.id=s.student_id "
                       "JOIN assignments a ON a.id=s.assignment_id WHERE s.state='final' ORDER BY s.submitted_ts DESC LIMIT 10").fetchall()
    rec_rows = [[link(f"/student/{r['student_id']}", r["full_name"]), link(f"/assignment/{r['assignment_id']}", r["title"]),
                 chip("on_time") if r["on_time"] else chip("late", r["over_minutes"] or 0),
                 f'<span class="nowrap">{esc(J.fmt_short(r["submitted_ts"]))}</span>'] for r in rec]
    rec_html = table(["دانش‌آموز", "تکلیف", "وضعیت", "زمان ارسال"], rec_rows) if rec_rows else '<div class="card muted">هنوز ارسالی ثبت نشده است.</div>'

    body = (f'<h1>داشبورد</h1><p class="sub">وضعیت امروز — {esc(J.fmt(now))}</p><div class="grid">{cards}</div>'
            f'<div class="two"><div><h2>مهلت‌های پیش‌رو</h2>{up_html}</div><div><h2>نیازمند پیگیری</h2>{need_html}</div></div>'
            f'<h2>وضعیت دانش‌آموزان پایه‌ی ششم (تکالیف الزامی)</h2>{main_tbl}<h2>آخرین ارسال‌ها</h2>{rec_html}'
            f'<p class="muted" style="margin-top:18px"><a class="btn ghost" href="/export.xlsx">📗 دریافت اکسل کامل</a></p>')
    return layout("داشبورد", body, "/", logo=logo)


def students_page(conn, cfg, now, logo=False) -> str:
    n = cfg.streak_size
    rows = []
    for s in conn.execute("SELECT * FROM students ORDER BY active DESC, grade, full_name").fetchall():
        state = "فعال" if s["active"] else "غیرفعال"
        joined = "✔ وارد شده" if s["chat_id"] else "🕓 هنوز وارد نشده"
        grade = "نهم" if s["grade"] == 9 else "ششم"
        if s["grade"] == 9:
            r = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(pages),0) p FROM book_reports WHERE student_id=? AND status='active'", (s["id"],)).fetchone()
            rows.append([link(f"/student/{s['id']}", s["full_name"]), esc(grade), '<span class="muted">—</span>', esc(f"{state} | {joined}"),
                         '<span class="muted">—</span>', f'{fa(r["n"])} گزارش | {fa(r["p"])} صفحه', "—"])
            continue
        t = R.student_stats(conn, s["id"], now, n)
        rows.append([link(f"/student/{s['id']}", s["full_name"]), esc(grade), groups_of(conn, s["id"]), esc(f"{state} | {joined}"),
                     stat_bar(t), f'{fa(t["on_time"])} / {fa(t["late"])} / {fa(t["missed"])} / {fa(t["excused"])}',
                     f'{fa(t["badges"])} نشان | {fa(t["points"])} امتیاز'])
    body = ('<h1>دانش‌آموزان</h1><p class="sub">برای دیدن گزارش کامل هر نفر روی نامش بزن.</p>'
            '<input class="search" data-table="t-st" placeholder="جست‌وجوی نام یا گروه…">' +
            table(["نام", "پایه", "گروه", "وضعیت", "توزیع", "به‌موقع / تاخیر / ارسال‌نشده / عذر (یا گزارش مطالعه)", "نشان و امتیاز"], rows, "t-st"))
    return layout("دانش‌آموزان", body, "/students", logo=logo)


def student_page(conn, cfg, now, sid: int, logo=False):
    s = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if not s:
        return None
    n = cfg.streak_size
    if s["grade"] == 9:
        return student_book_page(conn, s, logo)
    t = R.student_stats(conn, sid, now, n)
    chips = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(l)}</span></div>' for v, l in [
        (t["on_time"], "به‌موقع"), (t["late"], "با تاخیر"), (t["missed"], "ارسال‌نشده"), (t["excused"], "عذر موجه"),
        (t["badges"], "نشان"), (t["extra_done"], "اختیاری/امتیازی انجام‌شده"),
        (t["points"], "امتیاز تأییدشده"), (t["points_pending"], "امتیاز در انتظار تأیید")])
    asg_rows = []
    for a in reversed(R.targets_for_student(conn, sid)):
        st = R.student_status(conn, a, sid, now)
        sub = st["sub"]
        asg_rows.append([esc(R.KIND_ICON[a["kind"]] + " " + R.KIND_LABEL[a["kind"]]), link(f"/assignment/{a['id']}", a["title"]),
                         f'<span class="nowrap">{esc(J.fmt_short(R.effective_deadline(conn, a, sid)))}</span>',
                         chip(st["code"], st["over"]),
                         f'<span class="nowrap">{esc(J.fmt_short(sub["submitted_ts"]))}</span>' if sub else "—",
                         files_html(conn, sub)])
    asg_html = table(["نوع", "تکلیف", "مهلت", "وضعیت", "زمان ارسال", "فایل‌ها"], asg_rows) if asg_rows else '<div class="card muted">تکلیفی برای این دانش‌آموز نیست.</div>'
    badges = conn.execute("SELECT title, awarded_ts FROM badges WHERE student_id=? ORDER BY awarded_ts DESC", (sid,)).fetchall()
    b_html = "".join(f'<div class="row"><span>{esc(b["title"])}</span><span class="muted nowrap">{esc(J.fmt_short(b["awarded_ts"]))}</span></div>' for b in badges) or '<span class="muted">هنوز نشانی نگرفته است.</span>'
    fbs = conn.execute("SELECT f.*, a.title FROM feedback f LEFT JOIN assignments a ON a.id=f.assignment_id WHERE f.student_id=? ORDER BY f.ts DESC LIMIT 20", (sid,)).fetchall()
    f_html = "".join(f'<div class="row"><span>{esc(f["text"])}' + (f' <span class="muted">({esc(f["title"])})</span>' if f["title"] else "") +
                     f'</span><span class="muted nowrap">{esc(J.fmt_short(f["ts"]))}</span></div>' for f in fbs) or '<span class="muted">بازخوردی ثبت نشده است.</span>'
    ledger = conn.execute("SELECT * FROM points_ledger WHERE student_id=? ORDER BY id DESC LIMIT 15", (sid,)).fetchall()
    mark = {"approved": '<span class="chip ok">تأییدشده</span>', "pending": '<span class="chip wait">در انتظار</span>', "rejected": '<span class="chip miss">ردشده</span>'}
    l_rows = [[("+" if r["delta"] > 0 else "") + fa(r["delta"]), esc(r["reason"]), mark[r["status"]],
               f'<span class="nowrap">{esc(J.fmt_short(r["created_ts"]))}</span>'] for r in ledger]
    l_html = table(["امتیاز", "دلیل", "وضعیت", "زمان"], l_rows) if l_rows else '<div class="card muted">هنوز امتیازی ثبت نشده است.</div>'
    state = "" if s["active"] else ' <span class="chip exc">غیرفعال</span>'
    body = (f'<p><a href="/students">← همه‌ی دانش‌آموزان</a></p><h1>{esc(s["full_name"])}{state}</h1>'
            f'<p class="sub">گروه‌ها: {groups_of(conn, sid)}</p><div class="grid">{chips}</div>'
            f'<h2>مسیر نشان بعدی</h2><div class="card">{progress(t["current"], n)}<p class="muted" style="margin:6px 0 0">'
            f'{fa(t["current"])} از {fa(n)} تکلیف الزامی پشت‌سرهم و به‌موقع</p></div>'
            f'<h2>تکالیف</h2>{asg_html}<h2>دفتر امتیاز</h2>{l_html}'
            f'<div class="two"><div><h2>نشان‌ها</h2><div class="card">{b_html}</div></div>'
            f'<div><h2>بازخوردها</h2><div class="card">{f_html}</div></div></div>'
            f'<p style="margin-top:16px"><a class="btn ghost" href="/zip-student/{sid}">📥 دانلود همه‌ی پاسخ‌های او (ZIP)</a></p>')
    return layout(s["full_name"], body, "/students", logo=logo)


def assignments_page(conn, cfg, now, logo=False) -> str:
    rows = []
    for a in conn.execute("SELECT * FROM assignments ORDER BY deadline_ts DESC").fetchall():
        c = tally(conn, a, now)
        total = sum(len(v) for v in c.values())
        done = len(c["on_time"]) + len(c["late"])
        cancelled = ' <span class="chip exc">لغوشده</span>' if a["status"] != "active" else ""
        tgt = "همه" if a["target_all"] else esc("، ".join(r["name"] for r in conn.execute(
            "SELECT g.name FROM groups g JOIN assignment_groups ag ON ag.group_id=g.id WHERE ag.assignment_id=?", (a["id"],))) or "گروه")
        rows.append([esc(R.KIND_ICON[a["kind"]] + " " + R.KIND_LABEL[a["kind"]]), link(f"/assignment/{a['id']}", a["title"]) + cancelled,
                     tgt, f'<span class="nowrap">{esc(J.fmt_short(a["deadline_ts"]))}</span>',
                     f"{fa(done)} از {fa(total)}", f"{fa(len(c['on_time']))} / {fa(len(c['late']))}"])
    body = ('<h1>تکالیف</h1><p class="sub">جدیدترین مهلت اول</p>' +
            (table(["نوع", "تکلیف", "مخاطب", "مهلت", "ارسال‌شده", "به‌موقع / با تاخیر"], rows) if rows else '<div class="card muted">هنوز تکلیفی ثبت نشده است.</div>'))
    return layout("تکالیف", body, "/assignments", logo=logo)


def assignment_page(conn, cfg, now, aid: int, logo=False):
    a = conn.execute("SELECT * FROM assignments WHERE id=?", (aid,)).fetchone()
    if not a:
        return None
    c = tally(conn, a, now)
    total = sum(len(v) for v in c.values())
    cards = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(l)}</span></div>' for v, l in [
        (len(c["on_time"]), "به‌موقع"), (len(c["late"]), "با تاخیر"), (len(c["none"]), "ارسال‌نشده"), (len(c["excused"]), "عذر موجه")])
    rows = []
    for key in ("on_time", "late", "none", "excused"):
        for s, st in c[key]:
            sub = st["sub"]
            rows.append([link(f"/student/{s['id']}", s["full_name"]), chip(st["code"], st["over"]),
                         f'<span class="nowrap">{esc(J.fmt_short(sub["submitted_ts"]))}</span>' if sub else "—", files_html(conn, sub)])
    tgt = "همه‌ی دانش‌آموزان" if a["target_all"] else "گروه: " + (" ، ".join(r["name"] for r in conn.execute(
        "SELECT g.name FROM groups g JOIN assignment_groups ag ON ag.group_id=g.id WHERE ag.assignment_id=?", (aid,))) or "—")
    atts = conn.execute("SELECT * FROM assignment_files WHERE assignment_id=? ORDER BY id", (aid,)).fetchall()
    att_html = ""
    if atts:
        items = "".join((f'<a href="/afile/{f["id"]}" target="_blank"><img loading="lazy" src="/afile/{f["id"]}" alt="ضمیمه"></a>'
                         if Path(f["path"]).suffix.lower() in IMG_EXT else
                         f'<a class="pill" href="/afile/{f["id"]}" target="_blank">{esc(f["name"] or "فایل")}</a>') for f in atts)
        att_html = f'<h2>ضمیمه‌ی تکلیف</h2><div class="card"><div class="thumbs">{items}</div></div>'
    desc = f'<div class="card" style="white-space:pre-wrap">{esc(a["description"])}</div>' if a["description"] else ""
    cancelled = ' <span class="chip exc">لغوشده</span>' if a["status"] != "active" else ""
    body = (f'<p><a href="/assignments">← همه‌ی تکالیف</a></p><h1>{esc(R.KIND_ICON[a["kind"]])} {esc(a["title"])}{cancelled}</h1>'
            f'<p class="sub">{esc(R.KIND_LABEL[a["kind"]])} | {esc(tgt)} | مهلت: {esc(J.fmt(a["deadline_ts"]))} | '
            f'تاخیر مجاز {fa(a["grace_min"])} دقیقه، ارسال با تاخیر تا {fa(a["late_hours"])} ساعت</p>{desc}'
            f'<div class="grid" style="margin-top:12px">{cards}</div>{att_html}'
            f'<h2>وضعیت دانش‌آموزان ({fa(total)} نفر)</h2>'
            f'<input class="search" data-table="t-as" placeholder="جست‌وجوی نام…">' +
            table(["دانش‌آموز", "وضعیت", "زمان ارسال", "پاسخ"], rows, "t-as") +
            f'<p style="margin-top:16px"><a class="btn ghost" href="/zip/{aid}">📥 دانلود همه‌ی پاسخ‌ها (ZIP)</a></p>')
    return layout(a["title"], body, "/assignments", logo=logo)


def badges_page(conn, cfg, now, logo=False) -> str:
    board = conn.execute("SELECT s.id, s.full_name, COUNT(b.id) n FROM students s LEFT JOIN badges b ON b.student_id=s.id "
                         "WHERE s.active=1 GROUP BY s.id ORDER BY n DESC, s.full_name").fetchall()
    rows = [[fa(i), link(f"/student/{r['id']}", r["full_name"]), "🏅 " + fa(r["n"])] for i, r in enumerate(board, 1)]
    latest = conn.execute("SELECT b.*, s.full_name FROM badges b JOIN students s ON s.id=b.student_id ORDER BY b.awarded_ts DESC LIMIT 30").fetchall()
    l_rows = [[link(f"/student/{r['student_id']}", r["full_name"]), esc(r["title"]), f'<span class="nowrap">{esc(J.fmt_short(r["awarded_ts"]))}</span>'] for r in latest]
    body = ('<h1>نشان‌ها</h1><p class="sub">جدول تعداد نشان‌ها و آخرین نشان‌های صادرشده</p>'
            '<div class="two"><div><h2>جدول نشان‌ها</h2>' + table(["#", "دانش‌آموز", "نشان"], rows) + '</div>'
            '<div><h2>آخرین نشان‌ها</h2>' + (table(["دانش‌آموز", "نشان", "زمان"], l_rows) if l_rows else '<div class="card muted">هنوز نشانی صادر نشده است.</div>') + '</div></div>')
    return layout("نشان‌ها", body, "/badges", logo=logo)


def feedback_page(conn, cfg, now, logo=False) -> str:
    fbs = conn.execute("SELECT f.*, s.full_name, a.title FROM feedback f JOIN students s ON s.id=f.student_id "
                       "LEFT JOIN assignments a ON a.id=f.assignment_id ORDER BY f.ts DESC LIMIT 150").fetchall()
    rows = [[link(f"/student/{f['student_id']}", f["full_name"]), esc(f["title"] or "—"), esc(f["text"]),
             f'<span class="nowrap">{esc(J.fmt_short(f["ts"]))}</span>'] for f in fbs]
    body = ('<h1>بازخوردها</h1><p class="sub">آخرین بازخوردهایی که به دانش‌آموزان داده شده</p>' +
            (table(["دانش‌آموز", "تکلیف", "بازخورد", "زمان"], rows) if rows else '<div class="card muted">بازخوردی ثبت نشده است.</div>'))
    return layout("بازخوردها", body, "/feedback", logo=logo)


def audit_page(conn, cfg, now, logo=False) -> str:
    rows_db = conn.execute("SELECT * FROM audit ORDER BY ts DESC LIMIT 200").fetchall()
    rows = [[f'<span class="nowrap">{esc(J.fmt_short(r["ts"]))}</span>', esc(fa(r["admin_id"]) if r["admin_id"] else "—"),
             esc(ACTION_LABELS.get(r["action"], r["action"])), esc(r["details"] or "")] for r in rows_db]
    body = ('<h1>گزارش فعالیت مدیران</h1><p class="sub">۲۰۰ کار آخر؛ برای ردگیری و اطمینان، نه برای محدودکردن.</p>' +
            (table(["زمان", "شناسه‌ی مدیر", "کار", "جزئیات"], rows) if rows else '<div class="card muted">فعالیتی ثبت نشده است.</div>'))
    return layout("گزارش فعالیت", body, "/audit", logo=logo)


def not_found(logo=False) -> str:
    return layout("پیدا نشد", '<div class="card"><h1>صفحه پیدا نشد</h1><p><a href="/">بازگشت به داشبورد</a></p></div>', logo=logo)


# ====================== پایه‌ی نهم: باشگاه کتابخوانی ======================
def _pair(r) -> str:
    from .books import pair_label
    return pair_label(r["day1_ts"], r["day2_ts"])


def student_book_page(conn, s, logo=False) -> str:
    rows_db = conn.execute("SELECT * FROM book_reports WHERE student_id=? AND status='active' ORDER BY day2_ts DESC, id DESC", (s["id"],)).fetchall()
    pages = sum(r["pages"] for r in rows_db)
    books_n = len({reports._norm_book(r["book"]) for r in rows_db})
    cards = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(t)}</span></div>' for v, t in [
        (len(rows_db), "گزارش"), (pages, "مجموع صفحه"), (books_n, "کتاب")])
    rows = [[f'<span class="nowrap">{esc(_pair(r))}</span>', esc(r["book"]), f'{fa(r["from_page"])} تا {fa(r["to_page"])}',
             fa(r["pages"]), "✅" if r["posted"] else "—"] for r in rows_db]
    tbl = table(["روزها", "کتاب", "صفحه‌ها", "تعداد", "ارسال به گروه"], rows) if rows else '<div class="card muted">هنوز گزارشی ثبت نشده است.</div>'
    state = "" if s["active"] else ' <span class="chip exc">غیرفعال</span>'
    body = (f'<p><a href="/students">← همه‌ی دانش‌آموزان</a></p><h1>{esc(s["full_name"])}{state}</h1>'
            f'<p class="sub">پایه‌ی نهم — باشگاه کتابخوانی</p><div class="grid">{cards}</div><h2>گزارش‌های مطالعه</h2>{tbl}')
    return layout(s["full_name"], body, "/students", logo=logo)


def books_page(conn, cfg, now, days=None, logo=False) -> str:
    since = J.noon(now) - days * 86400 if days else None
    st = reports.book_stats(conn, since)
    labels = [(None, "همه‌ی زمان‌ها"), (7, "۷ روز اخیر"), (30, "۳۰ روز اخیر"), (90, "۹۰ روز اخیر")]
    filt = " ".join(f'<a class="pill" href="/books{"?days=" + str(d) if d else ""}"'
                    f'{" style=\"font-weight:700;background:#cfe8d6\"" if d == days else ""}>{esc(t)}</a>' for d, t in labels)
    cards = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(t)}</span></div>' for v, t in [
        (f'{st["readers"]} از {len(st["students"])}', "دانش‌آموز گزارش داده‌اند"), (st["total_reports"], "گزارش"),
        (st["total_pages"], "مجموع صفحه"), (len(st["books"]), "کتاب")])
    srows = []
    for p in st["students"]:
        last = J.fmt_short(p["last"]).split(" ")[0] if p["last"] else "—"
        srows.append([link(f"/student/{p['student']['id']}", p["student"]["full_name"]), fa(p["reports"]), fa(p["pages"]),
                      fa(len(p["books"])), fa(len(p["weeks"])), last])
    stbl = (table(["دانش‌آموز", "گزارش", "مجموع صفحه", "کتاب", "هفته‌های فعال", "آخرین گزارش"], srows)
            if srows else '<div class="card muted">دانش‌آموز پایه‌ی نهمی ثبت نشده است.</div>')
    mx = max([w[1][0] for w in st["weekly"]] or [1])
    bars = "".join(f'<div class="row"><span class="nowrap">{esc(J.fmt_short(w).split(" ")[0])}</span>'
                   f'<span style="flex:1;margin:0 10px"><i style="display:block;height:12px;border-radius:6px;background:#3aa066;width:{v[0] * 100 / mx:.1f}%"></i></span>'
                   f'<span class="nowrap">{fa(v[0])} صفحه | {fa(v[1])} گزارش</span></div>' for w, v in st["weekly"][-12:])
    chart = f'<div class="card">{bars}</div>' if bars else '<div class="card muted">هنوز داده‌ای نیست.</div>'
    btbl = table(["کتاب", "خواننده", "مجموع صفحه"], [[esc(b["title"]), fa(len(b["readers"])), fa(b["pages"])] for b in st["books"][:20]]) \
        if st["books"] else '<div class="card muted">هنوز کتابی ثبت نشده است.</div>'
    rec = [[link(f"/student/{r['student_id']}", r["full_name"]), f'<span class="nowrap">{esc(_pair(r))}</span>', esc(r["book"]),
            f'{fa(r["from_page"])} تا {fa(r["to_page"])} ({fa(r["pages"])})', "✅" if r["posted"] else "—"]
           for r in reversed(st["rows"][-20:])]
    rtbl = table(["دانش‌آموز", "روزها", "کتاب", "صفحه‌ها", "گروه"], rec) if rec else '<div class="card muted">هنوز گزارشی نیست.</div>'
    body = (f'<h1>باشگاه کتابخوانی (پایه‌ی نهم)</h1><p class="sub">{filt}</p><div class="grid">{cards}</div>'
            f'<h2>هر دانش‌آموز</h2>{stbl}<h2>صفحه‌های خوانده‌شده در هر هفته (۱۲ هفته‌ی اخیر)</h2>{chart}'
            f'<div class="two"><div><h2>کتاب‌ها</h2>{btbl}</div></div><h2>آخرین گزارش‌ها</h2>{rtbl}'
            f'<p style="margin-top:16px"><a class="btn ghost" href="/books.xlsx{"?days=" + str(days) if days else ""}">📗 دریافت اکسل کتابخوانی</a></p>')
    return layout("باشگاه کتابخوانی", body, "/books", logo=logo)


def points_page(conn, cfg, now, logo=False) -> str:
    n = cfg.streak_size
    rows = []
    for s in students_active(conn):
        a, p = R.points_total(conn, s["id"])
        rows.append([link(f"/student/{s['id']}", s["full_name"]), fa(a), fa(p) if p else "—"])
    pending = conn.execute("SELECT l.*, s.full_name FROM points_ledger l JOIN students s ON s.id=l.student_id "
                           "WHERE l.status='pending' ORDER BY l.id").fetchall()
    p_rows = [[link(f"/student/{r['student_id']}", r["full_name"]), esc(r["reason"]), "+" + fa(r["delta"]),
               f'<span class="nowrap">{esc(J.fmt_short(r["created_ts"]))}</span>'] for r in pending]
    ptbl = table(["دانش‌آموز", "دلیل", "امتیاز", "زمان"], p_rows) if p_rows else '<div class="card muted">امتیاز در انتظار تأییدی نیست ✅</div>'
    note = ('<p class="note">تأیید، رد و تغییر دستی امتیازها فقط در بات انجام می‌شود (پنل فقط‌خواندنی است): '
            'پنل مدیریت ← «⭐ تأیید امتیازها».</p>')
    body = (f'<h1>امتیازها</h1><p class="sub">امتیاز تأییدشده‌ی هر دانش‌آموز پایه‌ی ششم</p>{note}'
            f'<div class="two"><div><h2>در انتظار تأیید ({fa(len(pending))})</h2>{ptbl}</div>'
            f'<div><h2>جدول امتیاز</h2>{table(["دانش‌آموز", "تأییدشده", "در انتظار"], rows)}</div></div>')
    return layout("امتیازها", body, "/points", logo=logo)
