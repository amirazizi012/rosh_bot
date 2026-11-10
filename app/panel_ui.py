"""صفحه‌های پنل وب: همه‌ی متن‌ها فارسی، راست‌چین و با ارقام فارسی.
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
.inc{background:#ffe9d6;color:#a14a00}.exc{background:var(--exb);color:var(--ex)}.wait{background:var(--wtb);color:var(--wt)}
.kbar{display:flex;height:10px;width:150px;border-radius:6px;overflow:hidden;background:#e8ede6}
.kbar i{display:block;height:100%}.k-ok{background:#3aa066}.k-late{background:#e5a72b}.k-miss{background:#d9534f}.k-exc{background:#9aa9b0}.k-inc{background:#e67e22}
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
form.f{display:inline-block;margin:2px 0}form.f.blk{display:block}
form.f input[type=text],form.f input:not([type]),form.f select,form.f textarea{padding:6px 10px;border:1px solid var(--line);border-radius:9px;font:inherit;background:#fff;max-width:100%}
form.f textarea{width:100%;min-height:90px}
button.b{background:var(--g);color:#fff;border:0;border-radius:9px;padding:6px 14px;font:inherit;font-weight:700;cursor:pointer}
button.b:hover{background:var(--gd)}button.b.warn{background:#c0392b}button.b.ghost{background:#fff;color:var(--gd);border:1px solid var(--g)}
.flash{border-radius:12px;padding:10px 14px;margin:0 0 14px}.flash.ok{background:var(--okb);color:var(--ok)}.flash.err{background:var(--msb);color:var(--ms)}
form.f .chk{display:flex;flex-wrap:wrap;gap:6px 14px;margin:6px 0}form.f input[type=password],form.f input[type=file]{max-width:100%}
details.mng{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px 16px;margin:12px 0}
details.mng summary{cursor:pointer;font-weight:700;color:var(--gd)}
.chk{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0}.chk label{white-space:nowrap}
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
document.addEventListener('submit',function(e){
  var m=e.target.getAttribute('data-confirm');
  if(m && !window.confirm(m)) e.preventDefault();
});
"""

NAV = [("/", "داشبورد"), ("/students", "دانش‌آموزان"), ("/assignments", "تکالیف"), ("/groups", "گروه‌ها"), ("/points", "امتیازها"),
       ("/badges", "نشان‌ها"), ("/books", "باشگاه کتابخوانی"), ("/messages", "پیام‌ها"), ("/receipts", "رسیدها"), ("/feedback", "بازخوردها"), ("/admins", "مدیران"), ("/audit", "فعالیت مدیران")]


def form(action: str, inner: str, back: str, label: str, cls: str = "", confirm: str = "", block: bool = False, multipart: bool = False) -> str:
    """فرم تغییر؛ `{{CSRF}}` هنگام ارسال با توکن نشست جایگزین می‌شود. back = نشانیِ برگشت (فقط مسیر داخلی)."""
    conf = f' data-confirm="{esc(confirm)}"' if confirm else ""
    enc = ' enctype="multipart/form-data"' if multipart else ""
    return (f'<form class="f{" blk" if block else ""}" method="post" action="/act/{action}"{conf}{enc}>'
            f'<input type="hidden" name="_csrf" value="{{{{CSRF}}}}"><input type="hidden" name="back" value="{esc(back)}">'
            f'{inner}<button class="b {cls}">{esc(label)}</button></form>')


def hid(**kw) -> str:
    return "".join(f'<input type="hidden" name="{k}" value="{esc(v)}">' for k, v in kw.items())


STATUS_OPTS = [("ok", "✅ به‌موقع"), ("late", "⏰ با تاخیر"), ("inc", "⚠️ ناقص"), ("miss", "❌ ارسال‌نشده"), ("auto", "↩ خودکار")]


def status_form(aid: int, sid: int, back: str) -> str:
    opts = "".join(f'<option value="{k}">{esc(t)}</option>' for k, t in STATUS_OPTS)
    return form("status", hid(aid=aid, sid=sid) + f'<select name="code">{opts}</select> <input name="note" placeholder="توضیح (برای ناقص)" size="14">',
                back, "ثبت", "ghost")


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
            f'<nav>{links}</nav>{out}</div></header><main><!--FLASH-->{persian_digits(body)}</main>'
            f'<script src="/static/panel.js"></script></body></html>')


def login_page(error: str = "", logo: bool = False, password: bool = False) -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    body = ('<div class="login card"><h1>ورود به پنل رشد</h1>'
            f'<p class="sub">{"با رمز پنل و کد یک‌بارمصرفی که بات می‌دهد وارد شو." if password else "با کد یک‌بارمصرفی که بات می‌دهد وارد شو."}</p>'
            f'{err}<form method="post" action="/login">'
             + ('<input name="password" type="password" autocomplete="current-password" placeholder="رمز پنل" autofocus>' if password else '') + '<input name="code" inputmode="numeric" autocomplete="off" maxlength="12" placeholder="کد ۸ رقمی" autofocus>'
            '<button>ورود</button></form>'
            '<p class="muted" style="font-size:13px;margin-top:14px">در بات بله: پنل مدیریت ← «🌐 ورود به پنل وب» را بزن و کد را اینجا وارد کن. '
            'کد محدودیت زمانی ندارد ولی فقط یک‌بار قابل استفاده است.</p></div>')
    return layout("ورود", body, logged=False, logo=logo)


# ---------- اجزای مشترک ----------
def chip(code: str, over: int = 0, edited: bool = False) -> str:
    cls = {"on_time": "ok", "late": "late", "excused": "exc", "waiting": "wait", "overdue": "miss", "missed": "miss",
           "incomplete": "inc"}[code]
    label = {"on_time": "به‌موقع", "late": f"تاخیر {duration(over)}" if over else "با تاخیر", "excused": "عذر موجه",
             "waiting": "در انتظار", "overdue": "ارسال‌نشده", "missed": "ارسال‌نشده", "incomplete": "ناقص"}[code]
    return f'<span class="chip {cls}">{esc(label)}{" ✎" if edited else ""}</span>'


def stat_bar(t: dict) -> str:
    total = t["on_time"] + t["late"] + t["missed"] + t["excused"] + t["incomplete"]
    if not total:
        return '<span class="muted">—</span>'
    def w(x): return f"{x * 100 / total:.1f}%"
    return ('<div class="kbar" title="به‌موقع / با تاخیر / ناقص / ارسال‌نشده / عذر">'
            f'<i class="k-ok" style="width:{w(t["on_time"])}"></i><i class="k-late" style="width:{w(t["late"])}"></i>'
            f'<i class="k-inc" style="width:{w(t["incomplete"])}"></i>'
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


def students_active(conn, grades=(6,)):
    grades = tuple(grades) if isinstance(grades, (tuple, list)) else (grades,)
    return conn.execute("SELECT * FROM students WHERE active=1 AND grade IN (%s) ORDER BY grade, full_name" % ",".join("?" * len(grades)),
                        grades).fetchall()


TARGET_LABEL = {0: "ششم و هفتم", 6: "همه‌ی ششم", 7: "همه‌ی هفتم", 9: "همه‌ی نهم", 99: "همه‌ی پایه‌ها"}


def groups_of(conn, sid) -> str:
    g = reports.group_names(conn, sid)
    return "".join(f'<span class="pill">{esc(x)}</span>' for x in g.split("، ")) if g else '<span class="muted">—</span>'


def tally(conn, a, now):
    c = {"on_time": [], "late": [], "incomplete": [], "none": [], "excused": []}
    for s in R.target_students(conn, a):
        st = R.student_status(conn, a, s["id"], now)
        key = {"on_time": "on_time", "late": "late", "excused": "excused", "incomplete": "incomplete"}.get(st["code"], "none")
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
    studs = students_active(conn, R.HOMEWORK_GRADES)
    stats = {s["id"]: R.student_stats(conn, s["id"], now, n) for s in studs}
    joined = sum(1 for s in studs if s["chat_id"])
    n_asg = conn.execute("SELECT COUNT(*) c FROM assignments WHERE status='active'").fetchone()["c"]
    day = J.to_dt(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today = conn.execute("SELECT COUNT(*) c FROM submissions WHERE state='final' AND submitted_ts>=?", (int(day),)).fetchone()["c"]
    n_badges = conn.execute("SELECT COUNT(*) c FROM badges WHERE status='approved'").fetchone()["c"]
    n_pending = (conn.execute("SELECT COUNT(*) c FROM points_ledger WHERE status='pending' AND kind<>'badge'").fetchone()["c"]
                 + conn.execute("SELECT COUNT(*) c FROM badges WHERE status='pending'").fetchone()["c"])
    cards = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(t)}</span></div>' for v, t in [
        (f"{joined} از {len(studs)}", "دانش‌آموز (ششم و هفتم) وارد شده به بات"), (n_asg, "تکلیف فعال"),
        (today, "ارسال امروز"), (n_badges, "نشان صادرشده"), (n_pending, "نشان/امتیاز در انتظار تأیید مدیر")])

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
        gam = s["grade"] in R.GAMIFIED_GRADES
        dash = '<span class="muted">—</span>'
        rows.append([link(f"/student/{s['id']}", s["full_name"]) + ("" if gam else f' <span class="muted">({esc(R.GRADE_NAME.get(s["grade"], ""))})</span>'), groups_of(conn, s["id"]), stat_bar(t),
                     f'{fa(t["on_time"])} / {fa(t["late"])} / {fa(t["missed"])}' + (f' <span class="chip inc">ناقص {fa(t["incomplete"])}</span>' if t["incomplete"] else ""),
                     progress(t["current"], n) if gam else dash,
                     (fa(t["badges"]) + (f' <span class="muted">(+{fa(t["badges_pending"])} در انتظار)</span>' if t["badges_pending"] else "")) if gam else dash,
                     (fa(t["points"]) + (f' <span class="muted">(+{fa(t["points_pending"])})</span>' if t["points_pending"] else "")) if gam else dash])
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
            f'<h2>وضعیت دانش‌آموزان (تکالیف الزامی)</h2>{main_tbl}<h2>آخرین ارسال‌ها</h2>{rec_html}'
            f'<p class="muted" style="margin-top:18px"><a class="btn ghost" href="/export.xlsx">📗 دریافت اکسل کامل</a></p>')
    return layout("داشبورد", body, "/", logo=logo)


def _uname(s) -> str:
    return f' <span class="muted" dir="ltr">@{esc(s["username"])}</span>' if s["username"] else ""


def students_page(conn, cfg, now, logo=False) -> str:
    n = cfg.streak_size
    rows = []
    for s in conn.execute("SELECT * FROM students ORDER BY active DESC, grade, full_name").fetchall():
        state = "فعال" if s["active"] else "غیرفعال"
        joined = "✔ وارد شده" if s["chat_id"] else "🕓 هنوز وارد نشده" + (f" | 🔑 {fa(s['code'])}" if s["code"] else "")
        grade = R.GRADE_NAME.get(s["grade"], "ششم")
        t = R.student_stats(conn, s["id"], now, n)
        rows.append([link(f"/student/{s['id']}", s["full_name"]) + _uname(s), esc(grade), groups_of(conn, s["id"]), esc(f"{state} | {joined}"),
                     stat_bar(t), f'{fa(t["on_time"])} / {fa(t["late"])} / {fa(t["missed"])} / {fa(t["excused"])}' + (f' <span class="chip inc">ناقص {fa(t["incomplete"])}</span>' if t["incomplete"] else ""),
                     f'{fa(t["badges"])} نشان | {fa(t["points"])} امتیاز' if s["grade"] in R.GAMIFIED_GRADES else "—"])
    grade_opts = "".join(f'<option value="{g}">{esc(nm)}</option>' for g, nm in sorted(R.GRADE_NAME.items()))
    add = ('<details class="mng"><summary>➕ افزودن دانش‌آموز</summary>' +
           form("students_add", f'<p class="muted">هر خط یک نفر: <b>نام | @یوزرنیم بله | گروه</b> (یوزرنیم و گروه اختیاری؛ حداکثر ۶۰ نفر). هر دانش‌آموز یک «رمز ۶ رقمی» هم دارد؛ بدون یوزرنیم با همان رمز وارد بات می‌شود و رمز بعد از افزودن نشان داده می‌شود.</p>'
                f'<textarea name="text" placeholder="علی رضایی | @ali_01"></textarea><br>پایه: <select name="grade">{grade_opts}</select> ',
                "/students", "افزودن", block=True) + '</details>')
    body = ('<h1>دانش‌آموزان</h1><p class="sub">برای دیدن گزارش کامل هر نفر روی نامش بزن.</p>' + add +
            '<input class="search" data-table="t-st" placeholder="جست‌وجوی نام یا گروه…">' +
            table(["نام", "پایه", "گروه", "وضعیت", "توزیع", "به‌موقع / تاخیر / ارسال‌نشده / عذر", "نشان و امتیاز"], rows, "t-st"))
    return layout("دانش‌آموزان", body, "/students", logo=logo)


def student_page(conn, cfg, now, sid: int, logo=False):
    s = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if not s:
        return None
    n = cfg.streak_size
    t = R.student_stats(conn, sid, now, n)
    gam = s["grade"] in R.GAMIFIED_GRADES            # نشان و امتیاز فقط برای پایه‌ی ششم
    stat_items = [(t["on_time"], "به‌موقع"), (t["late"], "با تاخیر"), (t["incomplete"], "ناقص"), (t["missed"], "ارسال‌نشده"),
                  (t["excused"], "عذر موجه"), (t["extra_done"], "تمرین بیشتر/امتیازی انجام‌شده")]
    if gam:
        stat_items += [(t["badges"], "نشان"), (t["points"], "امتیاز تأییدشده"), (t["points_pending"], "امتیاز در انتظار تأیید")]
    chips = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(l)}</span></div>' for v, l in stat_items)
    asg_rows = []
    for a in reversed(R.targets_for_student(conn, sid)):
        st = R.student_status(conn, a, sid, now)
        sub = st["sub"]
        asg_rows.append([esc(R.KIND_ICON[a["kind"]] + " " + R.KIND_LABEL[a["kind"]]), link(f"/assignment/{a['id']}", a["title"]),
                         f'<span class="nowrap">{esc(J.fmt_short(R.effective_deadline(conn, a, sid)))}</span>',
                         chip(st["code"], st["over"], bool(st.get("override"))),
                         f'<span class="nowrap">{esc(J.fmt_short(sub["submitted_ts"]))}</span>' if sub else "—",
                         files_html(conn, sub), status_form(a["id"], sid, f"/student/{sid}")])
    asg_html = table(["نوع", "تکلیف", "مهلت", "وضعیت", "زمان ارسال", "فایل‌ها", "ویرایش وضعیت"], asg_rows) if asg_rows else '<div class="card muted">تکلیفی برای این دانش‌آموز نیست.</div>'
    badges = conn.execute("SELECT id, title, awarded_ts, status FROM badges WHERE student_id=? ORDER BY awarded_ts DESC", (sid,)).fetchall()
    b_html = "".join(f'<div class="row"><span>{esc(b["title"])}{" <span class=\"chip wait\">در انتظار تأیید</span>" if b["status"] == "pending" else ""}</span><span class="muted nowrap">{esc(J.fmt_short(b["awarded_ts"]))} ' +
                     form("badge_delete", hid(bid=b["id"], sid=sid), f"/student/{sid}", "🗑 حذف", "warn", "این نشان حذف شود؟") + '</span></div>' for b in badges) or '<span class="muted">هنوز نشانی نگرفته است.</span>'
    fbs = conn.execute("SELECT f.*, a.title FROM feedback f LEFT JOIN assignments a ON a.id=f.assignment_id WHERE f.student_id=? ORDER BY f.ts DESC LIMIT 20", (sid,)).fetchall()
    f_html = "".join(f'<div class="row"><span>{esc(f["text"])}' + (f' <span class="muted">({esc(f["title"])})</span>' if f["title"] else "") +
                     f'</span><span class="muted nowrap">{esc(J.fmt_short(f["ts"]))}</span></div>' for f in fbs) or '<span class="muted">بازخوردی ثبت نشده است.</span>'
    ledger = conn.execute("SELECT * FROM points_ledger WHERE student_id=? ORDER BY id DESC LIMIT 15", (sid,)).fetchall()
    mark = {"approved": '<span class="chip ok">تأییدشده</span>', "pending": '<span class="chip wait">در انتظار</span>', "rejected": '<span class="chip miss">ردشده</span>'}
    l_rows = [[("+" if r["delta"] > 0 else "") + fa(r["delta"]), esc(r["reason"]), mark[r["status"]],
               f'<span class="nowrap">{esc(J.fmt_short(r["created_ts"]))}</span>'] for r in ledger]
    l_html = table(["امتیاز", "دلیل", "وضعیت", "زمان"], l_rows) if l_rows else '<div class="card muted">هنوز امتیازی ثبت نشده است.</div>'
    state = "" if s["active"] else ' <span class="chip exc">غیرفعال</span>'
    streak_html = (f'<h2>مسیر نشان بعدی</h2><div class="card">{progress(t["current"], n)}<p class="muted" style="margin:6px 0 0">'
                   f'{fa(t["current"])} از {fa(n)} تکلیف الزامی پشت‌سرهم و به‌موقع</p></div>') if gam else ""
    ledger_html = (f'<h2>دفتر امتیاز</h2>{l_html}' + form(
        "points_adjust", hid(sid=sid) + '<input name="delta" size="5" placeholder="+5 یا -3"> <input name="reason" size="26" placeholder="دلیل">',
        f"/student/{sid}", "ثبت تغییر دستی امتیاز", block=True)) if gam else ""
    bottom = (f'<div class="two"><div><h2>نشان‌ها</h2><div class="card">{b_html}</div></div>'
              f'<div><h2>بازخوردها</h2><div class="card">{f_html}</div></div></div>') if gam else \
        f'<h2>بازخوردها</h2><div class="card">{f_html}</div>'
    book_html = _book_section(conn, s) if s["grade"] == 9 else ""
    all_groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    mine = {r["group_id"] for r in conn.execute("SELECT group_id FROM student_groups WHERE student_id=?", (sid,))}
    g_inner = hid(sid=sid) + '<div class="chk">' + "".join(
        f'<label><input type="checkbox" name="groups" value="{g["id"]}"{" checked" if g["id"] in mine else ""}> {esc(g["name"])}</label>'
        for g in all_groups) + "</div>" if all_groups else ""
    asg_opts = '<option value="0">بدون تکلیف مشخص</option>' + "".join(f'<option value="{a["id"]}">{esc(a["title"])}</option>' for a in reversed(R.targets_for_student(conn, sid)))
    msgs = ('<details class="mng"><summary>💬 بازخورد و پیام به او</summary>' +
            form("feedback", hid(sid=sid) + f'<p>تکلیف: <select name="aid">{asg_opts}</select></p><textarea name="text" placeholder="متن بازخورد"></textarea>', f"/student/{sid}", "ثبت و ارسال بازخورد", block=True) +
            form("broadcast", hid(target=f"s{sid}") + '<textarea name="text" placeholder="پیام مستقیم (بدون ثبت در بازخوردها)"></textarea><p><input type="file" name="files" multiple></p>', f"/student/{sid}", "ارسال پیام",
                 confirm="پیام برای این دانش‌آموز فرستاده شود؟", block=True, multipart=True) + '</details>')
    rc = conn.execute("SELECT * FROM receipts WHERE student_id=? ORDER BY ts DESC LIMIT 20", (sid,)).fetchall()
    rc_rows = [[f'<span class="nowrap">{esc(J.fmt_short(r["ts"]))}</span>', esc(r["note"] or "—"),
                (f'<a class="pill" href="/rfile/{r["id"]}" target="_blank">دیدن فایل</a>' if r["path"] else '<span class="muted">متنی</span>'),
                ('<span class="chip wait">بررسی‌نشده</span>' if r["status"] == "new" else '<span class="chip ok">دریافت‌شده</span>'),
                form("receipt_seen", hid(rid=r["id"]), f"/student/{sid}", "✅ دریافت شد", "ghost") if r["status"] == "new" else ""] for r in rc]
    rc_html = (f'<h2>رسیدهای واریزی</h2>' + table(["زمان", "توضیح", "رسید", "وضعیت", ""], rc_rows)) if rc_rows else ""
    fbs = conn.execute("SELECT f.*, a.title FROM feedback f LEFT JOIN assignments a ON a.id=f.assignment_id WHERE f.student_id=? ORDER BY f.ts DESC", (sid,)).fetchall()
    fb_html = ('<h2 id="fb">بازخوردهایی که به او داده‌ای (' + fa(len(fbs)) + ')</h2>' +
               (table(["تاریخ و ساعت", "تکلیف", "بازخورد", "ارسال", ""], _fb_rows(fbs, f"/student/{sid}", with_student=False)) if fbs else '<div class="card muted">هنوز بازخوردی ثبت نشده.</div>'))
    manage = ('<details class="mng"><summary>✏ مدیریت دانش‌آموز</summary>' +
              form("student_rename", hid(sid=sid) + f'<input name="name" value="{esc(s["full_name"])}" size="24"> ', f"/student/{sid}", "تغییر نام") + "<br>" +
              form("student_username", hid(sid=sid) + f'<input name="username" value="{esc(s["username"] or "")}" size="20" dir="ltr" placeholder="@username (خالی = پاک)"> ',
                   f"/student/{sid}", "ثبت یوزرنیم") + "<br>" +
              form("student_toggle", hid(sid=sid), f"/student/{sid}", "⏸ غیرفعال‌سازی" if s["active"] else "▶ فعال‌سازی", "ghost") + " " +
              form("student_reset", hid(sid=sid), f"/student/{sid}", "🔓 بازنشانی ورود", "ghost",
                   "ورود دانش‌آموز بازنشانی شود؟ باید دوباره /start بزند.") +
              (("<br>" + form("student_groups", g_inner, f"/student/{sid}", "ذخیره‌ی گروه‌ها", block=True)) if all_groups else
               '<p class="muted">هنوز گروهی نساخته‌ای؛ از صفحه‌ی «گروه‌ها» بساز.</p>') + '</details>')
    body = (f'<p><a href="/students">← همه‌ی دانش‌آموزان</a></p><h1>{esc(s["full_name"])}{state}</h1>'
            f'<p class="sub">پایه‌ی {esc(R.GRADE_NAME.get(s["grade"], ""))} | گروه‌ها: {groups_of(conn, sid)} | رمز ورود به بات: <b dir="ltr">{fa(s["code"])}</b></p><div class="grid">{chips}</div>'
            f'{manage}{msgs}{fb_html}{rc_html}{streak_html}<h2>تکالیف</h2>{asg_html}{ledger_html}{bottom}{book_html}'
            f'<p style="margin-top:16px"><a class="btn ghost" href="/zip-student/{sid}">📥 دانلود همه‌ی پاسخ‌های او (ZIP)</a></p>')
    return layout(s["full_name"], body, "/students", logo=logo)


def assignments_page(conn, cfg, now, logo=False) -> str:
    rows = []
    for a in conn.execute("SELECT * FROM assignments ORDER BY deadline_ts DESC").fetchall():
        c = tally(conn, a, now)
        total = sum(len(v) for v in c.values())
        done = len(c["on_time"]) + len(c["late"])
        cancelled = ' <span class="chip exc">لغوشده</span>' if a["status"] != "active" else ""
        tgt = esc(TARGET_LABEL.get(a["target_grade"], "همه")) if a["target_all"] else esc("، ".join(r["name"] for r in conn.execute(
            "SELECT g.name FROM groups g JOIN assignment_groups ag ON ag.group_id=g.id WHERE ag.assignment_id=?", (a["id"],))) or "گروه")
        rows.append([esc(R.KIND_ICON[a["kind"]] + " " + R.KIND_LABEL[a["kind"]]), link(f"/assignment/{a['id']}", a["title"]) + cancelled,
                     tgt, f'<span class="nowrap">{esc(J.fmt_short(a["deadline_ts"]))}</span>',
                     f"{fa(done)} از {fa(total)}", f"{fa(len(c['on_time']))} / {fa(len(c['late']))}"])
    groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    gchk = ('<div class="chk">' + "".join(f'<label><input type="checkbox" name="groups" value="{g["id"]}"> {esc(g["name"])}</label>' for g in groups) + '</div>'
            if groups else '<span class="muted">(گروهی نساخته‌ای)</span>')
    create = ('<details class="mng"><summary>➕ تکلیف جدید</summary>' + form("asg_create",
        '<p><input name="title" size="40" placeholder="عنوان (مثلاً: ریاضی — صفحه‌ی ۴۲ تا ۴۵)"></p>'
        '<textarea name="desc" placeholder="متن تکلیف (اختیاری)"></textarea>'
        '<p>نوع: <select name="kind"><option value="required">الزامی</option><option value="optional">تمرین بیشتر</option><option value="bonus">امتیازی (فقط ششم امتیاز می‌گیرد)</option></select> '
        '<input name="points" size="6" placeholder="امتیاز"> </p>'
        '<p>مخاطب: <select name="target"><option value="all">همه‌ی پایه‌ها</option><option value="g6">همه‌ی ششم</option><option value="g7">همه‌ی هفتم</option>'
        '<option value="g9">همه‌ی نهم</option><option value="groups">گروه‌های انتخابی ↓</option></select></p>' + gchk +
        '<p>مهلت: <input name="deadline" size="22" placeholder="۱۴۰۵/۰۸/۲۰ ۲۱:۳۰ یا فردا ۲۱:۳۰"></p>'
        '<p>ضمیمه (چند فایل، عکس یا PDF…): <input type="file" name="files" multiple></p>'
        '<p><label><input type="checkbox" name="notify" value="1" checked> به دانش‌آموزان در بات اطلاع داده شود</label></p>',
        "/assignments", "انتشار تکلیف", block=True, multipart=True) + '</details>')
    body = ('<h1>تکالیف</h1><p class="sub">جدیدترین مهلت اول</p>' + create +
            (table(["نوع", "تکلیف", "مخاطب", "مهلت", "ارسال‌شده", "به‌موقع / با تاخیر"], rows) if rows else '<div class="card muted">هنوز تکلیفی ثبت نشده است.</div>'))
    return layout("تکالیف", body, "/assignments", logo=logo)


def assignment_page(conn, cfg, now, aid: int, logo=False):
    a = conn.execute("SELECT * FROM assignments WHERE id=?", (aid,)).fetchone()
    if not a:
        return None
    c = tally(conn, a, now)
    total = sum(len(v) for v in c.values())
    cards = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(l)}</span></div>' for v, l in [
        (len(c["on_time"]), "به‌موقع"), (len(c["late"]), "با تاخیر"), (len(c["incomplete"]), "ناقص"),
        (len(c["none"]), "ارسال‌نشده"), (len(c["excused"]), "عذر موجه")])
    rows = []
    for key in ("on_time", "late", "incomplete", "none", "excused"):
        for s, st in c[key]:
            sub = st["sub"]
            rows.append([link(f"/student/{s['id']}", s["full_name"]), chip(st["code"], st["over"], bool(st.get("override"))),
                         f'<span class="nowrap">{esc(J.fmt_short(sub["submitted_ts"]))}</span>' if sub else "—", files_html(conn, sub),
                         status_form(aid, s["id"], f"/assignment/{aid}")])
    tgt = TARGET_LABEL.get(a["target_grade"], "همه‌ی دانش‌آموزان") if a["target_all"] else "گروه: " + (" ، ".join(r["name"] for r in conn.execute(
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
    back = f"/assignment/{aid}"
    stud_opts = "".join(f'<option value="{s["id"]}">{esc(s["full_name"])}</option>' for key in ("none", "incomplete", "late", "on_time", "excused") for s, _ in c[key])
    pts_in = f'<input name="points" size="6" value="{a["points"]}" placeholder="امتیاز"> ' if a["kind"] == "bonus" else ""
    att_del = "".join(f'<div class="row"><span>{esc(f["name"] or "فایل")}</span>' + form("asg_file_del", hid(fid=f["id"]), back, "حذف", "ghost", "این ضمیمه حذف شود؟") + '</div>' for f in atts)
    manage = ('<details class="mng"><summary>⚙ مدیریت تکلیف</summary>' +
              form("asg_edit", hid(aid=aid) + f'<p><input name="title" size="40" value="{esc(a["title"])}"></p><textarea name="desc">{esc(a["description"])}</textarea><p>{pts_in}</p>',
                   back, "ذخیره‌ی ویرایش", block=True) +
              '<hr>' + form("asg_files", hid(aid=aid) + '<input type="file" name="files" multiple> ', back, "افزودن ضمیمه", block=True, multipart=True) + att_del +
              '<hr>' + form("asg_extend_all", hid(aid=aid) + '<input name="deadline" size="22" placeholder="مهلت جدید برای همه"> ', back, "⏱ تمدید برای همه",
                            confirm="مهلت برای همه تغییر کند و به ارسال‌نشده‌ها خبر برود؟") +
              '<br>' + form("asg_extend_one", hid(aid=aid) + f'<select name="sid">{stud_opts}</select> <input name="deadline" size="22" placeholder="مهلت تازه"> ', back, "👤 تمدید برای یک نفر") +
              '<br>' + form("asg_excuse", hid(aid=aid) + f'<select name="sid">{stud_opts}</select> <input name="reason" size="24" placeholder="دلیل (اختیاری)"> ', back, "🙏 عذر موجه") +
              '<br>' + form("asg_resubmit", hid(aid=aid) + f'<select name="sid">{stud_opts}</select> <input name="note" size="24" placeholder="توضیح برای او"> ', back, "🔁 ارسال مجدد") +
              '<br>' + form("asg_remind", hid(aid=aid), back, "🔔 یادآوری به ارسال‌نشده‌ها", "ghost", "یادآوری برای ارسال‌نشده‌ها فرستاده شود؟") + ' ' +
              (form("asg_cancel", hid(aid=aid, restore=1), back, "↩ فعال‌سازی دوباره", "ghost") if a["status"] != "active" else
               form("asg_cancel", hid(aid=aid), back, "🗑 لغو تکلیف", "warn", "تکلیف لغو شود؟ (پاسخ‌ها حذف نمی‌شوند)")) + '</details>')
    body = (f'<p><a href="/assignments">← همه‌ی تکالیف</a></p><h1>{esc(R.KIND_ICON[a["kind"]])} {esc(a["title"])}{cancelled}</h1>'
            f'<p class="sub">{esc(R.KIND_LABEL[a["kind"]])} | {esc(tgt)} | مهلت: {esc(J.fmt(a["deadline_ts"]))} | '
            f'تاخیر مجاز {fa(a["grace_min"])} دقیقه، ارسال با تاخیر تا {fa(a["late_hours"])} ساعت</p>{desc}'
            f'{manage}<div class="grid" style="margin-top:12px">{cards}</div>{att_html}'
            f'<h2>وضعیت دانش‌آموزان ({fa(total)} نفر)</h2>'
            f'<input class="search" data-table="t-as" placeholder="جست‌وجوی نام…">' +
            table(["دانش‌آموز", "وضعیت", "زمان ارسال", "پاسخ", "ویرایش وضعیت"], rows, "t-as") +
            f'<p style="margin-top:16px"><a class="btn ghost" href="/zip/{aid}">📥 دانلود همه‌ی پاسخ‌ها (ZIP)</a></p>')
    return layout(a["title"], body, "/assignments", logo=logo)


def badges_page(conn, cfg, now, logo=False) -> str:
    board = conn.execute("SELECT s.id, s.full_name, COUNT(b.id) n FROM students s LEFT JOIN badges b ON b.student_id=s.id AND b.status='approved' "
                         "WHERE s.active=1 AND s.grade=6 GROUP BY s.id ORDER BY n DESC, s.full_name").fetchall()
    rows = [[fa(i), link(f"/student/{r['id']}", r["full_name"]), "🏅 " + fa(r["n"])] for i, r in enumerate(board, 1)]
    latest = conn.execute("SELECT b.*, s.full_name FROM badges b JOIN students s ON s.id=b.student_id WHERE b.status='approved' ORDER BY b.awarded_ts DESC LIMIT 30").fetchall()
    l_rows = [[link(f"/student/{r['student_id']}", r["full_name"]), esc(r["title"]), f'<span class="nowrap">{esc(J.fmt_short(r["awarded_ts"]))}</span>'] for r in latest]
    body = ('<h1>نشان‌ها</h1><p class="sub">جدول تعداد نشان‌ها و آخرین نشان‌های صادرشده</p>'
            '<div class="two"><div><h2>جدول نشان‌ها</h2>' + table(["#", "دانش‌آموز", "نشان"], rows) + '</div>'
            '<div><h2>آخرین نشان‌ها</h2>' + (table(["دانش‌آموز", "نشان", "زمان"], l_rows) if l_rows else '<div class="card muted">هنوز نشانی صادر نشده است.</div>') + '</div></div>')
    return layout("نشان‌ها", body, "/badges", logo=logo)


def _fb_status(f) -> str:
    if f["delivered"] == 1:
        return f'<span class="chip ok">رسید</span> <span class="muted nowrap">{esc(J.fmt_short(f["delivered_ts"]))}</span>' if f["delivered_ts"] else '<span class="chip ok">رسید</span>'
    if f["delivered"] == 0:
        return '<span class="chip wait">نرسیده</span>'
    return '<span class="muted">نامعلوم (ثبت قدیمی)</span>'


def _fb_rows(fbs, back, with_student=True):
    rows = []
    for f in fbs:
        row = ([link(f"/student/{f['student_id']}", f["full_name"])] if with_student else []) + [
            f'<span class="nowrap">{esc(J.fmt(f["ts"]))}</span>', esc(f["title"] or "—"), esc(f["text"]), _fb_status(f),
            form("feedback_resend", hid(fid=f["id"]), back, "🔁 ارسال دوباره", "ghost") if f["delivered"] != 1 else ""]
        rows.append(row)
    return rows


def feedback_page(conn, cfg, now, logo=False) -> str:
    fbs = conn.execute("SELECT f.*, s.full_name, a.title FROM feedback f JOIN students s ON s.id=f.student_id "
                       "LEFT JOIN assignments a ON a.id=f.assignment_id ORDER BY f.ts DESC LIMIT 300").fetchall()
    per = conn.execute("SELECT s.id, s.full_name, s.grade, COUNT(f.id) n, MAX(f.ts) last, SUM(CASE WHEN f.delivered IS NOT 1 THEN 1 ELSE 0 END) bad "
                       "FROM feedback f JOIN students s ON s.id=f.student_id GROUP BY s.id ORDER BY last DESC").fetchall()
    summ = [[link(f"/student/{p['id']}#fb", p["full_name"]), esc(R.GRADE_NAME.get(p["grade"], "")), fa(p["n"]),
             f'<span class="nowrap">{esc(J.fmt(p["last"]))}</span>', (f'<span class="chip wait">{fa(p["bad"])} نرسیده/نامعلوم</span>' if p["bad"] else "✅")] for p in per]
    body = ('<h1>بازخوردها</h1><p class="sub">هر بازخورد با تاریخ و ساعت ثبت می‌شود و وضعیت رسیدنش به بله معلوم است. تاریخچه‌ی کامل هر نفر در صفحه‌ی خودش (بخش «بازخوردها») است.</p>'
            '<h2>به تفکیک دانش‌آموز</h2>' + (table(["دانش‌آموز", "پایه", "تعداد", "آخرین بازخورد", "وضعیت ارسال"], summ) if summ else '<div class="card muted">بازخوردی ثبت نشده است.</div>') +
            '<h2>همه‌ی بازخوردها (جدیدترین اول)</h2>' + (table(["دانش‌آموز", "تاریخ و ساعت", "تکلیف", "بازخورد", "ارسال", ""], _fb_rows(fbs, "/feedback")) if fbs else ""))
    return layout("بازخوردها", body, "/feedback", logo=logo)


def audit_page(conn, cfg, now, logo=False) -> str:
    rows_db = conn.execute("SELECT * FROM audit ORDER BY ts DESC LIMIT 200").fetchall()
    rows = [[f'<span class="nowrap">{esc(J.fmt_short(r["ts"]))}</span>', esc(fa(r["admin_id"]) if r["admin_id"] else "—"),
             esc(ACTION_LABELS.get(r["action"], r["action"])), esc(r["details"] or "")] for r in rows_db]
    body = ('<h1>گزارش فعالیت مدیران</h1><p class="sub">۲۰۰ کار آخر؛ برای ردگیری و اطمینان، نه برای محدودکردن.</p>' +
            (table(["زمان", "شناسه‌ی مدیر", "کار", "جزئیات"], rows) if rows else '<div class="card muted">فعالیتی ثبت نشده است.</div>'))
    return layout("گزارش فعالیت", body, "/audit", logo=logo)


def groups_page(conn, cfg, now, logo=False) -> str:
    rows = []
    for g in conn.execute("SELECT * FROM groups ORDER BY name").fetchall():
        n = conn.execute("SELECT COUNT(*) c FROM student_groups WHERE group_id=?", (g["id"],)).fetchone()["c"]
        rows.append([link(f"/group/{g['id']}", g["name"]), fa(n)])
    add = ('<details class="mng" open><summary>➕ گروه تازه</summary>' +
           form("group_create", '<input name="name" size="24" placeholder="نام گروه"> ', "/groups", "ساخت") + '</details>')
    tbl = table(["گروه", "تعداد اعضا"], rows) if rows else '<div class="card muted">هنوز گروهی نیست.</div>'
    return layout("گروه‌ها", f'<h1>گروه‌ها</h1><p class="sub">گروه‌ها برای تکلیف و پیام ویژه‌ی چند نفر هستند.</p>{add}{tbl}', "/groups", logo=logo)


def group_page(conn, cfg, now, gid: int, logo=False):
    g = conn.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
    if not g:
        return None
    mine = {r["student_id"] for r in conn.execute("SELECT student_id FROM student_groups WHERE group_id=?", (gid,))}
    studs = conn.execute("SELECT * FROM students WHERE active=1 ORDER BY grade, full_name").fetchall()
    boxes = "".join(f'<label><input type="checkbox" name="students" value="{s["id"]}"{" checked" if s["id"] in mine else ""}> '
                    f'{esc(s["full_name"])} <span class="muted">({esc(R.GRADE_NAME.get(s["grade"], ""))})</span></label>' for s in studs)
    members = form("group_members", hid(gid=gid) + f'<div class="chk">{boxes}</div>', f"/group/{gid}", "ذخیره‌ی اعضا", block=True)
    used = conn.execute("SELECT COUNT(*) c FROM assignment_groups ag JOIN assignments a ON a.id=ag.assignment_id "
                        "WHERE ag.group_id=? AND a.status='active'", (gid,)).fetchone()["c"]
    warn = f"{fa(used)} تکلیف فعال برای این گروه تعریف شده و بعد از حذف مخاطبی نخواهد داشت. " if used else ""
    delete = form("group_delete", hid(gid=gid) + f'<label><input type="checkbox" name="confirm" value="1"> {esc(warn)}می‌خواهم این گروه حذف شود</label> ',
                  "/groups", "🗑 حذف گروه", "warn", "گروه حذف شود؟")
    body = (f'<p><a href="/groups">← همه‌ی گروه‌ها</a></p><h1>{esc(g["name"])}</h1><p class="sub">{fa(len(mine))} عضو</p>'
            f'<h2>اعضا</h2><div class="card">{members}</div><h2>حذف</h2><div class="card">{delete}</div>')
    return layout(g["name"], body, "/groups", logo=logo)


def not_found(logo=False) -> str:
    return layout("پیدا نشد", '<div class="card"><h1>صفحه پیدا نشد</h1><p><a href="/">بازگشت به داشبورد</a></p></div>', logo=logo)


# ====================== پایه‌ی نهم: باشگاه کتابخوانی ======================
def _pair(r) -> str:
    from .books import pair_label
    return pair_label(r["day1_ts"], r["day2_ts"])


def _book_section(conn, s) -> str:
    """بخش باشگاه کتابخوانی یک دانش‌آموز نهمی (در صفحه‌ی خود او، کنار تکالیف)."""
    rows_db = conn.execute("SELECT * FROM book_reports WHERE student_id=? AND status='active' ORDER BY day2_ts DESC, id DESC", (s["id"],)).fetchall()
    pages = sum(r["pages"] for r in rows_db)
    books_n = len({reports._norm_book(r["book"]) for r in rows_db})
    cards = "".join(f'<div class="card stat"><b>{fa(v)}</b><span>{esc(t)}</span></div>' for v, t in [
        (len(rows_db), "گزارش"), (pages, "مجموع صفحه"), (books_n, "کتاب")])
    rows = [[f'<span class="nowrap">{esc(_pair(r))}</span>', esc(r["book"]), f'{fa(r["from_page"])} تا {fa(r["to_page"])}',
             fa(r["pages"]), "✅" if r["posted"] else "—"] for r in rows_db]
    tbl = table(["روزها", "کتاب", "صفحه‌ها", "تعداد", "ارسال به گروه"], rows) if rows else '<div class="card muted">هنوز گزارشی ثبت نشده است.</div>'
    return f'<h2>باشگاه کتابخوانی</h2><div class="grid">{cards}</div>{tbl}'


def student_book_page(conn, s, logo=False) -> str:
    state = "" if s["active"] else ' <span class="chip exc">غیرفعال</span>'
    body = (f'<p><a href="/students">← همه‌ی دانش‌آموزان</a></p><h1>{esc(s["full_name"])}{state}</h1>'
            f'<p class="sub">پایه‌ی نهم — باشگاه کتابخوانی</p>' + _book_section(conn, s))
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
    def _edit(r):
        return ('<details><summary class="muted">ویرایش</summary>' +
                form("book_edit", hid(rid=r["id"]) + f'<input name="book" size="22" value="{esc(r["book"])}"> از <input name="from_p" size="5" value="{r["from_page"]}"> تا '
                     f'<input name="to_p" size="5" value="{r["to_page"]}"> ', "/books", "ذخیره") + " " +
                form("book_repost", hid(rid=r["id"]), "/books", "ارسال دوباره به گروه", "ghost") + " " +
                form("book_delete", hid(rid=r["id"]), "/books", "حذف", "warn", "این گزارش حذف شود؟") + '</details>')
    rec = [[link(f"/student/{r['student_id']}", r["full_name"]), f'<span class="nowrap">{esc(_pair(r))}</span>', esc(r["book"]),
            f'{fa(r["from_page"])} تا {fa(r["to_page"])} ({fa(r["pages"])})', "✅" if r["posted"] else "—", _edit(r)]
           for r in reversed(st["rows"][-20:])]
    rtbl = table(["دانش‌آموز", "روزها", "کتاب", "صفحه‌ها", "گروه", "مدیریت"], rec) if rec else '<div class="card muted">هنوز گزارشی نیست.</div>'
    cur = conn.execute("SELECT value FROM settings WHERE key='book_group_chat_id'").fetchone()
    kg = conn.execute("SELECT * FROM known_groups ORDER BY last_seen_ts DESC LIMIT 15").fetchall()
    cur_t = next((g["title"] or str(g["chat_id"]) for g in kg if cur and str(g["chat_id"]) == str(cur[0])), cur[0] if cur else "تنظیم نشده")
    gopts = "".join(f'<option value="{g["chat_id"]}">{esc(g["title"] or g["chat_id"])}</option>' for g in kg)
    grp = ('<details class="mng"><summary>👥 گروه بله‌ی گزارش‌ها: ' + esc(str(cur_t)) + '</summary>' +
           (form("book_group", f'<select name="chat_id">{gopts}</select> ', "/books", "تنظیم این گروه", confirm="گروه گزارش‌ها تغییر کند و پیام آزمایشی برود؟") if kg else
            '<p class="muted">بات هنوز گروهی ندیده؛ آن را به گروه اضافه کن و یک پیام در گروه بفرست.</p>') + '</details>')
    body = (f'<h1>باشگاه کتابخوانی (پایه‌ی نهم)</h1><p class="sub">{filt}</p>{grp}<div class="grid">{cards}</div>'
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
    p_rows = []
    for r in conn.execute("SELECT l.*, s.full_name FROM points_ledger l JOIN students s ON s.id=l.student_id "
                          "WHERE l.status='pending' AND l.kind<>'badge' ORDER BY l.id").fetchall():
        p_rows.append([link(f"/student/{r['student_id']}", r["full_name"]), esc(r["reason"]), "+" + fa(r["delta"]),
                       f'<span class="nowrap">{esc(J.fmt_short(r["created_ts"]))}</span>',
                       form("item_ok", hid(kind="points", id=r["id"]), "/points", "✅ تأیید") + " " +
                       form("item_no", hid(kind="points", id=r["id"]), "/points", "❌ رد", "warn")])
    for bd in conn.execute("SELECT b.*, s.full_name FROM badges b JOIN students s ON s.id=b.student_id WHERE b.status='pending' ORDER BY b.awarded_ts").fetchall():
        p_rows.append([link(f"/student/{bd['student_id']}", bd["full_name"]), "🏅 " + esc(bd["title"]), "—",
                       f'<span class="nowrap">{esc(J.fmt_short(bd["awarded_ts"]))}</span>',
                       form("item_ok", hid(kind="badge", id=bd["id"]), "/points", "✅ تأیید") + " " +
                       form("item_no", hid(kind="badge", id=bd["id"]), "/points", "❌ رد", "warn", "رد نشان، آن را حذف و مسدود می‌کند. ادامه؟")])
    ptbl = table(["دانش‌آموز", "دلیل", "امتیاز", "زمان", "تصمیم"], p_rows) if p_rows else '<div class="card muted">امتیاز در انتظار تأییدی نیست ✅</div>'
    all_btn = form("items_all", "", "/points", f"✅ تأیید همه‌ی {fa(len(p_rows))} مورد", confirm="همه‌ی موردهای منتظر تأیید شوند؟") if p_rows else ""
    note = '<p class="note">تأیید یا رد، دانش‌آموز را مثل بات خبردار می‌کند. تغییر دستی امتیاز از صفحه‌ی هر دانش‌آموز ششمی انجام می‌شود.</p>'
    body = (f'<h1>امتیازها</h1><p class="sub">امتیاز تأییدشده‌ی هر دانش‌آموز پایه‌ی ششم</p>{note}'
            f'<div class="two"><div><h2>در انتظار تأیید ({fa(len(p_rows))})</h2>{ptbl}{all_btn}</div>'
            f'<div><h2>جدول امتیاز</h2>{table(["دانش‌آموز", "تأییدشده", "در انتظار"], rows)}</div></div>')
    return layout("امتیازها", body, "/points", logo=logo)


def messages_page(conn, cfg, now, logo=False) -> str:
    opts = ('<option value="all">همه‌ی دانش‌آموزان</option><option value="g6">همه‌ی ششم</option><option value="g7">همه‌ی هفتم</option>'
            '<option value="g9">همه‌ی نهم</option>' + "".join(f'<option value="{g["id"]}">گروه: {esc(g["name"])}</option>'
                                                       for g in conn.execute("SELECT * FROM groups ORDER BY name")) +
            "".join(f'<option value="s{s["id"]}">{esc(s["full_name"])} ({esc(R.GRADE_NAME.get(s["grade"], ""))})</option>'
                    for s in conn.execute("SELECT * FROM students WHERE active=1 ORDER BY grade, full_name")))
    n = conn.execute("SELECT COUNT(*) c FROM students WHERE active=1 AND chat_id IS NOT NULL").fetchone()["c"]
    body = ('<h1>پیام به دانش‌آموزان</h1><p class="sub">پیام از طریق بات بله می‌رود؛ فقط دانش‌آموزانی که وارد بات شده‌اند دریافت می‌کنند ('
            + fa(n) + ' نفر).</p>' + form("broadcast", f'<p>گیرنده: <select name="target">{opts}</select></p><textarea name="text" placeholder="متن پیام (اگر فایل می‌فرستی می‌تواند خالی باشد)"></textarea>'
                                    '<p>پیوست (چند فایل: عکس، PDF…): <input type="file" name="files" multiple></p>',
                                    "/messages", "ارسال پیام", confirm="پیام برای گیرندگان انتخاب‌شده فرستاده شود؟", block=True, multipart=True))
    return layout("پیام‌ها", body, "/messages", logo=logo)


def admins_page(conn, cfg, now, logo=False) -> str:
    fixed = "، ".join(fa(i) for i in sorted(cfg.admin_ids)) or "—"
    extra = conn.execute("SELECT * FROM admins ORDER BY added_ts").fetchall()
    rows = [[f'<span dir="ltr">{fa(r["user_id"])}</span>', esc(J.fmt_short(r["added_ts"])),
             form("admin_remove", hid(uid=r["user_id"]), "/admins", "حذف", "warn", "این مدیر حذف شود؟")] for r in extra]
    body = ('<h1>مدیران</h1><p class="sub">شناسه‌ی عددی هر نفر را با دستور /myid در بات می‌گیرد.</p>'
            f'<div class="card">مدیران ثابت (از تنظیمات سرور؛ از اینجا حذف نمی‌شوند): <b>{fixed}</b></div><h2>مدیران افزوده‌شده</h2>' +
            (table(["شناسه", "زمان افزودن", "حذف"], rows) if rows else '<div class="card muted">مدیر افزوده‌شده‌ای نیست.</div>') +
            form("admin_add", '<input name="uid" size="16" dir="ltr" placeholder="شناسه‌ی عددی"> ', "/admins", "➕ افزودن مدیر"))
    return layout("مدیران", body, "/admins", logo=logo)


def receipts_page(conn, cfg, now, logo=False) -> str:
    rows_db = conn.execute("SELECT r.*, s.full_name FROM receipts r JOIN students s ON s.id=r.student_id "
                           "ORDER BY (r.status='new') DESC, r.ts DESC LIMIT 200").fetchall()
    rows = []
    for r in rows_db:
        ext = Path(r["path"]).suffix.lower() if r["path"] else ""
        view = ('<span class="muted">رسید متنی</span>' if not r["path"] else f'<a href="/rfile/{r["id"]}" target="_blank"><img loading="lazy" src="/rfile/{r["id"]}" alt="رسید" style="max-height:70px;border-radius:8px"></a>'
                if ext in IMG_EXT else f'<a class="pill" href="/rfile/{r["id"]}" target="_blank">{esc(r["name"] or "فایل")}</a>')
        state = '<span class="chip wait">بررسی‌نشده</span>' if r["status"] == "new" else f'<span class="chip ok">دریافت‌شده</span> <span class="muted nowrap">{esc(J.fmt_short(r["seen_ts"]))}</span>'
        act = form("receipt_seen", hid(rid=r["id"]), "/receipts", "✅ دریافت شد", "ghost") if r["status"] == "new" else ""
        rows.append([link(f"/student/{r['student_id']}", r["full_name"]), f'<span class="nowrap">{esc(J.fmt_short(r["ts"]))}</span>',
                     esc(r["note"] or "—"), view, state, act])
    n = sum(1 for r in rows_db if r["status"] == "new")
    body = (f'<h1>رسیدهای واریزی</h1><p class="sub">{fa(len(rows_db))} رسید | {fa(n)} بررسی‌نشده — دانش‌آموز از منوی بات «🧾 ارسال رسید» را می‌زند و رسید را می‌فرستد.</p>' +
            (table(["دانش‌آموز", "زمان", "توضیح", "رسید", "وضعیت", ""], rows) if rows else '<div class="card muted">هنوز رسیدی نرسیده است.</div>'))
    return layout("رسیدها", body, "/receipts", logo=logo)
