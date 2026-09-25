"""Convert ordinary inline keyboards into Telegram Rich Message buttons."""
import html
import urllib.parse
import aiohttp
from typing import Any

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
    url = _attr(button, "url")
    copy = _attr(button, "copy_text")
    if copy is not None and not isinstance(copy, str):
        copy = _attr(copy, "text")

    if callback is not None:
        # Rich callback buttons may use the link style; all other keyboard
        # styles map directly to Rich Message styles.
        return f'<tg-button type="callback_data" style="{style}" data="{_escape_attr(callback)}">{text}</tg-button>'
    if url is not None:
        return f'<tg-button type="url" style="{style}" url="{_escape_attr(url)}">{text}</tg-button>'
    if copy is not None:
        return f'<tg-button type="copy_text" style="{style}" text="{_escape_attr(copy)}">{text}</tg-button>'

    web_app = _attr(button, "web_app")
    if web_app:
        web_url = _attr(web_app, "url") or _attr(web_app, "url")
        if web_url:
            return f'<tg-button type="web_app" style="{style}" url="{_escape_attr(web_url)}">{text}</tg-button>'

    switch = _attr(button, "switch_inline_query")
    if switch is not None:
        return f'<tg-button type="switch_inline_query" style="{style}" query="{_escape_attr(switch)}">{text}</tg-button>'
    switch_current = _attr(button, "switch_inline_query_current_chat")
    if switch_current is not None:
        return f'<tg-button type="switch_inline_query_current_chat" style="{style}" query="{_escape_attr(switch_current)}">{text}</tg-button>'

    return f'<tg-button type="disabled" style="{style}">{text}</tg-button>'


def markup_to_rich_html(text: str, markup: Any) -> str | None:
    """Build a Rich HTML message from a Pyrogram/Kurigram inline keyboard."""
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return None
    body = str(text or "")
    rich_rows = []
    for row in rows:
        buttons = [_button_html(button) for button in row]
        if buttons:
            rich_rows.append('<tg-button-row align="center">' + "".join(buttons) + "</tg-button-row>")
    return body + ("\n\n" + "\n".join(rich_rows) if rich_rows else "")


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


async def edit_text(chat_id: int, message_id: int, text: str, markup: Any) -> bool:
    rich_html = markup_to_rich_html(text, markup)
    if rich_html is None:
        return False
    await request("editMessageText", {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "rich_message": {"html": rich_html},
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
    uri_type = "photo" if media_type == "photo" else "video" if media_type in ("video", "animation") else "audio" if media_type in ("audio", "voice") else "document"
    rich_html = f'<{tag} src="tg://{uri_type}?id={media_id}"/>\n' + rich_html
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
