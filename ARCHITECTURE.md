# معماری بات «رشد»

> این سند برای توسعه‌دهنده (و Claude) نوشته شده. جزئیات ماشینی (ماژول‌ها، توابع، جدول‌ها و ستون‌ها) در `docs/graph.json` است و با `python scripts/map.py` بازسازی می‌شود. هر وقت ساختار عوض شد، هر دو را به‌روز کنید.

## ۱. نمای کلی

دو فرایند جدا از یک دیتابیس SQLite کار می‌کنند:

```
  بله (tapi.bale.ai)                        مرورگر مدیر
        │ getUpdates (Long Polling)              │ HTTP (فقط خواندن)
        ▼                                        ▼
  ┌──────────────┐   می‌نویسد + می‌خواند   ┌──────────────┐
  │ app.main     │ ─────────────────────▶ │ app.panel    │  (یا همان فرایند، با PANEL_ENABLE=1)
  │ (بات)        │       data/rosh.db     │ (پنل وب)     │  دیتابیس را mode=ro باز می‌کند
  └──────────────┘                        └──────────────┘
        │ فایل‌ها                                │
        ▼                                        ▼
    data/submissions/…, data/assignments/…, data/exports/…
```

## ۲. نقطه‌های ورود

| فایل | نقش | چطور اجرا می‌شود |
|---|---|---|
| `app/main.py` | بات: حلقه‌ی دریافت پیام، مسیریابی، زمان‌بند | `python -m app.main` (Dockerfile، `deploy/rosh-bot.service`) |
| `app/panel.py` | پنل وب فقط‌خواندنی | `python -m app.panel` (`deploy/rosh-panel.service`، `start_panel.bat`) |

اگر `PANEL_ENABLE=1` باشد، `app/main.py` پنل را در یک نخ جدا هم بالا می‌آورد (برای کانتینر هم‌روش که یک اپ و یک دیسک دارد).

## ۳. لایه‌ها

### ۳٫۱ زیرساخت
- **`app/config.py`**: خواندن `.env` و متغیرهای محیطی به کلاس `Config`. هیچ مقدار دیگری جای آن ذخیره نمی‌شود.
- **`app/db.py`**: `SCHEMA` (۲۴ جدول)، `connect()` و `migrate()`. مهاجرت‌ها با `ALTER TABLE` و فقط برای ستون‌های جدید است و داده پاک نمی‌کند.
- **`app/bale.py`**: کلاس `Bale`؛ همه‌ی تماس‌ها با API بله از اینجا می‌گذرد (`getUpdates`، `sendMessage`، `sendPhoto`، `sendDocument`، `getFile`، `editMessageText`، `deleteMessage`، `setWebhook`). خطاها `BaleError` می‌شوند.
- **`app/core.py`**: کلاس `App` (وضعیت گفتگو در `chat_state`، ارسال پیام، `audit`، تنظیمات `settings`) و `Ctx` (چت، کاربر، یوزرنیم فرستنده).
- **`app/fa.py`، `app/jalali.py`، `app/usernames.py`**: ابزارهای فارسی، ارقام و تاریخ شمسی (ساعت ایران)، و یوزرنیم بله.

### ۳٫۲ قواعد کسب‌وکار (بدون وابستگی به بله)
- **`app/rules.py`**: منطق اصلی و قابل آزمون:
  - مهلت، تاخیر، تاخیر مجاز (`verdict`)،
  - ارسال و ویرایش (`can_submit`، `finalize`)،
  - عذر موجه و ارسال مجدد،
  - شمارنده‌ی نشان (`streak_state` برای الزامی و `extra_streak_state` برای اختیاری/امتیازی)،
  - نشان‌های خودکار (`award_auto`) و دفتر امتیاز (`add_points`، `points_total`).
- **`app/reports.py`**: ساخت اکسل (`build_xlsx`، `build_books_xlsx`)، ZIP پاسخ‌ها (`build_zips`) و متن گزارش‌ها.
- **`app/scheduler.py`**: یادآوری، پشتیبان‌گیری روزانه، و پاک‌سازی فایل‌های `exports`. هر ۶۰ ثانیه از حلقه‌ی `main` صدا زده می‌شود.

### ۳٫۳ رابط بات (پیام و دکمه)
- **`app/router.py`**: تنها جای مسیریابی. هر به‌روزرسانی را به یکی از این‌ها می‌فرستد:
  - دانش‌آموز (`student.py`)،
  - مدیر (`admin.py`)،
  - باشگاه کتابخوانی پایه‌ی نهم (`books.py`)،
  - گروه (فقط `/setgroup`).
- **`app/student.py`**: ورود با یوزرنیم یا کد، منوی تکالیف، ارسال و ویرایش پاسخ، پیشرفت، بازخوردها.
- **`app/admin.py`**: پنل مدیر (دکمه‌های `a:…`): تکلیف، دانش‌آموز، گروه، گزارش، بازخورد، پیام همگانی، نشان دستی، مدیران. کدها در دکمه‌ها با `:` جدا می‌شوند.
- **`app/books.py`**: باشگاه کتابخوانی پایه‌ی نهم (دکمه‌های `b:…` برای دانش‌آموز؛ بخش مدیر در همین فایل)؛ ارسال گزارش به گروه بله.
- **`app/points.py`**: صف تأیید امتیاز، تغییر دستی امتیاز، و مدیریت نشان‌ها.

### ۳٫۴ پنل وب (فقط‌خواندنی)
- **`app/panel.py`**: سرور HTTP (`ThreadingHTTPServer`)، ورود با کد ۸ رقمی یک‌بارمصرف، نشست‌ها در `data/panel.db` (جدا از دیتابیس اصلی)، محدودیت تلاش ورود، و سرو فایل‌ها و ZIP/اکسل. هر درخواست غیر GET رد می‌شود.
- **`app/panel_ui.py`**: تولید HTML فارسی، راست‌چین، با ارقام فارسی. همه‌ی توابعش فقط می‌خوانند.

## ۴. دیتابیس

۲۴ جدول در `app/db.py`. گروه‌ها:
- **دانش‌آموز و گروه:** `students` (شامل `grade` ۶/۹ و `username`)، `groups`، `student_groups`، `admins`.
- **تکلیف:** `assignments`، `assignment_groups`، `assignment_files`، `student_deadlines` (تمدید فردی)، `excuses`، `resubmit_requests`.
- **ارسال:** `submissions` (وضعیت `draft`/`final`/`superseded`)، `submission_files`.
- **پیشرفت:** `badges`، `badge_blocks` (نشان حذف‌شده که دوباره داده نمی‌شود)، `points_ledger`، `feedback`.
- **کتابخوانی:** `book_reports`.
- **پیام‌ها و وضعیت:** `reminders`، `chat_state`، `known_groups`، `login_attempts`، `settings`.
- **امنیت و ردیابی:** `web_logins`، `audit`.

قاعده‌ی مهم: **هر کار مدیر یک ردیف در `audit` می‌گیرد.** این برای ردگیری اشتباه است، نه محدودکردن.

## ۵. جریان‌های مهم

**ارسال پاسخ:** `student.start_upload` ← پیش‌نویس در `submissions(state=draft)` ← فایل‌ها در `submission_files` (دانلود از بله با `Bale.download`) ← «ارسال نهایی» ← `rules.finalize` که `verdict` را حساب می‌کند و نسخه‌ی قبلی را `superseded` می‌کند ← `award_auto`.

**ویرایش پاسخ:** `student.start_edit` پیش‌نویسی با کپی فایل‌های فعلی می‌سازد (فایل‌ها مشترک‌اند، پس حذف یک فایل از پیش‌نویس فایل پاسخ قبلی را پاک نمی‌کند تا وقتی ارسال نهایی شود).

**تأیید امتیاز:** تکلیف امتیازی یا نشان کوشا یک ردیف `pending` در `points_ledger` می‌سازد. فقط `points.approve` (از پنل مدیر) آن را `approved` می‌کند.

**ورود:** `router` ← `student.start_login` ← `try_login` با یوزرنیم (شناسه‌ی حساب در `students.chat_id` ثبت می‌شود، نه یوزرنیم).

**باشگاه کتابخوانی:** `books.on_callback`/`on_message` ← `book_reports` ← `post_report` به گروه ثبت‌شده در `settings.book_group_chat_id`.

## ۶. آزمون‌ها

`tests/test_rules.py` (قواعد خالص)، `test_flow.py` (جریان سرتاسری با بله‌ی جعلی `FakeBale`)، `test_books.py` (پایه‌ی نهم و امتیاز)، `test_panel.py` (پنل و امنیتش)، `test_login_edit.py` (یوزرنیم و ویرایش). اجرا: `python tests/test_rules.py` و بقیه.

## ۷. آنچه هنوز تأیید نشده

- **رفتار واقعی بله:** پیام‌ها، دکمه‌ها، دریافت فایل، ارسال پررنگ، `/setgroup` در گروه، و فیلد `from.username` فقط روی `FakeBale` آزمون شده‌اند. روی بله‌ی واقعی باید تست شوند.
- **Docker:** ایمیج ساخته و اجرا نشده؛ فقط اجرای مستقیم پایتون آزمون شده است.
