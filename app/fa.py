"""ابزارهای متن فارسی: ارقام فارسی، مدت زمان، پاک‌سازی ورودی."""
import re

_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def fa(x) -> str:
    """هر عدد/متنی را با ارقام فارسی برمی‌گرداند."""
    return str(x).translate(_TO_FA)


def en(s) -> str:
    """ارقام فارسی و عربی را به لاتین تبدیل می‌کند (برای پردازش ورودی)."""
    return str(s).translate(_TO_EN)


def clean(s) -> str:
    s = (s or "").replace("ي", "ی").replace("ك", "ک").replace("\u200f", "").replace("\u200e", "")
    return re.sub(r"[ \t]+", " ", s).strip()


def duration(minutes) -> str:
    """مثلاً ۱۳۵ -> «۲ ساعت و ۱۵ دقیقه»."""
    minutes = max(0, int(minutes))
    if minutes == 0:
        return "کمتر از یک دقیقه"
    d, rem = divmod(minutes, 1440)
    h, m = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{fa(d)} روز")
    if h:
        parts.append(f"{fa(h)} ساعت")
    if m:
        parts.append(f"{fa(m)} دقیقه")
    return " و ".join(parts)
