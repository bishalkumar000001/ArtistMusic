# ==========================================================
# New chat + Juno X personalized welcome system
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

    # Fonts included in the project. Noto Sans is used first because it
    # supports a much wider range of names than the decorative template font.
    regular_path = helpers / "NotoSans-Regular.ttf"
    bold_path = helpers / "NotoSans-Bold.ttf"
    fallback_regular = helpers / "Inter-Light.ttf"
    fallback_bold = helpers / "Raleway-Bold.ttf"

    def load_font(size, bold=False):
        paths = [bold_path if bold else regular_path,
                 fallback_bold if bold else fallback_regular]
        for path in paths:
            try:
                if path.exists():
                    return ImageFont.truetype(str(path), size)
            except Exception:
                continue
        return ImageFont.load_default()

    def clean_name(user):
        first = (getattr(user, "first_name", None) or "").strip()
        last = (getattr(user, "last_name", None) or "").strip()
        return " ".join(x for x in (first, last) if x)

    display_name = clean_name(member)
    if not display_name:
        # Telegram accounts can have no first/last name. Never leave the
        # image field blank in that case.
        display_name = f"User {member.id}"

    username_value = (
        f"@{member.username}" if getattr(member, "username", None)
        else str(member.id)
    )
    total_value = str(members_count)

    # ------------------------------------------------------
    # Avatar: exact circle in the supplied Juno X template.
    # ------------------------------------------------------
    avatar_box = (208, 204, 577, 573)
    ax1, ay1, ax2, ay2 = avatar_box
    aw, ah = ax2 - ax1, ay2 - ay1
    avatar_path = None

    try:
        photo = getattr(member, "photo", None)
        file_id = getattr(photo, "big_file_id", None) if photo else None
        if file_id:
            avatar_path = await app.download_media(file_id)
    except Exception as e:
        print(f"[WELCOME] PFP download failed for {member.id}: {e}")

    try:
        if avatar_path and os.path.exists(str(avatar_path)):
            avatar = Image.open(str(avatar_path)).convert("RGB")
            side = min(avatar.size)
            left = (avatar.width - side) // 2
            top = (avatar.height - side) // 2
            avatar = avatar.crop((left, top, left + side, top + side))
            avatar = avatar.resize((aw, ah), Image.Resampling.LANCZOS).convert("RGBA")
        else:
            # Clean fallback avatar when the Telegram account has no PFP.
            avatar = Image.new("RGBA", (aw, ah), (17, 31, 65, 255))
            ad = ImageDraw.Draw(avatar)
            cx, cy = aw // 2, ah // 2
            ad.ellipse((cx - 62, cy - 105, cx + 62, cy + 19), fill=(225, 235, 250, 255))
            ad.rounded_rectangle((cx - 120, cy - 2, cx + 120, cy + 190), radius=65,
                                 fill=(76, 122, 195, 255))

        mask = Image.new("L", (aw, ah), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, aw - 1, ah - 1), fill=255)
        image.paste(avatar, (ax1, ay1), mask)
    finally:
        if avatar_path:
            try:
                Path(str(avatar_path)).unlink(missing_ok=True)
            except Exception:
                pass

    # ------------------------------------------------------
    # Remove the template's example values while preserving its glass
    # background. A blurred copy of the same region is pasted over the
    # placeholders, so there are no visible boxes/seams.
    # ------------------------------------------------------
    blurred = image.filter(ImageFilter.GaussianBlur(10))
    value_regions = [
        (932, 452, 1450, 518),   # Name value
        (950, 522, 1450, 588),   # Username value
        (1008, 592, 1450, 660),  # Total members value
    ]
    for x1, y1, x2, y2 in value_regions:
        image.paste(blurred.crop((x1, y1, x2, y2)), (x1, y1))
    draw = ImageDraw.Draw(image)

    cyan = (61, 239, 255, 255)
    white = (248, 251, 255, 255)

    def text_width(text, font):
        b = draw.textbbox((0, 0), text, font=font)
        return b[2] - b[0]

    def fit_text(text, max_width, max_size=34, min_size=18):
        # Keep every value on one clean line; shrink long names/usernames.
        for size in range(max_size, min_size - 1, -1):
            font = load_font(size, bold=True)
            if text_width(text, font) <= max_width:
                return font
        return load_font(min_size, bold=True)

    # Values begin after the fixed labels (Name / Username / Total Members).
    name_font = fit_text(display_name, 455, 34, 18)
    user_font = fit_text(username_value, 445, 32, 18)
    total_font = fit_text(total_value, 330, 34, 20)

    # Vertical positions are centered inside each glass row.
    def centered_y(y1, y2, font):
        box = draw.textbbox((0, 0), "Ag", font=font)
        h = box[3] - box[1]
        return y1 + ((y2 - y1 - h) // 2) - box[1]

    draw.text((948, centered_y(452, 517, name_font)), display_name,
              font=name_font, fill=cyan)
    draw.text((960, centered_y(522, 587, user_font)), username_value,
              font=user_font, fill=cyan)
    draw.text((1030, centered_y(592, 660, total_font)), total_value,
              font=total_font, fill=white)

    out = Path(tempfile.gettempdir()) / f"junox_welcome_{member.id}.png"
    image.convert("RGB").save(out, "PNG", optimize=True)
    return str(out)


# ----------------------------------------------------------
# NEW MEMBER WELCOME
# ----------------------------------------------------------
@app.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(_, message: types.Message):
    try:
        setting = await db.cache.find_one({"_id": f"welcome_{message.chat.id}"})
        welcome_enabled = (
            setting.get("enabled", config.WELCOME_ENABLED)
            if setting else config.WELCOME_ENABLED
        )
    except Exception as e:
        welcome_enabled = config.WELCOME_ENABLED
        print(f"[WELCOME] DB setting read failed: {e}; default={welcome_enabled}")

    if not welcome_enabled:
        return

    for member in message.new_chat_members:
        if member.id == app.id:
            continue

        image_path = None
        try:
            try:
                members_count = await app.get_chat_members_count(message.chat.id)
            except Exception as e:
                print(f"[WELCOME] Member count failed: {e}")
                members_count = "-"

            image_path = await _make_welcome_image(member, members_count)

            first = (member.first_name or "").strip()
            last = (member.last_name or "").strip()
            name = " ".join(x for x in (first, last) if x) or f"User {member.id}"
            username = f"@{escape(member.username)}" if member.username else "Not available"

            caption = (
                "<b>╭━━━〔 ✨ NEW MEMBER 〕━━━╮</b>\n\n"
                "👋 <b>Welcome to Our Group!</b>\n\n"
                f"👤 <b>Name:</b> {escape(name)}\n"
                f"🆔 <b>ID:</b> <code>{member.id}</code>\n"
                f"🔗 <b>Username:</b> {username if member.username else f'<code>{member.id}</code>'}\n"
                f"👥 <b>Total Members:</b> {members_count}\n\n"
                "💙 <b>Enjoy the group and have fun!</b>\n\n"
                "🎵 <b>Juno X music</b>\n"
                "<b>╰━━━━━━━━━━━━━━━━━━━━╯</b>"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 VIEW MEMBER", url=f"tg://user?id={member.id}")]
            ])

            await app.send_photo(
                chat_id=message.chat.id,
                photo=image_path,
                caption=caption,
                reply_markup=keyboard,
            )
            print(f"[WELCOME] Sent: chat={message.chat.id} user={member.id} name={name}")

        except Exception as e:
            print(f"[WELCOME] Failed for user {member.id}: {type(e).__name__}: {e}")
        finally:
            if image_path:
                try:
                    Path(image_path).unlink(missing_ok=True)
                except Exception:
                    pass


# ----------------------------------------------------------
# /WELCOME ON | OFF
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
                member.privileges and (
                    member.privileges.can_change_info or
                    member.privileges.can_delete_messages
                )
            )
        except Exception:
            is_admin = False

    if not (is_owner or is_admin):
        return await message.reply_text("❌ Only the group admins can change the welcome setting.")

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
            f"❌ Could not save the setting to MongoDB.\n<code>{escape(str(e))}</code>"
        )

    await message.reply_text(
        "✅ <b>Welcome system is now ON.</b>\nNew members will receive the Juno X welcome message."
        if enabled else
        "🔴 <b>Welcome system is now OFF.</b>\nNew members will not receive the welcome message."
    )


# ----------------------------------------------------------
# BOT ADDED IN GROUP
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
