"""تاریخ شمسی و ساعت ایران (UTC+3:30 ثابت؛ ساعت تابستانی در ایران لغو شده است)."""
import re
from datetime import datetime, timedelta, timezone

from .fa import fa, en

TEHRAN = timezone(timedelta(hours=3, minutes=30))
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = {5: "شنبه", 6: "یکشنبه", 0: "دوشنبه", 1: "سه‌شنبه",
            2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه"}


def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
            - 80 + gd + g_d_m[gm - 1])
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def j2g(jy, jm, jd):
    jy += 1595
    days = (-355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
            + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186))
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    sal = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal[gm]:
        gd -= sal[gm]
        gm += 1
    return gy, gm, gd


def to_dt(ts):
    return datetime.fromtimestamp(ts, TEHRAN)


def jdate(ts):
    d = to_dt(ts)
    return g2j(d.year, d.month, d.day)


def weekday_name(ts):
    return WEEKDAYS[to_dt(ts).weekday()]


def fmt(ts) -> str:
    """مثلاً: یکشنبه ۱۵ مهر ۱۴۰۵، ساعت ۲۱:۳۰"""
    jy, jm, jd = jdate(ts)
    d = to_dt(ts)
    return fa(f"{weekday_name(ts)} {jd} {MONTHS[jm - 1]} {jy}، ساعت {d.hour:02d}:{d.minute:02d}")


def fmt_short(ts) -> str:
    """مثلاً: ۱۴۰۵/۰۷/۱۵ ۲۱:۳۰"""
    jy, jm, jd = jdate(ts)
    d = to_dt(ts)
    return fa(f"{jy}/{jm:02d}/{jd:02d} {d.hour:02d}:{d.minute:02d}")


def from_jalali(jy, jm, jd, h, mi):
    if not (1 <= jm <= 12 and 1 <= jd <= 31 and 0 <= h < 24 and 0 <= mi < 60):
        return None
    gy, gm, gd = j2g(jy, jm, jd)
    if g2j(gy, gm, gd) != (jy, jm, jd):
        return None  # تاریخ نامعتبر (مثلاً ۳۱ شهریور)
    return int(datetime(gy, gm, gd, h, mi, tzinfo=TEHRAN).timestamp())


def parse(text, now):
    """ورودی‌های مجاز: «۱۴۰۵/۰۷/۲۰ ۲۱:۳۰»، «فردا ۲۱:۳۰»، «امروز ۲۳:۰۰»، «پس‌فردا ۱۸:۰۰»."""
    t = en(text).replace("،", " ").replace("ساعت", " ")
    t = re.sub(r"\s+", " ", t).strip()
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2}) (\d{1,2})[:.](\d{2})$", t)
    if m:
        return from_jalali(*map(int, m.groups()))
    m = re.match(r"^(امروز|فردا|پس[\u200c ]?فردا) (\d{1,2})[:.](\d{2})$", t)
    if m:
        word, h, mi = m.group(1), int(m.group(2)), int(m.group(3))
        add = 0 if word == "امروز" else (1 if word == "فردا" else 2)
        day = to_dt(now).date() + timedelta(days=add)
        jy, jm, jd = g2j(day.year, day.month, day.day)
        return from_jalali(jy, jm, jd, h, mi)
    return None


def noon(ts) -> int:
    """ظهر همان روز (ساعت ایران)"""
    d = to_dt(ts)
    return int(datetime(d.year, d.month, d.day, 12, tzinfo=TEHRAN).timestamp())


def parse_date(text):
    """فقط تاریخ، مثل «۱۴۰۵/۰۷/۱۳» ← ظهر همان روز (ساعت ایران)؛ نامعتبر = None."""
    t = re.sub(r"\s+", "", en(text))
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", t)
    return from_jalali(*map(int, m.groups()), 12, 0) if m else None


DATE_HELP = ("زمان را این‌طور بنویس:\n"
             "• «۱۴۰۵/۰۷/۲۰ ۲۱:۳۰»\n"
             "• یا «فردا ۲۱:۳۰» ، «امروز ۲۳:۰۰» ، «پس‌فردا ۱۸:۰۰»")
