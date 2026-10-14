"""یوزرنیم بله: نرمال‌سازی و اعتبارسنجی (برای ورود دانش‌آموز با یوزرنیم)."""
import re

from .fa import en

_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
_LINK = re.compile(r"^(https?://)?(www\.)?(ble\.ir|bale\.ai|bale\.me)/", re.I)


def normalize(raw):
    """«@Ali_01» یا «ble.ir/Ali_01» ← «ali_01»؛ نامعتبر = None. (در بله حروف بزرگ و کوچک فرقی ندارد)"""
    if raw is None:
        return None
    s = _LINK.sub("", en(str(raw)).strip()).lstrip("@").strip().rstrip("/")
    return s.lower() if _RE.match(s) else None
