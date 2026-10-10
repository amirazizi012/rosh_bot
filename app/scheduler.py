"""کارهای زمان‌بندی‌شده: یادآوری پیش از مهلت و پشتیبان‌گیری روزانه."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from . import jalali as J
from . import rules as R
from .bale import btn
from .core import App

log = logging.getLogger("rosh")


def tick(app: App):
    try:
        reminders(app)
    except Exception:
        log.exception("خطا در یادآوری")
    try:
        daily_backup(app)
    except Exception:
        log.exception("خطا در پشتیبان‌گیری")


def reminders(app: App):
    now = app.now()
    window = app.cfg.reminder_hours * 3600
    for a in app.conn.execute("SELECT * FROM assignments WHERE status='active' AND deadline_ts>? AND deadline_ts<=?",
                              (now, now + window + 86400)).fetchall():
        for s in R.target_students(app.conn, a):
            if not s["chat_id"]:
                continue
            dl = R.effective_deadline(app.conn, a, s["id"])
            if not (now < dl <= now + window):
                continue
            if R.current_final(app.conn, a["id"], s["id"]) or R.is_excused(app.conn, a["id"], s["id"]):
                continue
            done = app.conn.execute("SELECT 1 FROM reminders WHERE assignment_id=? AND student_id=? AND kind='pre'",
                                    (a["id"], s["id"])).fetchone()
            if done:
                continue
            app.conn.execute("INSERT INTO reminders VALUES(?,?, 'pre')", (a["id"], s["id"]))
            app.conn.commit()
            app.send(s["chat_id"], f"⏰ یادآوری: تکلیف «{a['title']}» تا {J.fmt(dl)} مهلت دارد.",
                     [[btn("📖 باز کردن تکلیف", f"s:a:{a['id']}")]])


def daily_backup(app: App):
    day = J.to_dt(app.now()).strftime("%Y%m%d")
    r = app.conn.execute("SELECT value FROM settings WHERE key='last_backup'").fetchone()
    if r and r["value"] == day:
        return
    dest = app.data / "backups" / f"rosh-{day}.db"
    out = sqlite3.connect(str(dest))
    with out:
        app.conn.backup(out)
    out.close()
    app.conn.execute("INSERT INTO settings(key,value) VALUES('last_backup',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (day,))
    app.conn.commit()
    for old in sorted((app.data / "backups").glob("rosh-*.db"))[:-14]:
        old.unlink(missing_ok=True)
    log.info("پشتیبان‌گیری انجام شد: %s", dest.name)
