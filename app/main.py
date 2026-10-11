"""نقطه‌ی شروع: python -m app.main"""
from __future__ import annotations

import logging
import threading
import time

from . import config, db, router, scheduler
from .bale import Bale, BaleError
from .core import App

log = logging.getLogger("rosh")


def needs_pause(updates, elapsed: float) -> bool:
    return not updates and elapsed < 1.0


def start_panel(cfg):
    """اگر PANEL_ENABLE=1 باشد، پنل وب را در همین فرایند (نخ جدا) بالا می‌آورد؛ خطای پنل بات را متوقف نمی‌کند."""
    if not cfg.panel_enable:
        return None
    try:
        from . import panel
        srv = panel.make_server(cfg)
        threading.Thread(target=srv.serve_forever, daemon=True, name="panel").start()
        log.info("پنل وب (فقط‌خواندنی) روی %s:%s فعال شد", cfg.panel_host, srv.server_address[1])
        return srv
    except Exception:
        log.exception("راه‌اندازی پنل وب ناموفق بود؛ بات بدون پنل ادامه می‌دهد")
        return None


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # لاگ httpx نشانی کامل (و توکن) را می‌نویسد؛ خاموشش می‌کنیم
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = config.load()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(cfg.data_dir / "rosh.db")
    bale = Bale(cfg.token, cfg.api_base)
    app = App(cfg, bale, conn)
    bale.delete_webhook()
    start_panel(cfg)
    log.info("بات «رشد» شروع به کار کرد. مدیران ثابت: %d", len(cfg.admin_ids))
    offset, last_tick = None, 0.0
    while True:
        try:
            t0 = time.time()
            updates = bale.get_updates(offset, timeout=20)
            if needs_pause(updates, time.time() - t0):
                time.sleep(1.0)  # اگر سرور فوراً خالی جواب داد (بدون long-poll)، هر ثانیه یک‌بار می‌پرسیم
        except BaleError as e:
            log.warning("دریافت به‌روزرسانی ناموفق: %s", e)
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            try:
                router.handle(app, u)
            except Exception:
                log.exception("خطا در پردازش به‌روزرسانی")
                try:
                    chat = ((u.get("message") or {}).get("chat") or {}).get("id") or \
                           (((u.get("callback_query") or {}).get("message") or {}).get("chat") or {}).get("id")
                    if chat:
                        app.send(chat, "⚠️ مشکلی پیش آمد. دوباره امتحان کن یا /menu را بفرست.")
                except Exception:
                    pass
        if time.time() - last_tick >= 60:
            scheduler.tick(app)
            last_tick = time.time()


if __name__ == "__main__":
    run()
