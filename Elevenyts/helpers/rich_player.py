# Rich Telegram music-player message support (Bot API 10.3+).
# Uses Telegram's Rich HTML <tg-button>/<tg-button-row> controls.

import html
import json
import os
from dataclasses import dataclass
from typing import Optional

import aiohttp

from Elevenyts import config, queue


@dataclass
class RichSentMessage:
    id: int
    photo_ref: Optional[str] = None


_player_photos: dict[tuple[int, int], str] = {}


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def _format_time(seconds: int, duration: int) -> str:
    seconds = max(0, int(seconds or 0))
    if duration >= 3600:
        import time
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    import time
    return time.strftime("%M:%S", time.gmtime(seconds))


def _progress(media, timer: str | None = None) -> str:
    duration = int(getattr(media, "duration_sec", 0) or 0)
    if timer:
        return timer
    if not duration:
        return "LIVE"
    played = max(0, min(int(getattr(media, "time", 0) or 0), duration))
    length = 12
    filled = int(round(length * played / duration)) if duration else 0
    bar = "—" * filled + "●" + "—" * (length - filled)
    return f"{_format_time(played, duration)} {bar} {_format_time(duration, duration)}"


def player_controls_html(chat_id: int, media, *, timer: str | None = None,
                         playing: bool = True, remove: bool = False) -> str:
    """Return Telegram Rich HTML controls. These are real callback buttons."""
    if remove:
        return ""

    state_action = "pause" if playing else "resume"
    state_label = "Ⅱ Pause" if playing else "▶ Resume"
    upcoming = max(0, len(queue.get_queue(chat_id)) - 1)
    progress = _progress(media, timer)

    return (
        "\n\n"
        f'<blockquote>⏱ {html.escape(progress)}</blockquote>'
        f'<tg-button-row align="center">'
        f'<tg-button type="callback_data" style="danger" data="controls replay {chat_id}">↻ Replay</tg-button>'
        f'<tg-button type="callback_data" style="primary" data="controls {state_action} {chat_id}">{state_label}</tg-button>'
        f'<tg-button type="callback_data" data="controls skip {chat_id}">» Skip</tg-button>'
        f'</tg-button-row>'
        f'<tg-button-row align="center">'
        f'<tg-button type="callback_data" data="controls queue {chat_id}">≡ Queue · {upcoming}</tg-button>'
        f'</tg-button-row>'
    )


def build_player_html(base_html: str, chat_id: int, media, *, timer: str | None = None,
                      playing: bool = True, remove: bool = False) -> str:
    return base_html + player_controls_html(
        chat_id, media, timer=timer, playing=playing, remove=remove
    )


def _extract_photo_id(result: dict) -> str | None:
    """Best-effort extraction of a Telegram photo file_id from RichMessage JSON."""
    try:
        msg = result.get("result") or {}
        rich = msg.get("rich_message") or {}
        for block in rich.get("blocks", []) or []:
            if block.get("type") != "photo":
                continue
            photos = block.get("photo") or []
            if photos:
                # Largest/last PhotoSize normally has the most useful file_id.
                return photos[-1].get("file_id")
    except Exception:
        pass
    return None


async def _request(method: str, *, data: dict, file_path: str | None = None) -> dict:
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if file_path and os.path.isfile(file_path):
            form = aiohttp.FormData()
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                form.add_field(key, str(value))
            with open(file_path, "rb") as fp:
                form.add_field(
                    "player_cover",
                    fp,
                    filename=os.path.basename(file_path),
                    content_type="image/jpeg",
                )
                async with session.post(_api(method), data=form) as response:
                    payload = await response.json(content_type=None)
        else:
            async with session.post(_api(method), json=data) as response:
                payload = await response.json(content_type=None)

    if not payload.get("ok"):
        raise RuntimeError(payload.get("description", f"Telegram {method} failed"))
    return payload


async def send_player_message(chat_id: int, base_html: str, photo: str,
                              media, *, timer: str | None = None,
                              playing: bool = True) -> RichSentMessage:
    """Send a persistent Rich Message with embedded photo + callback controls."""
    local_photo = photo if photo and os.path.isfile(photo) else None
    if local_photo:
        html_text = build_player_html(
            base_html, chat_id, media, timer=timer, playing=playing
        )
        # Reference the uploaded photo through a message-local rich-media id.
        html_text = f'<img src="tg://photo?id=player_cover"/>\n{html_text}'
        rich = {
            "html": html_text,
            "media": [{
                "id": "player_cover",
                "media": {"type": "photo", "media": "attach://player_cover"},
            }],
        }
        payload = await _request(
            "sendRichMessage",
            data={"chat_id": chat_id, "rich_message": rich},
            file_path=local_photo,
        )
    else:
        photo_ref = photo or config.DEFAULT_THUMB
        if not str(photo_ref).startswith(("http://", "https://", "tg://")):
            # A Telegram file_id can also be bound to a rich photo reference.
            html_text = f'<img src="tg://photo?id=player_cover"/>\n{build_player_html(base_html, chat_id, media, timer=timer, playing=playing)}'
            rich = {
                "html": html_text,
                "media": [{
                    "id": "player_cover",
                    "media": {"type": "photo", "media": str(photo_ref)},
                }],
            }
        else:
            html_text = f'<img src="{html.escape(str(photo_ref), quote=True)}"/>\n{build_player_html(base_html, chat_id, media, timer=timer, playing=playing)}'
            rich = {"html": html_text}
        payload = await _request(
            "sendRichMessage",
            data={"chat_id": chat_id, "rich_message": rich},
        )

    result = payload["result"]
    photo_id = _extract_photo_id(payload)
    # If Telegram returned the normal rich message object without exposing a photo
    # id, keep the original reference; HTTP URLs remain valid for edits.
    if not photo_id and not local_photo:
        photo_id = photo if str(photo).startswith(("http://", "https://")) else None
    msg_id = int(result["message_id"])
    if not photo_id and local_photo:
        # Some Bot API responses don't expose rich photo sizes. Resolve the
        # uploaded rich message once through the existing Pyrogram client.
        try:
            from Elevenyts import app
            msg = await app.get_messages(chat_id, msg_id)
            if getattr(msg, "photo", None):
                photo_id = msg.photo.file_id
        except Exception:
            pass
    if photo_id:
        _player_photos[(chat_id, msg_id)] = photo_id
    return RichSentMessage(id=msg_id, photo_ref=photo_id)


async def edit_player_message(chat_id: int, message_id: int, base_html: str, media,
                              *, timer: str | None = None, playing: bool = True,
                              remove: bool = False) -> bool:
    """Edit an existing Rich Message while preserving its embedded cover."""
    photo_ref = _player_photos.get((chat_id, message_id), config.DEFAULT_THUMB)
    if photo_ref and str(photo_ref).startswith(("http://", "https://")):
        html_text = f'<img src="{html.escape(str(photo_ref), quote=True)}"/>\n'
        rich = {"html": html_text + build_player_html(base_html, chat_id, media, timer=timer, playing=playing, remove=remove)}
    else:
        html_text = '<img src="tg://photo?id=player_cover"/>\n'
        rich = {
            "html": html_text + build_player_html(base_html, chat_id, media, timer=timer, playing=playing, remove=remove),
            "media": [{"id": "player_cover", "media": {"type": "photo", "media": str(photo_ref)}}],
        }

    try:
        await _request(
            "editMessageText",
            data={
                "chat_id": chat_id,
                "message_id": message_id,
                "rich_message": rich,
            },
        )
        return True
    except Exception:
        return False


async def delete_player_message(chat_id: int, message_id: int) -> bool:
    try:
        await _request("deleteMessage", data={"chat_id": chat_id, "message_id": message_id})
        _player_photos.pop((chat_id, message_id), None)
        return True
    except Exception:
        return False
