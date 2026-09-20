import html
import json
import os
from typing import Optional
import aiohttp

from Elevenyts import config, queue

_PLAYER_PHOTOS: dict[tuple[int, int], str] = {}


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def _time(sec: int, duration: int) -> str:
    import time
    sec = max(0, int(sec or 0))
    return time.strftime("%H:%M:%S" if duration >= 3600 else "%M:%S", time.gmtime(sec))


def progress_text(media, timer: Optional[str] = None) -> str:
    duration = int(getattr(media, "duration_sec", 0) or 0)
    if timer:
        return timer
    if not duration:
        return "LIVE"
    played = max(0, min(int(getattr(media, "time", 0) or 0), duration))
    n = 12
    filled = int(round(n * played / duration))
    bar = "—" * filled + "●" + "—" * (n - filled)
    return f"{_time(played, duration)} {bar} {_time(duration, duration)}"


def controls_html(chat_id: int, media, *, timer: Optional[str] = None,
                  playing: bool = True, remove: bool = False) -> str:
    if remove:
        return ""
    state = "pause" if playing else "resume"
    label = "Ⅱ Pause" if playing else "▶ Resume"
    try:
        upcoming = max(0, len(queue.get_queue(chat_id)) - 1)
    except Exception:
        upcoming = 0
    p = html.escape(progress_text(media, timer))
    return (
        f'<tg-button-row align="center">'
        f'<tg-button type="callback_data" style="danger" data="controls replay {chat_id}">↻ Replay</tg-button>'
        f'<tg-button type="callback_data" style="primary" data="controls {state} {chat_id}">{label}</tg-button>'
        f'<tg-button type="callback_data" data="controls skip {chat_id}">» Skip</tg-button>'
        f'</tg-button-row>'
        f'<tg-button-row align="center">'
        f'<tg-button type="callback_data" data="controls queue {chat_id}">≡ Queue · {upcoming}</tg-button>'
        f'</tg-button-row>'
    )


def rich_html(base_html: str, chat_id: int, media, *, timer=None,
              playing=True, remove=False) -> str:
    if remove:
        return base_html
    # Progress is deliberately a normal rich-text line, matching the screenshot.
    p = html.escape(progress_text(media, timer))
    return f'{base_html}\n\n<blockquote>{p}</blockquote>{controls_html(chat_id, media, timer=timer, playing=playing)}'


async def _request(method: str, data: dict, file_path: Optional[str] = None) -> dict:
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if file_path and os.path.isfile(file_path):
            form = aiohttp.FormData()
            for k, v in data.items():
                form.add_field(k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))
            with open(file_path, "rb") as fp:
                form.add_field("player_cover", fp, filename=os.path.basename(file_path), content_type="image/jpeg")
                async with session.post(_api(method), data=form) as r:
                    result = await r.json(content_type=None)
        else:
            async with session.post(_api(method), json=data) as r:
                result = await r.json(content_type=None)
    if not result.get("ok"):
        raise RuntimeError(result.get("description", f"Telegram {method} failed"))
    return result


async def send_player(chat_id: int, base_html: str, photo, media, *, playing=True) -> int:
    if photo and os.path.isfile(str(photo)):
        rich = {
            "html": f'<img src="tg://photo?id=player_cover"/>\n{rich_html(base_html, chat_id, media, playing=playing)}',
            "media": [{"id": "player_cover", "media": {"type": "photo", "media": "attach://player_cover"}}],
        }
        result = await _request("sendRichMessage", {"chat_id": chat_id, "rich_message": rich}, str(photo))
    else:
        ref = str(photo or config.DEFAULT_THUMB)
        rich = {
            "html": f'<img src="tg://photo?id=player_cover"/>\n{rich_html(base_html, chat_id, media, playing=playing)}',
            "media": [{"id": "player_cover", "media": {"type": "photo", "media": ref}}],
        }
        # If ref is not a file_id/URL, don't let a broken rich request kill playback.
        if not ref.startswith(("http://", "https://")):
            rich["html"] = rich_html(base_html, chat_id, media, playing=playing)
            rich.pop("media", None)
        result = await _request("sendRichMessage", {"chat_id": chat_id, "rich_message": rich})

    msg = result["result"]
    mid = int(msg["message_id"])
    # Rich photo messages expose the same Photo object to Bot API/Pyrogram clients.
    try:
        photos = msg.get("photo") or []
        if photos:
            _PLAYER_PHOTOS[(chat_id, mid)] = photos[-1].get("file_id")
    except Exception:
        pass
    return mid


async def edit_player(chat_id: int, message_id: int, base_html: str, media, *,
                      timer=None, playing=True, remove=False) -> bool:
    if remove:
        try:
            await _request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            _PLAYER_PHOTOS.pop((chat_id, message_id), None)
            return True
        except Exception:
            return False

    photo = _PLAYER_PHOTOS.get((chat_id, message_id))
    rich = {"html": rich_html(base_html, chat_id, media, timer=timer, playing=playing)}
    if photo:
        rich["html"] = f'<img src="tg://photo?id=player_cover"/>\n{rich["html"]}'
        rich["media"] = [{"id": "player_cover", "media": {"type": "photo", "media": photo}}]
    try:
        await _request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "rich_message": rich,
        })
        return True
    except Exception:
        return False


# Backwards-compatible name used by existing plugins.
# Keep this wrapper so older player-update calls continue to work.
async def edit_player_message(chat_id, message_id, base_html, media, *args, **kwargs):
    return await edit_player(
        chat_id,
        message_id,
        base_html,
        media,
        timer=kwargs.get("timer"),
        playing=kwargs.get("playing", True),
        remove=kwargs.get("remove", False),
    )
