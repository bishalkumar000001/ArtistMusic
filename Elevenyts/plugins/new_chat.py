# ==========================================================
# New chat + new member welcome system for Juno X music
# ==========================================================
from pyrogram import filters, types
from pyrogram.errors import ChatAdminRequired, ChannelPrivate
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pathlib import Path

from Elevenyts import app, config, db


# ==========================================
# 👋 NEW MEMBER WELCOME
# ==========================================
async def _make_welcome_image(member, members_count):
    """Create a personalized Juno X welcome image with the member's PFP."""
    from pathlib import Path
    from html import escape
    import os
    import tempfile
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    base_path = Path(__file__).resolve().parent.parent / "helpers" / "welcome.png"
    image = Image.open(base_path).convert("RGBA")
    draw = ImageDraw.Draw(image)

    # Fonts already shipped with the project.
    font_dir = Path(__file__).resolve().parent.parent / "helpers"
    try:
        bold = str(font_dir / "Raleway-Bold.ttf")
        regular = str(font_dir / "Inter-Light.ttf")
        value_font_path = bold
    except Exception:
        value_font_path = None
        regular = None

    def font(size, bold_font=False):
        path = value_font_path if bold_font else regular
        try:
            return ImageFont.truetype(path, size) if path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    # The circular avatar is inside the decorative ring of welcome.png.
    avatar_box = (225, 207, 590, 572)
    ax1, ay1, ax2, ay2 = avatar_box
    aw, ah = ax2 - ax1, ay2 - ay1

    avatar_path = None
    try:
        if getattr(member, "photo", None) and getattr(member.photo, "big_file_id", None):
            avatar_path = await app.download_media(member.photo.big_file_id)
    except Exception as e:
        print(f"Could not download PFP for {member.id}: {e}")

    try:
        if avatar_path and os.path.exists(str(avatar_path)):
            avatar = Image.open(str(avatar_path)).convert("RGB")
            # Center-crop to a square and resize smoothly.
            side = min(avatar.size)
            left = (avatar.width - side) // 2
            top = (avatar.height - side) // 2
            avatar = avatar.crop((left, top, left + side, top + side)).resize((aw, ah), Image.Resampling.LANCZOS)
        else:
            # Generic fallback avatar when the member has no profile photo.
            avatar = Image.new("RGB", (aw, ah), (20, 35, 75))
            ad = ImageDraw.Draw(avatar)
            cx, cy = aw // 2, ah // 2
            ad.ellipse((cx-70, cy-95, cx+70, cy+45), fill=(205, 220, 245))
            ad.rounded_rectangle((cx-125, cy+20, cx+125, cy+205), radius=75, fill=(115, 135, 180))
            # subtle glow
            glow = Image.new("RGBA", avatar.size, (0,0,0,0))
            gd = ImageDraw.Draw(glow)
            gd.ellipse((15,15,aw-15,ah-15), outline=(0,220,255,150), width=12)
            glow = glow.filter(ImageFilter.GaussianBlur(7))
            avatar = Image.alpha_composite(avatar.convert("RGBA"), glow).convert("RGB")

        mask = Image.new("L", (aw, ah), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, aw, ah), fill=255)
        image.paste(avatar.convert("RGBA"), (ax1, ay1), mask)
    finally:
        if avatar_path:
            try:
                Path(avatar_path).unlink(missing_ok=True)
            except Exception:
                pass

    # Cover only the template's example values; keep the labels/design intact.
    cover = (935, 460, 1415, 510)
    cover2 = (935, 515, 1415, 565)
    cover3 = (1015, 610, 1415, 665)
    for box in (cover, cover2, cover3):
        # Match the dark glass panel and add a very subtle transparency.
        draw.rounded_rectangle(box, radius=20, fill=(21, 35, 92, 225))

    def fit_text(text, max_width, start_size=40, min_size=20):
        size = start_size
        while size > min_size:
            f = font(size, True)
            if draw.textbbox((0,0), text, font=f)[2] <= max_width:
                return f
            size -= 1
        return font(min_size, True)

    name = " ".join(x for x in [member.first_name, member.last_name] if x) or "Friend"
    username_value = f"@{member.username}" if member.username else str(member.id)
    total_value = str(members_count)

    # Dynamic values: real member name, username or ID, and current member count.
    value_color = (65, 240, 255, 255)
    draw.text((945, 470), name, font=fit_text(name, 430, 38, 20), fill=value_color)
    draw.text((950, 525), username_value, font=fit_text(username_value, 420, 36, 20), fill=value_color)
    draw.text((1030, 620), total_value, font=fit_text(total_value, 300, 38, 22), fill=(245, 250, 255, 255))

    # Temporary per-user file; Telegram receives this personalized image.
    out = Path(tempfile.gettempdir()) / f"junox_welcome_{member.id}.png"
    image.convert("RGB").save(out, "PNG", optimize=True)
    return str(out)


@app.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(_, message: types.Message):
    """Welcome real users with a personalized PFP/name/username image."""
    try:
        setting = await db.cache.find_one({"_id": f"welcome_{message.chat.id}"})
        welcome_enabled = (
            setting.get("enabled", config.WELCOME_ENABLED)
            if setting else config.WELCOME_ENABLED
        )
    except Exception as e:
        welcome_enabled = config.WELCOME_ENABLED
        print(f"Welcome setting DB read failed: {e}; using default={welcome_enabled}")

    if not welcome_enabled:
        return

    for member in message.new_chat_members:
        if member.id == app.id:
            continue

        image_path = None
        try:
            try:
                members_count = await app.get_chat_members_count(message.chat.id)
            except Exception:
                members_count = "Unknown"

            image_path = await _make_welcome_image(member, members_count)
            from html import escape
            name = escape(" ".join(x for x in [member.first_name, member.last_name] if x) or "Friend")
            username = f"@{escape(member.username)}" if member.username else f"<code>{member.id}</code>"

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

            await app.send_photo(
                chat_id=message.chat.id,
                photo=image_path,
                caption=caption,
                reply_markup=keyboard,
            )
            print(f"Welcome sent for user {member.id} in chat {message.chat.id}")
        except Exception as e:
            print(f"Failed to send welcome for user {member.id}: {type(e).__name__}: {e}")
        finally:
            if image_path:
                try:
                    Path(image_path).unlink(missing_ok=True)
                except Exception:
                    pass


# ==========================================
# ⚙️ /WELCOME ON|OFF (GROUP ADMINS / OWNER)
# ==========================================
@app.on_message(filters.command("welcome") & filters.group)
async def welcome_setting(_, message: types.Message):
    user = message.from_user
    if not user:
        return

    is_owner = user.id == config.OWNER_ID
    is_admin = False
    if not is_owner:
        try:
            member = await app.get_chat_member(message.chat.id, user.id)
            is_admin = bool(
                member.privileges
                and (
                    member.privileges.can_change_info
                    or member.privileges.can_delete_messages
                )
            )
        except Exception:
            is_admin = False

    if not (is_owner or is_admin):
        return await message.reply_text(
            "❌ Only the group admins can change the welcome setting."
        )

    if len(message.command) < 2 or message.command[1].lower() not in {"on", "off"}:
        try:
            current = await db.cache.find_one({"_id": f"welcome_{message.chat.id}"})
            enabled = current.get("enabled", config.WELCOME_ENABLED) if current else config.WELCOME_ENABLED
        except Exception:
            enabled = config.WELCOME_ENABLED
        status = "ON 🟢" if enabled else "OFF 🔴"
        return await message.reply_text(
            f"<b>Welcome System: {status}</b>\n\nUse <code>/welcome on</code> or <code>/welcome off</code>."
        )

    enabled = message.command[1].lower() == "on"
    try:
        await db.cache.update_one(
            {"_id": f"welcome_{message.chat.id}"},
            {"$set": {"enabled": enabled}},
            upsert=True,
        )
    except Exception as e:
        return await message.reply_text(
            f"❌ Could not save the setting to MongoDB.\n<code>{e}</code>"
        )

    if enabled:
        await message.reply_text(
            "✅ <b>Welcome system is now ON.</b>\n"
            "New members will receive the Juno X music welcome message."
        )
    else:
        await message.reply_text(
            "🔴 <b>Welcome system is now OFF.</b>\n"
            "New members will not receive the welcome message."
        )


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
