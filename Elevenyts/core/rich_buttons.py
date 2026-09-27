"""Global Rich Button renderer.

Every Pyrogram InlineKeyboardMarkup is rendered as Telegram Rich Message
buttons.  The original button labels, callback data, URLs and message text
are preserved; only the button presentation changes.
"""
import html
import re
from typing import Any
import aiohttp
from Elevenyts import config


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def _attr(obj: Any, name: str, default=None):
    value = getattr(obj, name, default)
    return default if value in (None, "") else value


def _style(button: Any) -> str:
    value = getattr(button, "style", None)
    name = getattr(value, "name", str(value or "")).lower()
    if "danger" in name:
        return "danger"
    if "success" in name:
        return "success"
    return "primary"


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _button_html(button: Any) -> str:
    label = _e(getattr(button, "text", "Button"))
    style = _style(button)

    callback = _attr(button, "callback_data")
    if callback is not None:
        return f'<tg-button type="callback_data" style="{style}" data="{_e(callback)}">{label}</tg-button>'

    url = _attr(button, "url")
    if url is not None:
        return f'<tg-button type="url" style="{style}" url="{_e(url)}">{label}</tg-button>'

    copy = _attr(button, "copy_text")
    if copy is not None:
        copy = copy if isinstance(copy, str) else _attr(copy, "text")
        if copy is not None:
            return f'<tg-button type="copy_text" style="{style}" text="{_e(copy)}">{label}</tg-button>'

    web_app = _attr(button, "web_app")
    if web_app:
        url = _attr(web_app, "url")
        if url:
            return f'<tg-button type="web_app" style="{style}" url="{_e(url)}">{label}</tg-button>'

    switch = _attr(button, "switch_inline_query")
    if switch is not None:
        return f'<tg-button type="switch_inline_query" style="{style}" query="{_e(switch)}">{label}</tg-button>'

    switch_current = _attr(button, "switch_inline_query_current_chat")
    if switch_current is not None:
        return f'<tg-button type="switch_inline_query_current_chat" style="{style}" query="{_e(switch_current)}">{label}</tg-button>'

    # Keep an unknown button visible rather than silently dropping it.
    return f'<tg-button type="disabled" style="{style}">{label}</tg-button>'


def _body(text: str) -> str:
    # Preserve the bot's existing HTML/text exactly. Only raw line breaks need
    # to become HTML breaks inside a Rich Message.
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def is_inline_markup(markup: Any) -> bool:
    return bool(markup is not None and getattr(markup, "inline_keyboard", None))


def markup_to_rich_html(text: str, markup: Any) -> str | None:
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return None
    parts = [_body(text)]
    for row in rows:
        buttons = [_button_html(button) for button in row]
        if buttons:
            parts.append('<tg-button-row align="center">' + ''.join(buttons) + '</tg-button-row>')
    return '<br>'.join(parts)


def _media_from_message(message):
    """Return (rich tag, rich media type, Telegram file_id) for common media."""
    checks = (
        ("photo", "photo", "img"),
        ("video", "video", "video"),
        ("animation", "animation", "video"),
        ("audio", "audio", "audio"),
        ("voice", "voice_note", "audio"),
        ("document", "document", "tg-document"),
    )
    for attr, kind, tag in checks:
        obj = getattr(message, attr, None)
        fid = getattr(obj, "file_id", None) if obj else None
        if fid:
            return tag, kind, fid
    return None


def build_rich_payload(message, text: str, markup: Any):
    body = markup_to_rich_html(text, markup)
    if body is None:
        return None
    payload = {"html": body}
    media = _media_from_message(message)
    if media:
        tag, kind, file_id = media
        payload["html"] = f'<{tag} src="tg://media?id=rich_media"/><br>{body}'
        payload["media"] = [{"id": "rich_media", "media": {"type": kind, "media": file_id}}]
    return payload


async def _request(method: str, data: dict):
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_api(method), json=data) as response:
            result = await response.json(content_type=None)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", f"Telegram {method} failed"))
    return result


async def replace_with_rich(message, text: str, markup: Any):
    """Replace one normal inline-keyboard message with a Rich Message.

    The temporary normal message is deleted only after sendRichMessage succeeds.
    A Pyrogram Message for the new Rich Message is fetched before returning, so
    existing bot code can continue using the returned object normally.
    """
    payload = build_rich_payload(message, text, markup)
    if not payload:
        return message

    data = {
        "chat_id": int(message.chat.id),
        "rich_message": payload,
    }
    # Preserve reply/thread placement when possible.
    try:
        data["reply_parameters"] = {"message_id": int(message.reply_to_message_id)} if getattr(message, "reply_to_message_id", None) else None
    except Exception:
        pass
    if data.get("reply_parameters") is None:
        data.pop("reply_parameters", None)

    result = await _request("sendRichMessage", data)
    new_id = int((result.get("result") or {}).get("message_id"))
    if not new_id:
        raise RuntimeError("sendRichMessage returned no message_id")

    await _request("deleteMessage", {
        "chat_id": int(message.chat.id),
        "message_id": int(message.id),
    })

    # Fetching through the same Pyrogram client gives callers the normal Message
    # object instead of exposing the raw Bot API response.
    client = getattr(message, "_client", None)
    if client is not None:
        try:
            fetched = await client.get_messages(int(message.chat.id), new_id)
            if fetched:
                return fetched
        except Exception:
            pass
    return message


async def convert_existing(message, text: str, markup: Any) -> bool:
    """Compatibility helper for code that only needs success/failure."""
    try:
        new_message = await replace_with_rich(message, text, markup)
        return bool(new_message)
    except Exception:
        return False
