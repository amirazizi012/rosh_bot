"""مسیریابی به‌روزرسانی‌های بله به بخش دانش‌آموز یا مدیر."""
from __future__ import annotations

import logging
from pathlib import Path

from . import admin, student
from .bale import BaleError
from .core import App, Ctx
from .fa import fa

log = logging.getLogger("rosh")


def handle(app: App, u: dict):
    if "callback_query" in u:
        cq = u["callback_query"]
        m = cq.get("message") or {}
        chat = (m.get("chat") or {}).get("id") or (cq.get("from") or {}).get("id")
        user = (cq.get("from") or {}).get("id")
        if chat is None or user is None:
            return
        ctx = Ctx(chat, user, m.get("message_id"))
        app.bale.answer_callback(cq.get("id"))
        parts = (cq.get("data") or "").split(":")
        route_callback(app, ctx, parts)
    elif "message" in u:
        msg = u["message"]
        chat = (msg.get("chat") or {}).get("id")
        user = (msg.get("from") or {}).get("id") or chat
        if chat is None or (msg.get("chat") or {}).get("type", "private") != "private":
            return  # فقط گفتگوی خصوصی
        route_message(app, Ctx(chat, user), msg)


def route_callback(app: App, ctx: Ctx, parts):
    kind = parts[0] if parts else ""
    if kind == "a":
        if not app.is_admin(ctx.user_id):
            app.send(ctx.chat_id, "این بخش مخصوص مدیران است.")
            return
        admin.on_callback(app, ctx, parts)
    elif kind == "s":
        st = app.student_by_chat(ctx.chat_id)
        if not st:
            student.ask_code(app, ctx)
            return
        student.on_callback(app, ctx, st, parts)


def route_message(app: App, ctx: Ctx, msg: dict):
    text = (msg.get("text") or "").strip()
    if text.startswith("/myid"):
        app.send(ctx.chat_id, f"شناسه‌ی عددی تو در بله: {ctx.user_id}\n(این عدد را به مدیر مجموعه بده تا دسترسی مدیر بگیری.)")
        return
    if text.startswith("/start") or text.startswith("/menu") or text == "منو":
        # لغو هر کار نیمه‌تمام (فایل‌های موقت تکلیف هم پاک می‌شود)
        state, data = app.get_state(ctx.chat_id)
        for f in data.get("files", []) if isinstance(data, dict) else []:
            Path(f["path"]).unlink(missing_ok=True)
        if state == "s:upload":
            st = app.student_by_chat(ctx.chat_id)
            if st:
                student._discard_drafts(app, data.get("aid"), st["id"])
        app.clear_state(ctx.chat_id)
        if app.is_admin(ctx.user_id):
            admin.menu(app, ctx)
            return
        st = app.student_by_chat(ctx.chat_id)
        if st:
            student.home(app, ctx, st)
        else:
            student.ask_code(app, ctx)
        return
    if app.is_admin(ctx.user_id):
        admin.on_message(app, ctx, msg)
        return
    st = app.student_by_chat(ctx.chat_id)
    if st:
        student.on_message(app, ctx, st, msg)
    else:
        state, _ = app.get_state(ctx.chat_id)
        if state != "s:code":
            app.set_state(ctx.chat_id, "s:code", {})
        student.on_code(app, ctx, text)
