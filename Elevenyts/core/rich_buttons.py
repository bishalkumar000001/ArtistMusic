"""Global Rich Message button renderer.

All Pyrogram inline keyboards used by this bot are converted to Telegram Rich
Message buttons.  The keyboard remains the source of truth: labels, callback
data, URLs, copy text and row order are preserved.
"""
import html
import aiohttp
from typing import Any

from Elevenyts import config


API_BASE = f"https://api.telegram.org/bot{config.BOT_TOKEN}"


def _api(method: str) -> str:
    return f"{API_BASE}/{method}"


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
    if "link" in name:
        return "primary"
    return "primary"


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _button_html(button: Any) -> str:
    """Convert every supported Pyrogram InlineKeyboardButton type."""
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

    login = _attr(button, "login_url")
    if login:
        url = _attr(login, "url")
        if url:
            forward = _attr(login, "forward_text")
            extra = f' forward-text="{_e(forward)}"' if forward else ""
            if _attr(login, "request_write_access", False):
                extra += " request-write-access"
            return f'<tg-button type="login_url" style="{style}" url="{_e(url)}"{extra}>{label}</tg-button>'

    switch = _attr(button, "switch_inline_query")
    if switch is not None:
        return f'<tg-button type="switch_inline_query" style="{style}" query="{_e(switch)}">{label}</tg-button>'

    switch_current = _attr(button, "switch_inline_query_current_chat")
    if switch_current is not None:
        return f'<tg-button type="switch_inline_query_current_chat" style="{style}" query="{_e(switch_current)}">{label}</tg-button>'

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
        return f'<tg-button type="switch_inline_query_chosen_chat" style="{style}" query="{_e(query)}"{flags}>{label}</tg-button>'

    # A callback_game/login variant not understood by the running Pyrogram
    # version should stay visible instead of silently disappearing.
    return f'<tg-button type="disabled" style="{style}">{label}</tg-button>'


def _body(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def is_inline_markup(markup: Any) -> bool:
    return bool(markup is not None and getattr(markup, "inline_keyboard", None))


def markup_to_rich_html(text: str, markup: Any) -> str | None:
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return None
    parts = [_body(text)]
    for row in rows:
        # Rich Message currently permits 1-8 buttons per button block.
        for start in range(0, len(row), 8):
            chunk = row[start:start + 8]
            if chunk:
                parts.append(
                    '<tg-button-row align="center">'
                    + "".join(_button_html(button) for button in chunk)
                    + "</tg-button-row>"
                )
    return "<br>".join(parts)


def _media_from_message(message):
    checks = (
        ("photo", "photo", "photo"),
        ("video", "video", "video"),
        ("animation", "animation", "video"),
        ("audio", "audio", "audio"),
        ("voice", "voice_note", "audio"),
        ("document", "document", "document"),
    )
    for attr, kind, rich_kind in checks:
        obj = getattr(message, attr, None)
        fid = getattr(obj, "file_id", None) if obj else None
        if fid:
            return kind, rich_kind, fid
    return None


def build_rich_payload(message, text: str, markup: Any):
    """Build the same media-reference form already used by the Rich player."""
    body = markup_to_rich_html(text, markup)
    if body is None:
        return None

    media = _media_from_message(message)
    payload = {"html": body}
    if media:
        kind, rich_kind, file_id = media
        # This exact tg:// + media-array pattern is supported by Telegram's
        # Rich Message API and is also used by the bot's existing Rich player.
        payload["html"] = f'<img src="tg://photo?id=rich_media"/>\n{body}' if kind == "photo" else body
        if kind != "photo":
            tag = "video" if kind in ("video", "animation") else "audio" if kind in ("audio", "voice_note") else "tg-document"
            payload["html"] = f'<{tag} src="tg://{rich_kind}?id=rich_media"/>\n{body}'
        payload["media"] = [{
            "id": "rich_media",
            "media": {"type": rich_kind, "media": file_id},
        }]
    return payload


async def _request(method: str, data: dict):
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_api(method), json=data) as response:
            result = await response.json(content_type=None)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", f"Telegram {method} failed"))
    return result


def _send_options(kwargs: dict) -> dict:
    """Keep Bot API options that also apply to sendRichMessage."""
    allowed = {
        "message_thread_id", "direct_messages_topic_id", "disable_notification",
        "protect_content", "allow_paid_broadcast", "message_effect_id",
        "suggested_post_parameters", "reply_parameters", "business_connection_id",
    }
    return {k: v for k, v in kwargs.items() if k in allowed and v is not None}


async def send_rich_for_message(chat_id, text, markup, *, reply_to_message_id=None, **kwargs):
    payload = markup_to_rich_html(text, markup)
    if not payload:
        return None
    data = {"chat_id": int(chat_id), "rich_message": {"html": payload}}
    if reply_to_message_id:
        data["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    data.update(_send_options(kwargs))
    return await _request("sendRichMessage", data)


async def send_rich_for_media(chat_id, text, markup, media_kind, media, *, reply_to_message_id=None, **kwargs):
    """Send a media message and all its inline buttons as one Rich Message."""
    body = markup_to_rich_html(text, markup)
    if not body:
        return None

    rich_kind = {
        "photo": "photo", "video": "video", "animation": "animation",
        "audio": "audio", "voice": "voice_note", "voice_note": "voice_note",
        "document": "document",
    }.get(media_kind, media_kind)
    tag = "img" if rich_kind == "photo" else "video" if rich_kind in ("video", "animation") else "audio" if rich_kind in ("audio", "voice_note") else "tg-document"
    rich = {
        "html": f'<{tag} src="tg://{rich_kind}?id=rich_media"/>\n{body}',
        "media": [{"id": "rich_media", "media": {"type": rich_kind, "media": media}}],
    }
    data = {"chat_id": int(chat_id), "rich_message": rich}
    if reply_to_message_id:
        data["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    data.update(_send_options(kwargs))
    return await _request("sendRichMessage", data)


async def replace_with_rich(message, text: str, markup: Any):
    payload = build_rich_payload(message, text, markup)
    if not payload:
        return message
    data = {"chat_id": int(message.chat.id), "rich_message": payload}
    try:
        reply_id = getattr(message, "reply_to_message_id", None)
        if reply_id:
            data["reply_parameters"] = {"message_id": int(reply_id)}
    except Exception:
        pass

    result = await _request("sendRichMessage", data)
    new_id = int((result.get("result") or {}).get("message_id") or 0)
    if not new_id:
        raise RuntimeError("sendRichMessage returned no message_id")

    await _request("deleteMessage", {
        "chat_id": int(message.chat.id),
        "message_id": int(message.id),
    })

    client = getattr(message, "_client", None)
    if client is not None:
        try:
            fetched = await client.get_messages(int(message.chat.id), new_id)
            if fetched:
                return fetched
        except Exception:
            pass
    return message


async def replace_callback_message(message, text, markup):
    """Replace an edited callback message with its Rich equivalent.

    Callback handlers throughout the bot use query.edit_message_text/caption.
    Replacing the message here makes those existing handlers automatically use
    the same Rich buttons without changing their callbacks or text.
    """
    return await replace_with_rich(message, text, markup)


async def convert_existing(message, text: str, markup: Any) -> bool:
    try:
        await replace_with_rich(message, text, markup)
        return True
    except Exception:
        return False
