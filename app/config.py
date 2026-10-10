"""تنظیمات از متغیرهای محیطی / فایل .env"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Config:
    token: str
    admin_ids: set
    data_dir: Path
    api_base: str = "https://tapi.bale.ai"
    grace_minutes: int = 20
    late_window_hours: int = 24
    streak_size: int = 6
    reminder_hours: int = 3
    max_file_mb: int = 20
    max_files_per_submission: int = 15
    panel_url: str = ""
    panel_host: str = "127.0.0.1"
    panel_port: int = 8080
    panel_secure_cookie: bool = False
    panel_trust_proxy: bool = False
    panel_enable: bool = False


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def load() -> Config:
    load_env()
    token = os.environ.get("BALE_TOKEN", "").strip()
    if not token:
        raise SystemExit("BALE_TOKEN تنظیم نشده است؛ فایل .env را از روی .env.example بسازید.")
    raw = os.environ.get("ADMIN_IDS", "").replace("،", ",")
    admins = {int(x) for x in (p.strip() for p in raw.split(",")) if x.isdigit()}
    return Config(
        token=token,
        admin_ids=admins,
        data_dir=Path(os.environ.get("DATA_DIR", "./data")),
        api_base=os.environ.get("BALE_API_BASE", "https://tapi.bale.ai"),
        grace_minutes=_int("GRACE_MINUTES", 20),
        late_window_hours=_int("LATE_WINDOW_HOURS", 24),
        streak_size=_int("STREAK_SIZE", 6),
        reminder_hours=_int("REMINDER_HOURS", 3),
        panel_url=os.environ.get("PANEL_URL", "").strip().rstrip("/"),
        panel_host=os.environ.get("PANEL_HOST", "127.0.0.1").strip(),
        panel_port=_int("PANEL_PORT", 8080),
        panel_secure_cookie=os.environ.get("PANEL_SECURE_COOKIE", "0") == "1",
        panel_trust_proxy=os.environ.get("PANEL_TRUST_PROXY", "0") == "1",
        panel_enable=os.environ.get("PANEL_ENABLE", "0") == "1",
    )
