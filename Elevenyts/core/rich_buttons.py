"""Safe Rich Message bridge for existing Pyrogram messages.

The original bot remains responsible for sending/editing messages. Rich
conversion happens only after the original message exists, so command startup,
reply behaviour, media and returned Message objects stay unchanged.
"""
import html
import re
import urllib.parse
from typing import Any
import aiohttp
from Elevenyts import config


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def _style(button: Any) -> str:
    value = getattr(button, "style", None)
    name = getattr(value, "name", str(value or "")).lower()
    if "danger" in name:
        return "danger"
    if "success" in name:
        return "success"
    return "primary"


def _attr(button: Any, name: str, default=None):
    value = getattr(button, name, default)
    return value if value not in (None, "") else default


def _ea(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _button_html(button: Any) -> str:
    label = html.escape(str(getattr(button, "text", "Button")))
    style = _style(button)
    callback = _attr(button, "callback_data")
    if callback is not None:
        return f'<tg-button type="callback_data" style="{style}" data="{_ea(callback)}">{label}</tg-button>'
    url = _attr(button, "url")
    if url is not None:
        return f'<tg-button type="url" style="{style}" url="{_ea(url)}">{label}</tg-button>'
    copy = _attr(button, "copy_text")
    if copy is not None:
        copy = copy if isinstance(copy, str) else _attr(copy, "text")
        if copy is not None:
            return f'<tg-button type="copy_text" style="{style}" text="{_ea(copy)}">{label}</tg-button>'
    web_app = _attr(button, "web_app")
    if web_app:
        url = _attr(web_app, "url")
        if url:
            return f'<tg-button type="web_app" style="{style}" url="{_ea(url)}">{label}</tg-button>'
    switch = _attr(button, "switch_inline_query")
    if switch is not None:
        return f'<tg-button type="switch_inline_query" style="{style}" query="{_ea(switch)}">{label}</tg-button>'
    switch_current = _attr(button, "switch_inline_query_current_chat")
    if switch_current is not None:
        return f'<tg-button type="switch_inline_query_current_chat" style="{style}" query="{_ea(switch_current)}">{label}</tg-button>'
    return f'<tg-button type="disabled" style="{style}">{label}</tg-button>'


def _body(text: str) -> str:
    # Do not rebuild/clean the bot's message. Preserve every character and
    # every existing HTML tag; only convert raw newlines to HTML line breaks.
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n", "<br>", s)


def markup_to_rich_html(text: str, markup: Any) -> str | None:
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return None
    parts = [_body(text)]
    for row in rows:
        buttons = [_button_html(b) for b in row]
        if buttons:
            parts.append('<tg-button-row align="center">' + "".join(buttons) + "</tg-button-row>")
    return "<br>".join(parts)


def is_inline_markup(markup: Any) -> bool:
    return bool(markup is not None and getattr(markup, "inline_keyboard", None))


def _message_media(message):
    if not message:
        return None
    for attr, kind, tag in (
        ("photo", "photo", "img"),
        ("video", "video", "video"),
        ("animation", "animation", "video"),
        ("audio", "audio", "audio"),
        ("voice", "voice_note", "audio"),
        ("document", "document", "tg-document"),
    ):
        obj = getattr(message, attr, None)
        fid = getattr(obj, "file_id", None) if obj else None
        if fid:
            return tag, kind, fid
    return None


def _rich_payload(message, text, markup):
    body = markup_to_rich_html(text, markup)
    if body is None:
        return None
    payload = {"html": body}
    media = _message_media(message)
    if media:
        tag, kind, fid = media
        payload["html"] = f'<{tag} src="tg://media?id=existing_media"/><br>' + body
        payload["media"] = [{"id": "existing_media", "media": {"type": kind, "media": fid}}]
    return payload


async def _request(method: str, data: dict):
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_api(method), json=data) as response:
            result = await response.json(content_type=None)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", f"Telegram {method} failed"))
    return result


async def convert_existing(message, text: str, markup: Any) -> bool:
    """Convert the already-sent message in place.

    Returning False is deliberately non-fatal: the original Pyrogram message
    remains intact with its normal buttons.
    """
    payload = _rich_payload(message, text, markup)
    if not payload:
        return False
    try:
        await _request("editMessageText", {
            "chat_id": int(message.chat.id),
            "message_id": int(message.id),
            "rich_message": payload,
        })
        return True
    except Exception:
        return False
