"""Direct Rich Message sender for all supported inline-button messages.

Unlike post-send conversion, this sends the Rich Message first, so users never
see a temporary normal inline keyboard. Button labels, callback data, URLs,
row order and message HTML are preserved.
"""
import html
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
from Elevenyts import config

log = logging.getLogger("Elevenyts")


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def _attr(obj: Any, name: str, default=None):
    value = getattr(obj, name, default)
    return default if value in (None, "") else value


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _style(button: Any) -> str:
    value = getattr(button, "style", None)
    name = getattr(value, "name", str(value or "")).lower()
    label = str(getattr(button, "text", "")).lower()
    if "danger" in name:
        return "danger"
    if "success" in name:
        return "success"
    if not name or name in ("none", "buttonstyle.none"):
        if any(word in label for word in ("stop", "delete", "remove", "cancel", "close")):
            return "danger"
        if any(word in label for word in ("play", "resume", "start", "next", "skip", "loop", "download")):
            return "success"
    return "primary"


def _button_html(button: Any) -> str:
    label = html.escape(str(getattr(button, "text", "Button")))
    style = _style(button)
    callback = _attr(button, "callback_data")
    if callback is not None:
        return f'<tg-button type="callback_data" style="{style}" data="{_escape(callback)}">{label}</tg-button>'
    url = _attr(button, "url")
    if url is not None:
        return f'<tg-button type="url" style="{style}" url="{_escape(url)}">{label}</tg-button>'
    copy = _attr(button, "copy_text")
    if copy is not None:
        copy = copy if isinstance(copy, str) else _attr(copy, "text")
        if copy is not None:
            return f'<tg-button type="copy_text" style="{style}" text="{_escape(copy)}">{label}</tg-button>'
    web_app = _attr(button, "web_app")
    if web_app:
        target = _attr(web_app, "url")
        if target:
            return f'<tg-button type="web_app" style="{style}" url="{_escape(target)}">{label}</tg-button>'
    login = _attr(button, "login_url")
    if login:
        target = _attr(login, "url")
        if target:
            extra = ""
            forward = _attr(login, "forward_text")
            if forward:
                extra += f' forward-text="{_escape(forward)}"'
            if _attr(login, "request_write_access", False):
                extra += " request-write-access"
            return f'<tg-button type="login_url" style="{style}" url="{_escape(target)}"{extra}>{label}</tg-button>'
    switch = _attr(button, "switch_inline_query")
    if switch is not None:
        return f'<tg-button type="switch_inline_query" style="{style}" query="{_escape(switch)}">{label}</tg-button>'
    switch_current = _attr(button, "switch_inline_query_current_chat")
    if switch_current is not None:
        return f'<tg-button type="switch_inline_query_current_chat" style="{style}" query="{_escape(switch_current)}">{label}</tg-button>'
    chosen = _attr(button, "switch_inline_query_chosen_chat")
    if chosen:
        query = _attr(chosen, "query", "")
        flags = ""
        for attr, flag in (
            ("allow_user_chats", "allow-user-chats"),
            ("allow_bot_chats", "allow-bot-chats"),
            ("allow_group_chats", "allow-group-chats"),
            ("allow_channel_chats", "allow-channel-chats"),
        ):
            if _attr(chosen, attr, False):
                flags += f" {flag}"
        return f'<tg-button type="switch_inline_query_chosen_chat" style="{style}" query="{_escape(query)}"{flags}>{label}</tg-button>'
    return f'<tg-button type="disabled" style="{style}">{label}</tg-button>'


def _body(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def is_inline_markup(markup: Any) -> bool:
    return bool(markup is not None and getattr(markup, "inline_keyboard", None))


def markup_to_rich_html(text: str, markup: Any) -> str | None:
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return None
    body = _body(text)
    row_html = []
    for row in rows:
        # Telegram Rich Message supports at most eight buttons in a row.
        for start in range(0, len(row), 8):
            chunk = row[start:start + 8]
            if chunk:
                row_html.append(
                    '<tg-button-row align="center">'
                    + "".join(_button_html(button) for button in chunk)
                    + "</tg-button-row>"
                )
    # Deliberately no <br> between button rows: each tg-button-row is already
    # its own block. This removes the extra vertical gap seen in the old UI.
    if body and row_html:
        return body + "<br>" + "".join(row_html)
    return body + "".join(row_html)


def _options(kwargs: dict) -> dict:
    allowed = {
        "message_thread_id", "direct_messages_topic_id", "disable_notification",
        "protect_content", "allow_paid_broadcast", "message_effect_id",
        "business_connection_id", "suggested_post_parameters",
    }
    result = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if kwargs.get("reply_parameters") is not None:
        result["reply_parameters"] = kwargs["reply_parameters"]
    elif kwargs.get("reply_to_message_id"):
        result["reply_parameters"] = {"message_id": int(kwargs["reply_to_message_id"])}
    return result


async def _request(method: str, data: dict, *, upload=None):
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if upload is None:
            async with session.post(_api(method), json=data) as response:
                result = await response.json(content_type=None)
        else:
            form = aiohttp.FormData()
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                form.add_field(key, str(value) if value is not None else "")
            field_name, file_obj, filename, content_type, _owned = upload
            form.add_field(field_name, file_obj, filename=filename, content_type=content_type)
            async with session.post(_api(method), data=form) as response:
                result = await response.json(content_type=None)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", f"Telegram {method} failed"))
    return result


def _media_kind(kind: str):
    mapping = {
        "photo": ("photo", "img"),
        "video": ("video", "video"),
        "animation": ("animation", "video"),
        "audio": ("audio", "audio"),
        "voice": ("voice_note", "audio"),
        "voice_note": ("voice_note", "audio"),
        "document": ("document", "tg-document"),
    }
    return mapping.get(kind, (kind, "tg-document"))


def _is_url(value):
    if not isinstance(value, str):
        return False
    return urlparse(value).scheme in ("http", "https")


def _local_upload(source):
    """Return a multipart upload tuple for local files/bytes/file objects."""
    if isinstance(source, (str, os.PathLike)):
        path = os.fspath(source)
        if os.path.isfile(path):
            import mimetypes
            guessed = mimetypes.guess_type(path)[0] or "application/octet-stream"
            return ("media0", open(path, "rb"), os.path.basename(path), guessed, True)
        return None
    if isinstance(source, (bytes, bytearray)):
        return ("media0", bytes(source), "upload.bin", "application/octet-stream", False)
    if hasattr(source, "read"):
        import mimetypes
        name = getattr(source, "name", "upload.bin")
        filename = os.path.basename(str(name))
        guessed = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return ("media0", source, filename, guessed, False)
    return None


async def send_rich_text(chat_id, text, markup, **kwargs):
    rich_html = markup_to_rich_html(text, markup)
    if rich_html is None:
        return None
    data = {
        "chat_id": int(chat_id),
        "rich_message": {"html": rich_html},
    }
    data.update(_options(kwargs))
    return await _request("sendRichMessage", data)


async def send_rich_media(chat_id, text, markup, media_kind, media, **kwargs):
    rich_html = markup_to_rich_html(text, markup)
    if rich_html is None:
        return None

    kind, tag = _media_kind(media_kind)
    scheme = {
        "photo": "photo", "video": "video", "animation": "video",
        "audio": "audio", "voice_note": "audio", "document": "document",
    }.get(kind, kind)
    upload = _local_upload(media)
    if upload:
        media_ref = "attach://media0"
    else:
        # Telegram file_id and HTTP(S) URL are valid media references. For
        # unsupported sources, let caller use its established Pyrogram path.
        # Any non-empty string that is not a local path is passed through as a
        # Telegram file_id or an HTTP(S) URL; file_id prefixes are not fixed.
        if not (isinstance(media, str) and media.strip()):
            return None
        media_ref = media.strip()

    rich = {
        "html": f'<{tag} src="tg://{kind}?id=rich_media"/><br>{rich_html}',
        "media": [{"id": "rich_media", "media": {"type": kind, "media": media_ref}}],
    }
    data = {"chat_id": int(chat_id), "rich_message": rich}
    data.update(_options(kwargs))
    try:
        result = await _request("sendRichMessage", data, upload=upload)
        return result
    finally:
        if upload and upload[4] and hasattr(upload[1], "close"):
            try:
                upload[1].close()
            except Exception:
                pass


async def convert_existing(message, text: str, markup: Any) -> bool:
    """Legacy fallback for unsupported media sources; not used on supported sends."""
    rich_html = markup_to_rich_html(text or getattr(message, "caption", "") or "", markup)
    if rich_html is None:
        return False
    payload = {"html": rich_html}
    for attr, kind, tag in (
        ("photo", "photo", "img"), ("video", "video", "video"),
        ("animation", "animation", "video"), ("audio", "audio", "audio"),
        ("voice", "voice_note", "audio"), ("document", "document", "tg-document"),
    ):
        obj = getattr(message, attr, None)
        fid = getattr(obj, "file_id", None) if obj else None
        if fid:
            payload["html"] = f'<{tag} src="tg://{kind}?id=existing_media"/><br>{rich_html}'
            payload["media"] = [{"id": "existing_media", "media": {"type": kind, "media": fid}}]
            break
    result = await _request("editMessageText", {
        "chat_id": int(message.chat.id),
        "message_id": int(message.id),
        "rich_message": payload,
    })
    return bool(result.get("ok"))


# Backward-compatible aliases for older Bot implementations.
async def send_rich_for_text(chat_id, text, markup, **kwargs):
    return await send_rich_text(chat_id, text, markup, **kwargs)

async def send_rich_for_media(chat_id, text, markup, media_kind, media, **kwargs):
    return await send_rich_media(chat_id, text, markup, media_kind, media, **kwargs)
