# ==========================================================
# Copyright (c) 2026 VelocityBots
# All Rights Reserved.
# ==========================================================
import time
import psutil

from pyrogram import filters, types
from Elevenyts import app, tune, boot, config, lang
from Elevenyts.helpers import buttons


@app.on_message(filters.command(["alive", "ping"]) & ~app.bl_users)
@lang.language()
async def _ping(_, m: types.Message):
    # Remove the user's command before preparing the final response.
    try:
        await m.delete()
    except Exception:
        pass

    start = time.time()

    def get_time(s):
        return (lambda r: (f"{r[-1]}, " if r[-1][:-4] != "0" else "") + ":".join(reversed(r[:-1])))(
            [f"{v}{u}" for v, u in zip(
                [s % 60, (s // 60) % 60, (s // 3600) % 24, s // 86400],
                ["s", "m", "h", "days"]
            )]
        )

    uptime = get_time(int(time.time() - boot))

    # Gather the stats before sending anything, so no temporary normal message
    # (such as "Pinging...") appears before the final Rich Message.
    mem = psutil.virtual_memory()
    ram_usage = f"{round(mem.used / (1024 ** 3), 1)}GB / {round(mem.total / (1024 ** 3), 1)}GB"
    cpu_percent = psutil.cpu_percent(interval=0.5)

    from Elevenyts import db
    active_chats = len(await db.get_chats())

    latency = round((time.time() - start) * 1000, 2)
    caption_text = m.lang["ping_pong"].format(
        latency,
        uptime,
        await tune.ping(),
        ram_usage,
        cpu_percent,
        active_chats,
    )
    markup = buttons.ping_markup(m.lang["support"])

    # Send the final photo/caption/buttons in one request. Bot.send_photo routes
    # supported inline keyboards straight through the Rich Message API.
    try:
        await app.send_photo(
            chat_id=m.chat.id,
            photo=config.PING_IMG,
            caption=caption_text,
            reply_markup=markup,
        )
    except Exception:
        # If Rich Message/photo sending is unavailable, send one text fallback;
        # do not create a placeholder message and then edit it.
        await app.send_message(
            chat_id=m.chat.id,
            text=caption_text,
            reply_markup=markup,
        )
