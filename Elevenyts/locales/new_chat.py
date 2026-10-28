# ==========================================================
# New chat + Juno X welcome system
# ==========================================================
from pathlib import Path
from html import escape
import os
import tempfile

from pyrogram import filters, types
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from Elevenyts import app, config, db


# ----------------------------------------------------------
# Personalized welcome image
# ----------------------------------------------------------
async def _make_welcome_image(member, members_count):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    helpers = Path(__file__).resolve().parent.parent / "helpers"
    base_path = helpers / "welcome.png"
    image = Image.open(base_path).convert("RGBA")
    draw = ImageDraw.Draw(image)

    # Noto Sans handles normal names plus many Unicode characters.
    bold_path = helpers / "NotoSans-Bold.ttf"
    regular_path = helpers / "NotoSans-Regular.ttf"
    fallback_bold = helpers / "Raleway-Bold.ttf"
    fallback_regular = helpers / "Inter-Light.ttf"

    def load_font(size, bold=False):
        paths = [
            bold_path if bold else regular_path,
            fallback_bold if bold else fallback_regular,
        ]
        for path in paths:
            try:
                if path.exists():
                    return ImageFont.truetype(str(path), size)
            except Exception:
                pass
        return ImageFont.load_default()

    # Values shown in the image.
    display_name = " ".join(
        part for part in [member.first_name or "", member.last_name or ""] if part
    ).strip()
    if not display_name:
        display_name = member.username or str(member.id)

    username_or_id = f"@{member.username}" if member.username else str(member.id)
    total_value = str(members_count)

    # Avatar circle in the supplied Juno X template.
    avatar_box = (225, 207, 590, 572)
    ax1, ay1, ax2, ay2 = avatar_box
    aw, ah = ax2 - ax1, ay2 - ay1

    avatar_path = None
    try:
        if getattr(member, "photo", None) and getattr(member.photo, "big_file_id", None):
            avatar_path = await app.download_media(member.photo.big_file_id)
    except Exception as e:
        print(f"[WELCOME] PFP download failed for {member.id}: {e}")

    try:
        if avatar_path and os.path.exists(str(avatar_path)):
            avatar = Image.open(str(avatar_path)).convert("RGB")
            side = min(avatar.size)
            left = (avatar.width - side) // 2
            top = (avatar.height - side) // 2
            avatar = avatar.crop((left, top, left + side, top + side))
            avatar = avatar.resize((aw, ah), Image.Resampling.LANCZOS)
        else:
            # Clean default avatar if the user has no PFP.
            avatar = Image.new("RGBA", (aw, ah), (18, 34, 72, 255))
            ad = ImageDraw.Draw(avatar)
            cx, cy = aw // 2, ah // 2
            ad.ellipse((cx - 72, cy - 100, cx + 72, cy + 44), fill=(220, 230, 245, 255))
            ad.rounded_rectangle(
                (cx - 125, cy + 15, cx + 125, cy + 205),
                radius=70,
                fill=(80, 120, 190, 255),
            )
            glow = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            gd.ellipse((15, 15, aw - 15, ah - 15), outline=(0, 220, 255, 180), width=12)
            glow = glow.filter(ImageFilter.GaussianBlur(7))
            avatar = Image.alpha_composite(avatar, glow)

        mask = Image.new("L", (aw, ah), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, aw, ah), fill=255)
        image.paste(avatar.convert("RGBA"), (ax1, ay1), mask)
    finally:
        if avatar_path:
            try:
                Path(str(avatar_path)).unlink(missing_ok=True)
            except Exception:
                pass

    # IMPORTANT: remove the template's example values before writing real values.
    # These coordinates match the Name / Username / Total Members value areas.
    value_boxes = [
        (925, 452, 1435, 516),
        (925, 515, 1435, 580),
        (1005, 590, 1435, 658),
    ]
    for box in value_boxes:
        draw.rounded_rectangle(box, radius=22, fill=(21, 35, 92, 238))

    value_color = (70, 240, 255, 255)
    white = (245, 250, 255, 255)

    def fit_font(text, max_width, start=38, minimum=19):
        # Prefer a single clean line; shrink only when necessary.
        for size in range(start, minimum - 1, -1):
            f = load_font(size, bold=True)
            bbox = draw.textbbox((0, 0), text, font=f)
            if bbox[2] - bbox[0] <= max_width:
                return f
        return load_font(minimum, bold=True)

    # Draw values with stable positions so they never disappear behind labels.
    draw.text(
        (945, 462),
        display_name,
        font=fit_font(display_name, 450),
        fill=value_color,
        stroke_width=0,
    )
    draw.text(
        (955, 527),
        username_or_id,
        font=fit_font(username_or_id, 430, 36, 19),
        fill=value_color,
        stroke_width=0,
    )
    draw.text(
        (1030, 601),
        total_value,
        font=fit_font(total_value, 300, 36, 21),
        fill=white,
        stroke_width=0,
    )

    out = Path(tempfile.gettempdir()) / f"junox_welcome_{member.id}.png"
    image.convert("RGB").save(out, "PNG", optimize=True)
    return str(out)


# ----------------------------------------------------------
# 👋 NEW MEMBER WELCOME
# ----------------------------------------------------------
@app.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(_, message: types.Message):
    try:
        setting = await db.cache.find_one({"_id": f"welcome_{message.chat.id}"})
        welcome_enabled = (
            setting.get("enabled", config.WELCOME_ENABLED)
            if setting
            else config.WELCOME_ENABLED
        )
    except Exception as e:
        welcome_enabled = config.WELCOME_ENABLED
        print(f"[WELCOME] DB setting read failed: {e}; default={welcome_enabled}")

    if not welcome_enabled:
        return

    for member in message.new_chat_members:
        # Do not welcome the bot itself; its separate bot-added message handles that.
        if member.id == app.id:
            continue

        image_path = None
        try:
            try:
                members_count = await app.get_chat_members_count(message.chat.id)
            except Exception:
                members_count = "Unknown"

            image_path = await _make_welcome_image(member, members_count)

            name = escape(
                " ".join(
                    part for part in [member.first_name or "", member.last_name or ""] if part
                ).strip()
                or member.username
                or "Friend"
            )
            username = (
                f"@{escape(member.username)}"
                if member.username
                else f"<code>{member.id}</code>"
            )

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
            print(
                f"[WELCOME] Sent: chat={message.chat.id} user={member.id} "
                f"name={display_name if 'display_name' in locals() else name}"
            )
        except Exception as e:
            print(f"[WELCOME] Failed for user {member.id}: {type(e).__name__}: {e}")
        finally:
            if image_path:
                try:
                    Path(image_path).unlink(missing_ok=True)
                except Exception:
                    pass


# ----------------------------------------------------------
# ⚙️ /WELCOME ON|OFF
# ----------------------------------------------------------
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
            enabled = (
                current.get("enabled", config.WELCOME_ENABLED)
                if current
                else config.WELCOME_ENABLED
            )
        except Exception:
            enabled = config.WELCOME_ENABLED
        status = "ON 🟢" if enabled else "OFF 🔴"
        return await message.reply_text(
            f"<b>Welcome System: {status}</b>\n\n"
            "Use <code>/welcome on</code> or <code>/welcome off</code>."
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
            f"❌ Could not save the setting to MongoDB.\n<code>{escape(str(e))}</code>"
        )

    await message.reply_text(
        "✅ <b>Welcome system is now ON.</b>\nNew members will receive the Juno X welcome message."
        if enabled
        else
        "🔴 <b>Welcome system is now OFF.</b>\nNew members will not receive the welcome message."
    )


# ----------------------------------------------------------
# 🟢 BOT ADDED IN GROUP
# ----------------------------------------------------------
@app.on_message(filters.new_chat_members & filters.group)
async def new_chat_member(_, message: types.Message):
    for member in message.new_chat_members:
        if member.id == app.id:
            try:
                await message.reply_text(
                    f"🎉 <b>Thanks for adding me to {escape(message.chat.title or 'the group')}!</b>\n\n"
                    "🎵 <b>Juno X music</b> is ready to play.\n"
                    "Use the bot's music commands to get started!"
                )
            except Exception as e:
                print(f"[BOT-ADDED] Failed: {e}")
