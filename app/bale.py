"""کلاینت ساده‌ی API بات‌های بله (سازگار با ساختار بات‌های تلگرام)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx


class BaleError(Exception):
    pass


def btn(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


def keyboard(rows) -> dict:
    return {"inline_keyboard": rows}


class Bale:
    def __init__(self, token: str, base: str = "https://tapi.bale.ai", timeout: float = 45.0):
        base = base.rstrip("/")
        self.api = f"{base}/bot{token}"
        self.file_api = f"{base}/file/bot{token}"
        self.http = httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0))

    # توجه: متن خطاهای httpx شامل نشانی (و در نتیجه توکن) است؛ هرگز آن را لاگ نمی‌کنیم.
    def call(self, method: str, data: dict | None = None, files: dict | None = None):
        try:
            if files:
                r = self.http.post(f"{self.api}/{method}", data=data, files=files)
            else:
                r = self.http.post(f"{self.api}/{method}", json=data or {})
        except httpx.HTTPError as e:
            raise BaleError(f"{method}: network {type(e).__name__}") from None
        try:
            js = r.json()
        except ValueError:
            raise BaleError(f"{method}: bad response {r.status_code}") from None
        if not js.get("ok"):
            raise BaleError(f"{method}: {js.get('description') or js.get('error_code')}")
        return js.get("result")

    def delete_webhook(self):
        try:
            self.call("deleteWebhook")
        except BaleError:
            pass

    def get_updates(self, offset=None, timeout: int = 20):
        data = {"timeout": timeout}
        if offset is not None:
            data["offset"] = offset
        return self.call("getUpdates", data) or []

    def send_message(self, chat_id, text, rows=None):
        data = {"chat_id": chat_id, "text": text}
        if rows:
            data["reply_markup"] = keyboard(rows)
        return self.call("sendMessage", data)

    def edit_text(self, chat_id, message_id, text, rows=None):
        data = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if rows:
            data["reply_markup"] = keyboard(rows)
        return self.call("editMessageText", data)

    def answer_callback(self, callback_id, text=None):
        data = {"callback_query_id": callback_id}
        if text:
            data["text"] = text
        try:
            self.call("answerCallbackQuery", data)
        except BaleError:
            pass

    def _send_file(self, method, field, chat_id, path, caption=None, rows=None, filename=None):
        path = Path(path)
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
        if rows:
            data["reply_markup"] = json.dumps(keyboard(rows), ensure_ascii=False)
        with open(path, "rb") as fh:
            return self.call(method, data, files={field: (filename or path.name, fh)})

    def send_photo(self, chat_id, path, caption=None, rows=None):
        return self._send_file("sendPhoto", "photo", chat_id, path, caption, rows)

    def send_document(self, chat_id, path, caption=None, rows=None, filename=None):
        return self._send_file("sendDocument", "document", chat_id, path, caption, rows, filename)

    def download(self, file_id: str, dest: Path) -> int:
        info = self.call("getFile", {"file_id": file_id})
        fpath = info.get("file_path") if isinstance(info, dict) else None
        if not fpath:
            raise BaleError("getFile: no file_path")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with self.http.stream("GET", f"{self.file_api}/{fpath}") as r:
                if r.status_code != 200:
                    raise BaleError(f"download: http {r.status_code}")
                with open(dest, "wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
                        size += len(chunk)
        except httpx.HTTPError as e:
            raise BaleError(f"download: network {type(e).__name__}") from None
        return size
