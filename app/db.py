"""دیتابیس SQLite — یک فایل ساده که پشتیبان‌گیری‌اش فقط کپی کردن است."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY, added_ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS students(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  code TEXT UNIQUE NOT NULL,
  chat_id INTEGER UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  created_ts INTEGER NOT NULL,
  joined_ts INTEGER,
  grade INTEGER NOT NULL DEFAULT 6,           -- پایه: ۶ یا ۹
  username TEXT                               -- یوزرنیم بله (حروف کوچک، بدون @)؛ برای ورود
);
CREATE TABLE IF NOT EXISTS student_groups(
  student_id INTEGER NOT NULL, group_id INTEGER NOT NULL,
  PRIMARY KEY(student_id, group_id)
);
CREATE TABLE IF NOT EXISTS assignments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'required',      -- required | optional | bonus
  deadline_ts INTEGER NOT NULL,
  grace_min INTEGER NOT NULL,
  late_hours INTEGER NOT NULL,
  target_all INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',      -- active | cancelled
  created_ts INTEGER NOT NULL,
  points INTEGER NOT NULL DEFAULT 0           -- امتیاز تکلیف امتیازی (بعد از تأیید مدیر)
);
CREATE TABLE IF NOT EXISTS assignment_groups(
  assignment_id INTEGER NOT NULL, group_id INTEGER NOT NULL,
  PRIMARY KEY(assignment_id, group_id)
);
CREATE TABLE IF NOT EXISTS assignment_files(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id INTEGER NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL, name TEXT
);
CREATE TABLE IF NOT EXISTS student_deadlines(
  assignment_id INTEGER NOT NULL, student_id INTEGER NOT NULL, deadline_ts INTEGER NOT NULL,
  PRIMARY KEY(assignment_id, student_id)
);
CREATE TABLE IF NOT EXISTS excuses(
  assignment_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  reason TEXT, admin_id INTEGER, ts INTEGER NOT NULL,
  PRIMARY KEY(assignment_id, student_id)
);
CREATE TABLE IF NOT EXISTS submissions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  state TEXT NOT NULL,                        -- draft | final | superseded
  created_ts INTEGER NOT NULL,
  submitted_ts INTEGER,
  on_time INTEGER,
  over_minutes INTEGER,
  resubmit_of INTEGER
);
CREATE INDEX IF NOT EXISTS ix_sub ON submissions(assignment_id, student_id, state);
CREATE TABLE IF NOT EXISTS submission_files(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id INTEGER NOT NULL, path TEXT NOT NULL, name TEXT, size INTEGER
);
CREATE TABLE IF NOT EXISTS resubmit_requests(
  assignment_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  note TEXT, ts INTEGER NOT NULL, open INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(assignment_id, student_id)
);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL, assignment_id INTEGER,
  text TEXT NOT NULL, admin_id INTEGER, ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS badges(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL, code TEXT NOT NULL, key TEXT NOT NULL,
  title TEXT NOT NULL, awarded_ts INTEGER NOT NULL,
  UNIQUE(student_id, code, key)
);
CREATE TABLE IF NOT EXISTS reminders(
  assignment_id INTEGER NOT NULL, student_id INTEGER NOT NULL, kind TEXT NOT NULL,
  PRIMARY KEY(assignment_id, student_id, kind)
);
CREATE TABLE IF NOT EXISTS chat_state(chat_id INTEGER PRIMARY KEY, state TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS book_reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  day1_ts INTEGER NOT NULL, day2_ts INTEGER NOT NULL,      -- ظهر روز اول و دوم (ساعت ایران)
  book TEXT NOT NULL,
  from_page INTEGER NOT NULL, to_page INTEGER NOT NULL, pages INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',                   -- active | deleted
  posted INTEGER NOT NULL DEFAULT 0,
  created_ts INTEGER NOT NULL, edited_ts INTEGER
);
CREATE INDEX IF NOT EXISTS ix_br ON book_reports(student_id, day1_ts, status);
CREATE TABLE IF NOT EXISTS points_ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL, delta INTEGER NOT NULL, reason TEXT NOT NULL,
  kind TEXT NOT NULL,                                      -- bonus | badge | manual
  source_code TEXT, source_key TEXT,
  status TEXT NOT NULL DEFAULT 'pending',                  -- pending | approved | rejected
  created_ts INTEGER NOT NULL, decided_ts INTEGER, admin_id INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_pl_src ON points_ledger(student_id, kind, source_code, source_key) WHERE source_code IS NOT NULL;
CREATE TABLE IF NOT EXISTS badge_blocks(
  student_id INTEGER NOT NULL, code TEXT NOT NULL, key TEXT NOT NULL,
  PRIMARY KEY(student_id, code, key)
);
CREATE TABLE IF NOT EXISTS login_attempts(
  chat_id INTEGER PRIMARY KEY, username TEXT, name TEXT, last_ts INTEGER NOT NULL, count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS known_groups(chat_id INTEGER PRIMARY KEY, title TEXT, last_seen_ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS web_logins(
  code_hash TEXT PRIMARY KEY, admin_id INTEGER NOT NULL,
  created_ts INTEGER NOT NULL, expires_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL, admin_id INTEGER, action TEXT NOT NULL, details TEXT
);
"""


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # روی دیسک‌های شبکه‌ای/ابری اگر WAL مشکل داد، SQLITE_JOURNAL=DELETE بگذارید
    mode = os.environ.get("SQLITE_JOURNAL", "WAL").upper()
    conn.execute("PRAGMA journal_mode=%s" % (mode if mode in ("WAL", "DELETE", "TRUNCATE") else "WAL"))
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.commit()
    return conn


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn):
    """به‌روزرسانی دیتابیس‌های قدیمی (ساخته‌شده با نسخه‌ی پیش از پایه‌ی نهم و امتیاز) بدون از دست رفتن داده."""
    if "grade" not in _cols(conn, "students"):
        conn.execute("ALTER TABLE students ADD COLUMN grade INTEGER NOT NULL DEFAULT 6")
    if "points" not in _cols(conn, "assignments"):
        conn.execute("ALTER TABLE assignments ADD COLUMN points INTEGER NOT NULL DEFAULT 0")
    if "username" not in _cols(conn, "students"):
        conn.execute("ALTER TABLE students ADD COLUMN username TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_stu_username ON students(username) "
                 "WHERE username IS NOT NULL AND username<>''")
