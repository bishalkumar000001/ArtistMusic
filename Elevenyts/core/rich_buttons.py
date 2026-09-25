"""Rich Message button bridge.

Converts normal Pyrogram inline keyboards to Telegram Rich Message buttons
without changing the original button order, rows, or message media.
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
    if "link" in name:
        return "link"
    return "primary"


def _attr(button: Any, name: str, default=None):
    value = getattr(button, name, default)
    return value if value not in (None, "") else default


def _escape_attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _button_html(button: Any) -> str:
    text = html.escape(str(getattr(button, "text", "Button")))
    style = _style(button)

    callback = _attr(button, "callback_data")
    if callback is not None:
        return f'<tg-button type="callback_data" style="{style}" data="{_escape_attr(callback)}">{text}</tg-button>'

    url = _attr(button, "url")
    if url is not None:
        return f'<tg-button type="url" style="{style}" url="{_escape_attr(url)}">{text}</tg-button>'

    copy = _attr(button, "copy_text")
    if copy is not None:
        if not isinstance(copy, str):
            copy = _attr(copy, "text")
        if copy is not None:
            return f'<tg-button type="copy_text" style="{style}" text="{_escape_attr(copy)}">{text}</tg-button>'

    web_app = _attr(button, "web_app")
    if web_app:
        web_url = _attr(web_app, "url")
        if web_url:
            return f'<tg-button type="web_app" style="{style}" url="{_escape_attr(web_url)}">{text}</tg-button>'

    switch = _attr(button, "switch_inline_query")
    if switch is not None:
        return f'<tg-button type="switch_inline_query" style="{style}" query="{_escape_attr(switch)}">{text}</tg-button>'

    switch_current = _attr(button, "switch_inline_query_current_chat")
    if switch_current is not None:
        return f'<tg-button type="switch_inline_query_current_chat" style="{style}" query="{_escape_attr(switch_current)}">{text}</tg-button>'

    return f'<tg-button type="disabled" style="{style}">{text}</tg-button>'


def _rich_text_body(text: str) -> str:
    """Keep the original visual line sequence instead of turning every line
    into a separate Rich paragraph. Existing HTML tags are left untouched.
    """
    body = str(text or "")
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    # A single newline in normal Telegram text is a line break. Rich HTML can
    # otherwise render the same content as visually separated paragraphs.
    body = re.sub(r"(?<!>)\n(?!<)", "<br>", body)
    return body


def markup_to_rich_html(text: str, markup: Any) -> str | None:
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return None

    body = _rich_text_body(text)
    rich_rows = []
    for row in rows:
        buttons = [_button_html(button) for button in row]
        if buttons:
            # Preserve EXACTLY the original Pyrogram row order.
            rich_rows.append('<tg-button-row align="center">' + "".join(buttons) + "</tg-button-row>")
    if not rich_rows:
        return body
    return body + "<br><br>" + "\n".join(rich_rows)


def is_inline_markup(markup: Any) -> bool:
    return bool(markup is not None and getattr(markup, "inline_keyboard", None))


async def request(method: str, data: dict) -> dict:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_api(method), json=data) as response:
            result = await response.json(content_type=None)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", f"Telegram {method} failed"))
    return result


def _message_media(message):
    """Return (tag, media_type, file_id) for an existing Telegram message."""
    if message is None:
        return None

    photo = getattr(message, "photo", None)
    if photo:
        fid = getattr(photo, "file_id", None)
        if fid:
            return "img", "photo", fid

    video = getattr(message, "video", None)
    if video:
        fid = getattr(video, "file_id", None)
        if fid:
            return "video", "video", fid

    animation = getattr(message, "animation", None)
    if animation:
        fid = getattr(animation, "file_id", None)
        if fid:
            return "video", "animation", fid

    audio = getattr(message, "audio", None)
    if audio:
        fid = getattr(audio, "file_id", None)
        if fid:
            return "audio", "audio", fid

    voice = getattr(message, "voice", None)
    if voice:
        fid = getattr(voice, "file_id", None)
        if fid:
            return "audio", "voice_note", fid

    document = getattr(message, "document", None)
    if document:
        fid = getattr(document, "file_id", None)
        if fid:
            return "tg-document", "document", fid

    return None


def _rich_media_from_message(message):
    media = _message_media(message)
    if not media:
        return None, None
    tag, media_type, file_id = media
    return f'<{tag} src="tg://{media_type}?id=existing_media"/>', {
        "id": "existing_media",
        "media": {"type": media_type, "media": file_id},
    }


async def edit_text(chat_id: int, message_id: int, text: str, markup: Any, *, client=None) -> bool:
    rich_html = markup_to_rich_html(text, markup)
    if rich_html is None:
        return False

    # IMPORTANT: editMessageText can replace a media message with text if the
    # current media is not included again. Fetch and re-attach it first.
    current = None
    if client is not None:
        try:
            current = await client.get_messages(chat_id, message_id)
        except Exception:
            current = None

    media_tag, media_def = _rich_media_from_message(current)
    if media_tag:
        rich_html = media_tag + "<br>" + rich_html

    payload = {"html": rich_html}
    if media_def:
        payload["media"] = [media_def]

    await request("editMessageText", {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "rich_message": payload,
    })
    return True


async def send_text(chat_id: int, text: str, markup: Any, *, reply_to_message_id: int | None = None, **kwargs):
    rich_html = markup_to_rich_html(text, markup)
    if rich_html is None:
        return None
    data = {"chat_id": int(chat_id), "rich_message": {"html": rich_html}}
    if reply_to_message_id:
        data["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    for key in ("disable_notification", "protect_content", "allow_paid_broadcast", "message_thread_id"):
        if key in kwargs and kwargs[key] is not None:
            data[key] = kwargs[key]
    result = await request("sendRichMessage", data)
    return result.get("result")


async def send_media(chat_id: int, media_type: str, source: str, caption: str, markup: Any, **kwargs):
    rich_html = markup_to_rich_html(caption or "", markup)
    if rich_html is None:
        return None

    media_id = "rich_media"
    tag = "img" if media_type == "photo" else "video" if media_type in ("video", "animation") else "audio" if media_type in ("audio", "voice") else "tg-document"
    api_media_type = "photo" if media_type == "photo" else "video" if media_type in ("video", "animation") else "audio" if media_type in ("audio", "voice") else "document"
    rich_html = f'<{tag} src="tg://{api_media_type}?id={media_id}"/><br>' + rich_html

    data = {
        "chat_id": int(chat_id),
        "rich_message": {
            "html": rich_html,
            "media": [{"id": media_id, "media": {"type": media_type if media_type != "voice" else "voice_note", "media": source}}],
        },
    }
    if kwargs.get("reply_to_message_id"):
        data["reply_parameters"] = {"message_id": int(kwargs["reply_to_message_id"])}
    result = await request("sendRichMessage", data)
    return result.get("result")


async def edit_media(chat_id: int, message_id: int, media, caption: str, markup: Any, *, client=None, **kwargs):
    """Convert an existing media message to Rich while retaining its media."""
    if not is_inline_markup(markup):
        return False

    current = None
    if client is not None:
        try:
            current = await client.get_messages(chat_id, message_id)
        except Exception:
            pass

    media_tag, media_def = _rich_media_from_message(current)
    if not media_def:
        # Fallback for InputMedia* objects carrying a reusable file_id/URL.
        source = getattr(media, "media", None) or getattr(media, "file_id", None)
        if source:
            kind = media.__class__.__name__.lower()
            media_type = "photo" if "photo" in kind else "video" if "video" in kind or "animation" in kind else "audio" if "audio" in kind or "voice" in kind else "document"
            tag = "img" if media_type == "photo" else "video" if media_type == "video" else "audio" if media_type == "audio" else "tg-document"
            media_tag = f'<{tag} src="tg://{media_type}?id=existing_media"/>'
            media_def = {"id": "existing_media", "media": {"type": media_type, "media": source}}

    rich_html = markup_to_rich_html(caption or "", markup)
    if rich_html is None:
        return False
    if media_tag:
        rich_html = media_tag + "<br>" + rich_html

    payload = {"html": rich_html}
    if media_def:
        payload["media"] = [media_def]

    await request("editMessageText", {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "rich_message": payload,
    })
    return True
