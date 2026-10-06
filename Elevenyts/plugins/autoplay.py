# ==========================================================
  # Copyright (c) 2026 ArtistBots
  # All Rights Reserved.
  #
  # Project      : ArtistBots API Telegram Music Bot
  # Powered By   : Artist
  # Type         : API Based Telegram Music Bot
  #
  # Bot          : @ArtistApibot
  # Channel      : https://t.me/artistbots
  # GitHub       : https://github.com/elevenyts
  #
  # Unauthorized copying, modification, or redistribution
  # of this source code without permission is prohibited.
  # ==========================================================

from pyrogram import filters, types

from Elevenyts import app, db, tune, lang
from Elevenyts.helpers import can_manage_vc


@app.on_message(filters.command(["autoplay", "cautoplay"]) & filters.group & ~app.bl_users)
@can_manage_vc
async def _autoplay(_, m: types.Message):
    try:
        await m.delete()
    except Exception:
        pass

    # Determine target chat_id:
    # - /cautoplay → explicitly use linked channel
    # - /autoplay  → use channel if channel-play is active, else group
    is_explicit_channel = m.command[0].lower() == "cautoplay"
    chat_id = m.chat.id

    channel_id = await db.get_cmode(m.chat.id)

    if is_explicit_channel:
        if channel_id is None:
            return await m.reply_text(
                "<blockquote>❌ Channel play is not enabled.\n\n"
                "Use /channelplay to enable it first.</blockquote>"
            )
        chat_id = channel_id
    elif channel_id is not None:
        # /autoplay in a group that has channel-play active → target channel
        chat_id = channel_id

    current = await db.get_autoplay(chat_id)

    # Toggle autoplay
    new_state = not current
    await db.set_autoplay(chat_id, new_state)

    # Keep the live call engine synchronized with the saved autoplay state.
    try:
        await tune.set_autoplay(chat_id, new_state)
    except Exception:
        pass

    if new_state:
        text = (
            "<blockquote>🎵 <b>Autoplay: ON</b>\n\n"
            "Ek baar /play karo — baaki songs apne aap bajte rahenge!\n"
            "Queue khatam hone par main automatically similar song dhundh kar bajata rahunga.\n\n"
            "Band karne ke liye dobara /autoplay karo.</blockquote>"
        )
    else:
        text = (
            "<blockquote>⏹ <b>Autoplay: OFF</b>\n\n"
            "Autoplay band kar diya. Queue khatam hone par playback ruk jayega.\n\n"
            "Dobara chalu karne ke liye /autoplay karo.</blockquote>"
        )

    await m.reply_text(text)


# ==========================================================
# Smart Queue + Album Mode (self-contained)
# These handlers intentionally live in autoplay.py so they are
# loaded by the existing plugin discovery on every deployment.
# ==========================================================
import asyncio as _sq_asyncio
import re as _sq_re
from pyrogram import filters as _sq_filters, types as _sq_types
from Elevenyts import queue as _sq_queue, yt as _sq_yt, config as _sq_config
from Elevenyts.helpers._play import checkUB as _sq_checkUB


def _sq_is_playlist(value: str) -> bool:
    return bool(_sq_re.search(r"(?:youtube\\.com|youtu\\.be).*(?:[?&]list=|/playlist\\?list=)", value or "", _sq_re.I))


def _sq_existing(chat_id: int):
    return {str(getattr(x, "id", "") or "") for x in _sq_queue.get_queue(chat_id)}


async def _sq_build(chat_id: int, user: str, count: int = 5):
    current = _sq_queue.get_current(chat_id)
    if not current:
        return []
    existing = _sq_existing(chat_id)
    title = getattr(current, "ytitle", None) or getattr(current, "title", "")
    channel = getattr(current, "channel_name", None)
    clean = _sq_re.sub(r"\\s*[-|].*", "", title or "").strip()
    queries = []
    if clean:
        queries.extend([f"{clean} similar songs", f"songs like {clean}", f"{clean} best songs"])
    if channel:
        queries.append(f"{channel} songs")
    found_tracks = []
    for q in queries:
        try:
            results = await _sq_yt.search_many(q, getattr(current, "message_id", 0), limit=8)
        except Exception:
            results = []
        for item in results:
            iid = str(getattr(item, "id", "") or "")
            if not iid or iid in existing or any(str(getattr(x, "id", "") or "") == iid for x in found_tracks):
                continue
            if getattr(item, "is_live", False):
                continue
            item.user = user
            found_tracks.append(item)
            if len(found_tracks) >= count:
                return found_tracks
    return found_tracks


@app.on_message(_sq_filters.command(["smartqueue", "smartq"]) & _sq_filters.group & ~app.bl_users)
@lang.language()
@_sq_checkUB
async def _smartqueue_command(_, message: _sq_types.Message):
    if not await db.get_call(message.chat.id):
        return await message.reply_text("<blockquote>🎵 Nothing is playing right now.</blockquote>")
    status = await message.reply_text("<blockquote>🧠 <b>Building Smart Queue…</b>\nFinding tracks related to the current song.</blockquote>")
    tracks = await _sq_build(message.chat.id, message.from_user.mention, 5)
    if not tracks:
        return await status.edit_text("<blockquote>🧠 I couldn't find related tracks right now. Try again in a moment.</blockquote>")
    for track in tracks:
        _sq_queue.add(message.chat.id, track)
    lines = ["<blockquote>🧠 <b>SMART QUEUE</b>", f"Added <b>{len(tracks)}</b> related tracks:\n"]
    lines.extend(f"<b>{i}.</b> {t.title}" for i, t in enumerate(tracks, 1))
    lines.append("\n⚡ Added to the current queue.</blockquote>")
    await status.edit_text("\n".join(lines))
    try:
        from Elevenyts import preload as _sq_preload
        _sq_asyncio.create_task(_sq_preload.start_preload(message.chat.id, count=min(2, len(tracks))))
    except Exception:
        pass


@app.on_message(_sq_filters.command("album") & _sq_filters.group & ~app.bl_users)
@lang.language()
@_sq_checkUB
async def _album_command(_, message: _sq_types.Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<blockquote>💿 <b>Album Mode</b>\n\n"
            "Use <code>/album Artist - Album Name</code>\n"
            "or <code>/album &lt;YouTube playlist URL&gt;</code>.\n\n"
            "A YouTube playlist URL gives the exact album track order.</blockquote>"
        )
    query = " ".join(message.command[1:]).strip()
    status = await message.reply_text("<blockquote>💿 <b>Loading Album Mode…</b>\nPreparing tracks in order.</blockquote>")
    try:
        if _sq_is_playlist(query):
            tracks = await _sq_yt.playlist(_sq_config.PLAYLIST_LIMIT, message.from_user.mention, query)
        else:
            tracks = await _sq_yt.search_many(f"{query} album songs", status.id, limit=min(_sq_config.PLAYLIST_LIMIT, 12))
    except Exception as e:
        tracks = []
        try:
            await status.edit_text(f"<blockquote>❌ <b>Album lookup failed.</b>\n<code>{str(e)[:250]}</code></blockquote>")
        except Exception:
            pass
        return
    if not tracks:
        return await status.edit_text("<blockquote>❌ <b>Album not found.</b>\n\nTry <code>Artist - Album Name</code> or an exact YouTube album playlist URL.</blockquote>")
    existing = _sq_existing(message.chat.id)
    unique=[]
    for track in tracks:
        iid=str(getattr(track,"id","") or "")
        if iid and iid not in existing and not any(str(getattr(x,"id","") or "") == iid for x in unique):
            track.user=message.from_user.mention
            unique.append(track)
    if not unique:
        return await status.edit_text("<blockquote>💿 All album tracks are already in the queue.</blockquote>")
    if not await db.get_call(message.chat.id):
        first=unique.pop(0)
        first.file_path=await _sq_yt.download(first.id, video=getattr(first,"video",False))
        if not first.file_path:
            return await status.edit_text("<blockquote>❌ I couldn't download the first album track.</blockquote>")
        _sq_queue.add(message.chat.id, first)
        try:
            await tune.play_media(chat_id=message.chat.id, message=status, media=first)
        except Exception as e:
            return await status.edit_text(f"<blockquote>❌ Could not start album playback.\n<code>{str(e)[:250]}</code></blockquote>")
    for track in unique:
        _sq_queue.add(message.chat.id, track)
    preview=unique[:8]
    lines=["<blockquote>💿 <b>ALBUM MODE</b>", f"Added <b>{len(unique)}</b> album track{'s' if len(unique)!=1 else ''} to the queue.\n"]
    lines.extend(f"<b>{i}.</b> {t.title}" for i,t in enumerate(preview,1))
    if len(unique)>len(preview): lines.append(f"\n…and {len(unique)-len(preview)} more.")
    lines.append("\n🎧 Enjoy the album.</blockquote>")
    await status.edit_text("\n".join(lines))
