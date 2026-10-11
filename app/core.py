"""هسته‌ی برنامه: وضعیت گفتگو، ارسال پیام، دسترسی‌ها، ثبت رویدادها."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from .bale import BaleError

log = logging.getLogger("rosh")


@dataclass
class Ctx:
    chat_id: int
    user_id: int
    msg_id: int | None = None


class App:
    def __init__(self, cfg, bale, conn):
        self.cfg, self.bale, self.conn = cfg, bale, conn
        self.clock = time.time
        self.data = Path(cfg.data_dir)
        for sub in ("assignments", "submissions", "tmp", "backups", "exports"):
            (self.data / sub).mkdir(parents=True, exist_ok=True)

    def now(self) -> int:
        return int(self.clock())

    # ---------- وضعیت گفتگو ----------
    def get_state(self, chat_id):
        r = self.conn.execute("SELECT state, data FROM chat_state WHERE chat_id=?", (chat_id,)).fetchone()
        if not r:
            return "", {}
        try:
            return r["state"] or "", json.loads(r["data"] or "{}")
        except ValueError:
            return r["state"] or "", {}

    def set_state(self, chat_id, state, data=None):
        self.conn.execute(
            "INSERT INTO chat_state(chat_id,state,data) VALUES(?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET state=excluded.state, data=excluded.data",
            (chat_id, state, json.dumps(data or {}, ensure_ascii=False)))
        self.conn.commit()

    def clear_state(self, chat_id):
        self.conn.execute("DELETE FROM chat_state WHERE chat_id=?", (chat_id,))
        self.conn.commit()

    # ---------- هویت‌ها ----------
    def is_admin(self, user_id) -> bool:
        if user_id in self.cfg.admin_ids:
            return True
        return self.conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone() is not None

    def student_by_chat(self, chat_id):
        return self.conn.execute(
            "SELECT * FROM students WHERE chat_id=? AND active=1", (chat_id,)).fetchone()

    def student(self, sid):
        return self.conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()

    def assignment(self, aid):
        return self.conn.execute("SELECT * FROM assignments WHERE id=?", (aid,)).fetchone()

    def award(self, sid):
        """نشان‌های خودکار (و امتیازهای در انتظار تأیید) را برای یک دانش‌آموز بررسی می‌کند."""
        from . import rules as R
        c = self.cfg
        return R.award_auto(self.conn, sid, self.now(), c.streak_size, c.extra_streak_size, c.extra_streak_points)

    def audit(self, admin_id, action, details=""):
        self.conn.execute("INSERT INTO audit(ts,admin_id,action,details) VALUES(?,?,?,?)",
                          (self.now(), admin_id, action, details))
        self.conn.commit()

    # ---------- ارسال پیام ----------
    def send(self, chat_id, text, rows=None):
        try:
            return self.bale.send_message(chat_id, text, rows)
        except BaleError as e:
            log.warning("ارسال پیام ناموفق: %s", e)
            return None

    def send_long(self, chat_id, text, rows=None, limit=3500):
        chunks, cur = [], ""
        for line in text.split("\n"):
            if len(cur) + len(line) + 1 > limit and cur:
                chunks.append(cur)
                cur = ""
            cur += line + "\n"
        if cur.strip():
            chunks.append(cur.rstrip())
        for i, c in enumerate(chunks):
            self.send(chat_id, c, rows if i == len(chunks) - 1 else None)

    def show(self, ctx: Ctx, text, rows=None):
        """اگر از دکمه آمده‌ایم پیام قبلی را ویرایش می‌کند، وگرنه پیام تازه می‌فرستد."""
        if ctx.msg_id:
            try:
                self.bale.edit_text(ctx.chat_id, ctx.msg_id, text, rows)
                return
            except BaleError as e:
                # طبق مستندات بله فعلاً پیام‌های دارای دکمه‌ی inline قابل ویرایش نیستند؛ پیام قبلی را پاک و پیام تازه می‌فرستیم
                log.info("ویرایش پیام ممکن نشد، پیام تازه ارسال می‌شود: %s", e)
                try:
                    self.bale.delete_message(ctx.chat_id, ctx.msg_id)
                except BaleError:
                    pass
        self.send(ctx.chat_id, text, rows)

    def send_file(self, chat_id, path, caption=None):
        """عکس را به‌صورت عکس و بقیه را به‌صورت فایل می‌فرستد."""
        path = Path(path)
        try:
            # سقف ارسال عکس با multipart ده مگابایت است؛ عکس بزرگ‌تر را به‌صورت فایل می‌فرستیم
            if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and path.stat().st_size <= 9_500_000:
                self.bale.send_photo(chat_id, path, caption)
            else:
                self.bale.send_document(chat_id, path, caption)
            return True
        except (BaleError, OSError) as e:
            log.warning("ارسال فایل ناموفق: %s", e)
            return False


def _admin_ids(self):
    ids = set(self.cfg.admin_ids)
    ids.update(r["user_id"] for r in self.conn.execute("SELECT user_id FROM admins"))
    return ids


def _get_setting(self, key, default=None):
    r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def _set_setting(self, key, value):
    self.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    self.conn.commit()


App.admin_ids = _admin_ids
App.get_setting = _get_setting
App.set_setting = _set_setting
