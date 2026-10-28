# ==========================================================
# New chat + new member welcome system for Juno X music
# ==========================================================
from pyrogram import filters, types
from pyrogram.errors import ChatAdminRequired, ChannelPrivate
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from Elevenyts import app, config, db


# ==========================================
# 👋 NEW MEMBER WELCOME
# ==========================================
@app.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(_, message: types.Message):
    # Per-group ON/OFF setting. If a group has never changed the setting,
    # use WELCOME_ENABLED from the environment as the default.
    setting = await db.cache.find_one({"_id": f"welcome_{message.chat.id}"})
    welcome_enabled = setting.get("enabled", config.WELCOME_ENABLED) if setting else config.WELCOME_ENABLED
    if not welcome_enabled:
        return

    for member in message.new_chat_members:
        # Do not welcome the bot itself here; its own join notification is handled below.
        if member.id == app.id:
            continue

        chat = message.chat
        try:
            members_count = await app.get_chat_members_count(chat.id)
        except Exception:
            members_count = "Unknown"

        name = member.first_name or "Friend"
        username = f"@{member.username}" if member.username else "No username"
        user_link = member.mention

        caption = f"""<b>╭━━━〔 ✨ NEW MEMBER 〕━━━╮</b>

<b>👋 Welcome to Our Group!</b>

<b>👤 Name:</b> {name}
<b>🆔 ID:</b> <code>{member.id}</code>
<b>🔗 Username:</b> {username}
<b>👥 Total Members:</b> {members_count}

<b>💙 Enjoy the group and have fun!</b>

<b>🎵 Juno X music</b>
<b>╰━━━━━━━━━━━━━━━━━━━━╯</b>"""

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("👤 VIEW MEMBER", url=f"tg://user?id={member.id}")]]
        )

        try:
            # Use the bundled Juno X welcome artwork.
            await app.send_photo(
                chat_id=chat.id,
                photo=config.WELCOME_IMG,
                caption=caption,
                reply_markup=keyboard,
            )
        except Exception as e:
            print(f"Failed to send welcome message: {e}")


# ==========================================
# ⚙️ /WELCOME ON|OFF (GROUP ADMINS / OWNER)
# ==========================================
@app.on_message(filters.command("welcome") & filters.group)
async def welcome_setting(_, message: types.Message):
    user = message.from_user
    if not user:
        return

    # Owner can always change it. Group admins can also change it.
    is_owner = user.id == config.OWNER_ID
    is_admin = False
    if not is_owner:
        try:
            member = await app.get_chat_member(message.chat.id, user.id)
            is_admin = bool(member.privileges and (member.privileges.can_change_info or member.privileges.can_delete_messages))
        except Exception:
            is_admin = False

    if not (is_owner or is_admin):
        return await message.reply_text("❌ Only the group admins can change the welcome setting.")

    if len(message.command) < 2 or message.command[1].lower() not in {"on", "off"}:
        current = await db.cache.find_one({"_id": f"welcome_{message.chat.id}"})
        enabled = current.get("enabled", config.WELCOME_ENABLED) if current else config.WELCOME_ENABLED
        status = "ON 🟢" if enabled else "OFF 🔴"
        return await message.reply_text(
            f"<b>Welcome System: {status}</b>\n\nUse <code>/welcome on</code> or <code>/welcome off</code>."
        )

    enabled = message.command[1].lower() == "on"
    await db.cache.update_one(
        {"_id": f"welcome_{message.chat.id}"},
        {"$set": {"enabled": enabled}},
        upsert=True,
    )

    status = "ON 🟢" if enabled else "OFF 🔴"
    text = (
        "✅ <b>Welcome system is now ON.</b>\nNew members will receive the Juno X music welcome message."
        if enabled
        else
        "🔴 <b>Welcome system is now OFF.</b>\nNew members will not receive the welcome message."
    )
    await message.reply_text(text)


# ==========================================
# 🟢 BOT ADDED IN GROUP
# ==========================================
@app.on_message(filters.new_chat_members & filters.group)
async def new_chat_member(_, message: types.Message):
    for member in message.new_chat_members:
        if member.id == app.id:
            chat = message.chat
            chat_name = chat.title
            chat_id = chat.id
            chat_username = f"@{chat.username}" if chat.username else "ᴘʀɪᴠᴀᴛᴇ ɢʀᴏᴜᴘ"

            try:
                members_count = await app.get_chat_members_count(chat_id)
            except Exception:
                members_count = "ᴜɴᴋɴᴏᴡɴ"

            added_by = message.from_user
            added_by_name = added_by.mention if added_by else "ᴜɴᴋɴᴏᴡɴ"

            try:
                if chat.username:
                    chat_link = f"https://t.me/{chat.username}"
                else:
                    bot_member = await app.get_chat_member(chat_id, app.id)
                    if bot_member.privileges and bot_member.privileges.can_invite_users:
                        chat_link = await app.export_chat_invite_link(chat_id)
                    else:
                        chat_link = "❌ ɴᴏ ɪɴᴠɪᴛᴇ ᴘᴇʀᴍɪssɪᴏɴ"
            except ChatAdminRequired:
                chat_link = "❌ ʙᴏᴛ ɴᴏᴛ ᴀᴅᴍɪɴ"
            except Exception:
                chat_link = "❌ ᴜɴᴀʙʟᴇ ᴛᴏ ɢᴇᴛ ʟɪɴᴋ"

            text = f"""<blockquote>🟢 <b>˹˹𝐉𝐮𝐧𝐨 𝐗 ᴍᴜꜱɪᴄ˼ ᴀᴅᴅᴇᴅ ɪɴ ᴀ ɴᴇᴡ ɢʀᴏᴜᴘ</b></blockquote>

<blockquote>
🔖 <b>ᴄʜᴀᴛ ɴᴀᴍᴇ:</b> {chat_name}
🆔 <b>ᴄʜᴀᴛ ɪᴅ:</b> <code>{chat_id}</code>
👤 <b>ᴄʜᴀᴛ ᴜꜱᴇʀɴᴀᴍᴇ:</b> {chat_username}
🔗 <b>ᴄʜᴀᴛ ʟɪɴᴋ:</b> {chat_link}
👥 <b>ɢʀᴏᴜᴘ ᴍᴇᴍʙᴇʀs:</b> {members_count}
🤵 <b>ᴀᴅᴅᴇᴅ ʙʏ:</b> {added_by_name}
</blockquote>"""

            try:
                await app.send_photo(
                    chat_id=config.LOGGER_ID,
                    photo=config.START_IMG,
                    caption=text,
                )
            except Exception as e:
                print(f"Failed to send new chat notification: {e}")
            break


# ==========================================
# 🔴 BOT REMOVED
# ==========================================
@app.on_message(filters.left_chat_member & filters.group)
async def left_chat_member(_, message: types.Message):
    if message.left_chat_member.id == app.id:
        chat = message.chat
        chat_name = chat.title
        chat_id = chat.id
        chat_username = f"@{chat.username}" if chat.username else "ᴘʀɪᴠᴀᴛᴇ ɢʀᴏᴜᴘ"
        removed_by = message.from_user
        removed_by_name = removed_by.mention if removed_by else "ᴜɴᴋɴᴏᴡɴ"

        try:
            if chat.username:
                chat_link = f"https://t.me/{chat.username}"
            else:
                bot_member = await app.get_chat_member(chat_id, app.id)
                if bot_member.privileges and bot_member.privileges.can_invite_users:
                    chat_link = await app.export_chat_invite_link(chat_id)
                else:
                    chat_link = "❌ ɴᴏ ɪɴᴠɪᴛᴇ ᴘᴇʀᴍɪssɪᴏɴ"
        except Exception:
            chat_link = "❌ ᴜɴᴀʙʟᴇ ᴛᴏ ɢᴇᴛ ʟɪɴᴋ"

        text = f"""<blockquote>🔴 <b>˹𝐉𝐮𝐧𝐨 𝐗 ᴍᴜꜱɪᴄ˼ ʀᴇᴍᴏᴠᴇᴅ ꜰʀᴏᴍ ᴀ ɢʀᴏᴜᴘ</b></blockquote>

<blockquote>
🔖 <b>ᴄʜᴀᴛ ɴᴀᴍᴇ:</b> {chat_name}
🆔 <b>ᴄʜᴀᴛ ɪᴅ:</b> <code>{chat_id}</code>
👤 <b>ᴄʜᴀᴛ ᴜꜱᴇʀɴᴀᴍᴇ:</b> {chat_username}
🔗 <b>ᴄʜᴀᴛ ʟɪɴᴋ:</b> {chat_link}
🚫 <b>ʀᴇᴍᴏᴠᴇᴅ ʙʏ:</b> {removed_by_name}
</blockquote>"""

        try:
            await app.send_photo(
                chat_id=config.LOGGER_ID,
                photo=config.START_IMG,
                caption=text,
            )
        except Exception as e:
            print(f"Failed to send left chat notification: {e}")


# ==========================================
# 🔗 /LINK COMMAND (OWNER ONLY)
# ==========================================
@app.on_message(filters.command("link") & filters.private)
async def get_group_link(_, message: types.Message):
    if message.from_user.id != config.OWNER_ID:
        return await message.reply_text("❌ You are not authorized.")

    if len(message.command) < 2:
        return await message.reply_text("⚠️ Usage:\n/link <group_id>")

    try:
        chat_id = int(message.command[1])
    except Exception:
        return await message.reply_text("❌ Invalid group ID")

    try:
        chat = await app.get_chat(chat_id)
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            bot_member = await app.get_chat_member(chat_id, app.id)
            if bot_member.privileges and bot_member.privileges.can_invite_users:
                link = await app.export_chat_invite_link(chat_id)
            else:
                return await message.reply_text("❌ No invite permission")

        await message.reply_text(
            f"🔗 <b>Group Link:</b>\n{link}",
            disable_web_page_preview=True,
        )
    except ChannelPrivate:
        await message.reply_text("❌ Bot is not in that group")
    except ChatAdminRequired:
        await message.reply_text("❌ Bot is not admin")
    except Exception as e:
        await message.reply_text(f"❌ Error:\n{e}")
