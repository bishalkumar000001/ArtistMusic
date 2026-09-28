"""Rich Message conversion for all existing Pyrogram inline keyboards.

Uses the same Rich Message HTML/media-reference format as helpers.rich_player.
The original message text, button labels, callback data and URLs are preserved.
"""
import html
import logging
import re
from typing import Any
import aiohttp
from Elevenyts import config

log = logging.getLogger("Elevenyts")


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def _attr(obj: Any, name: str, default=None):
    value = getattr(obj, name, default)
    return value if value not in (None, "") else default


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _style(button: Any) -> str:
    value = getattr(button, "style", None)
    name = getattr(value, "name", str(value or "")).lower()
    label = str(getattr(button, "text", "")).lower()
    # Respect explicit styles first; use action labels only when no style exists.
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
    switch = _attr(button, "switch_inline_query")
    if switch is not None:
        return f'<tg-button type="switch_inline_query" style="{style}" query="{_escape(switch)}">{label}</tg-button>'
    switch_current = _attr(button, "switch_inline_query_current_chat")
    if switch_current is not None:
        return f'<tg-button type="switch_inline_query_current_chat" style="{style}" query="{_escape(switch_current)}">{label}</tg-button>'
    return f'<tg-button type="disabled" style="{style}">{label}</tg-button>'


def _body(text: str) -> str:
    # Keep existing HTML and all visible text; only normalize literal newlines.
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n", "<br>", value)


def markup_to_rich_html(text: str, markup: Any) -> str | None:
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return None
    parts = [_body(text)]
    for row in rows:
        buttons = [_button_html(button) for button in row]
        if buttons:
            parts.append('<tg-button-row align="center">' + "".join(buttons) + '</tg-button-row>')
    return "<br>".join(parts)


def is_inline_markup(markup: Any) -> bool:
    return bool(markup is not None and getattr(markup, "inline_keyboard", None))


def _message_media(message):
    if not message:
        return None
    # The player helper uses this exact Rich Message photo-reference syntax.
    for attr, kind, tag, scheme in (
        ("photo", "photo", "img", "photo"),
        ("video", "video", "video", "video"),
        ("animation", "animation", "video", "video"),
        ("audio", "audio", "audio", "audio"),
        ("voice", "voice_note", "audio", "audio"),
        ("document", "document", "tg-document", "document"),
    ):
        obj = getattr(message, attr, None)
        file_id = getattr(obj, "file_id", None) if obj else None
        if file_id:
            return tag, kind, scheme, file_id
    return None


def _rich_payload(message, text, markup):
    body = markup_to_rich_html(text, markup)
    if body is None:
        return None
    payload = {"html": body}
    media = _message_media(message)
    if media:
        tag, kind, scheme, file_id = media
        # Critical: use tg://photo (not tg://media), matching rich_player.py.
        payload["html"] = f'<{tag} src="tg://{scheme}?id=existing_media"/><br>' + body
        payload["media"] = [{"id": "existing_media", "media": {"type": kind, "media": file_id}}]
    return payload


async def _request(method: str, data: dict):
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_api(method), json=data) as response:
            result = await response.json(content_type=None)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", f"Telegram {method} failed"))
    return result


async def convert_existing(message, text: str, markup: Any) -> bool:
    """Convert a sent message in place; return True only on API success."""
    payload = _rich_payload(message, text or getattr(message, "caption", "") or "", markup)
    if not payload:
        return False
    try:
        await _request("editMessageText", {
            "chat_id": int(message.chat.id),
            "message_id": int(message.id),
            "rich_message": payload,
        })
        return True
    except Exception as exc:
        # Do not hide failures: otherwise old inline keyboards remain unnoticed.
        log.warning("Rich button conversion failed for message %s: %s", getattr(message, "id", "?"), exc)
        return False
