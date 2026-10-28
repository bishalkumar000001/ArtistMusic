# ==========================================================
# Juno X Music - New chat + dynamic welcome system
# ==========================================================
from pathlib import Path
from html import escape
import asyncio
import os
import tempfile

from PIL import Image, ImageDraw, ImageChops, ImageFilter, ImageOps
from pyrogram import filters, types
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from Elevenyts import app, config, db
from Elevenyts.helpers._textimg import draw_text

HELPERS = Path(__file__).resolve().parent.parent / "helpers"
CARD_PATH = HELPERS / "welcome.png"
FONT_DIR = HELPERS / "assets" / "fonts"

# Coordinates for the 1671x941 Juno X welcome template.
AV_CENTER = (392, 389)
AV_RADIUS = 164
BADGE_BOX = (285, 526, 500, 594)
BADGE_RADIUS = 34
NAME_X, NAME_TOP, NAME_SIZE, NAME_MAXW = 938, 454, 38, 485
USER_X, USER_TOP, USER_SIZE, USER_MAXW = 938, 548, 34, 485
TOTAL_X, TOTAL_TOP, TOTAL_SIZE, TOTAL_MAXW = 1030, 620, 34, 300
TEXT_COLOR = (61, 239, 255, 255)
WHITE = (248, 251, 255, 255)


def _clean_name(user):
    first = (getattr(user, "first_name", None) or "").strip()
    last = (getattr(user, "last_name", None) or "").strip()
    value = " ".join(x for x in (first, last) if x)
    return " ".join(value.split()) or f"User {user.id}"


def _circle(im, d):
    im = ImageOps.fit(im.convert("RGB"), (d, d), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=255)
    im.putalpha(mask.resize((d, d), Image.Resampling.LANCZOS))
    return im


def _badge_mask(size):
    k = 4
    x0, y0, x1, y1 = BADGE_BOX
    m = Image.new("L", (size[0] * k, size[1] * k), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        (x0 * k, y0 * k, x1 * k, y1 * k), radius=BADGE_RADIUS * k, fill=255
    )
    return m.resize(size, Image.Resampling.LANCZOS)


def _put_text(img, x, top, text, size, maxw, primary, fill):
    # draw_text handles Unicode/font fallback and shrinks long names cleanly.
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_text(
        layer,
        (x, top),
        text,
        size,
        fill=fill,
        max_width=maxw,
        min_size=18,
        primary=primary,
    )
    img.alpha_composite(layer)


def build_welcome_card(avatar_path, name, user_value, total, uid):
    card = Image.open(CARD_PATH).convert("RGBA")
    original = card.copy()

    # Replace only the avatar inside the circular photo area.
    d = AV_RADIUS * 2
    cx, cy = AV_CENTER
    if avatar_path and os.path.exists(str(avatar_path)):
        avatar = _circle(Image.open(avatar_path), d)
    else:
        avatar = Image.new("RGBA", (d, d), (16, 31, 65, 255))
        ad = ImageDraw.Draw(avatar)
        ad.ellipse((d//2-55, d//2-105, d//2+55, d//2+5), fill=(225,235,250,255))
        ad.rounded_rectangle((d//2-115, d//2-8, d//2+115, d//2+150), radius=55, fill=(76,122,195,255))
        avatar = _circle(avatar, d)
    card.alpha_composite(avatar, (cx - AV_RADIUS, cy - AV_RADIUS))

    # Put the template's JOINED badge/ring foreground back over the avatar.
    card.paste(original, (0, 0), _badge_mask(card.size))

    # A subtle glass tint hides the sample values while preserving the original design.
    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for box in ((910, 444, 1460, 515), (910, 515, 1460, 590), (995, 590, 1215, 665)):
        od.rounded_rectangle(box, radius=18, fill=(7, 23, 58, 72))
    card.alpha_composite(overlay)

    # Dynamic text is rendered with the multi-font engine copied from the working bot.
    _put_text(card, NAME_X, NAME_TOP, name, NAME_SIZE, NAME_MAXW, "Poppins-Bold.ttf", TEXT_COLOR)
    _put_text(card, USER_X, USER_TOP, user_value, USER_SIZE, USER_MAXW, "Poppins-Medium.ttf", TEXT_COLOR)
    _put_text(card, TOTAL_X, TOTAL_TOP, str(total), TOTAL_SIZE, TOTAL_MAXW, "Poppins-Medium.ttf", WHITE)

    out = Path(tempfile.gettempdir()) / f"junox_welcome_{uid}.png"
    card.convert("RGB").save(out, "PNG", optimize=True)
    return str(out)


async def _make_welcome_image(member, members_count):
    avatar_path = None
    try:
        photo = getattr(member, "photo", None)
        if photo and photo.big_file_id:
            avatar_path = await app.download_media(photo.big_file_id)
    except Exception as e:
        print(f"[WELCOME] PFP download failed for {member.id}: {e}")

    try:
        name = _clean_name(member)
        # Requirement: username if available; otherwise Telegram ID in that same field.
        user_value = f"@{member.username}" if getattr(member, "username", None) else str(member.id)
        return await asyncio.to_thread(
            build_welcome_card, avatar_path, name, user_value, members_count, member.id
        )
    finally:
        if avatar_path:
            try:
                Path(str(avatar_path)).unlink(missing_ok=True)
            except Exception:
                pass


async def _welcome_enabled(chat_id):
    try:
        setting = await db.cache.find_one({"_id": f"welcome_{chat_id}"})
        return setting.get("enabled", config.WELCOME_ENABLED) if setting else config.WELCOME_ENABLED
    except Exception as e:
        print(f"[WELCOME] DB setting read failed: {e}; default={config.WELCOME_ENABLED}")
        return config.WELCOME_ENABLED


# ==========================================================
# NEW MEMBER WELCOME
# ==========================================================
@app.on_message(filters.new_chat_members & filters.group)
async def welcome_new_members(_, message: types.Message):
    if not await _welcome_enabled(message.chat.id):
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
            name = _clean_name(member)
            username = f"@{member.username}" if member.username else str(member.id)

            caption = (
                "<b>╭━━━〔 ✨ NEW MEMBER 〕━━━╮</b>\n\n"
                "👋 <b>Welcome to Our Group!</b>\n\n"
                f"👤 <b>Name:</b> {escape(name)}\n"
                f"🆔 <b>ID:</b> <code>{member.id}</code>\n"
                f"🔗 <b>Username:</b> {escape(username)}\n"
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


# ==========================================================
# /WELCOME ON | OFF
# ==========================================================
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
            is_admin = bool(member.privileges and (
                member.privileges.can_change_info or member.privileges.can_delete_messages
            ))
        except Exception:
            pass

    if not (is_owner or is_admin):
        return await message.reply_text("❌ Only the group admins can change the welcome setting.")

    if len(message.command) < 2 or message.command[1].lower() not in {"on", "off"}:
        enabled = await _welcome_enabled(message.chat.id)
        return await message.reply_text(
            f"<b>Welcome System: {'ON 🟢' if enabled else 'OFF 🔴'}</b>\n\n"
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
        return await message.reply_text(f"❌ Could not save the setting to MongoDB.\n<code>{escape(str(e))}</code>")

    await message.reply_text(
        "✅ <b>Welcome system is now ON.</b>\nNew members will receive the Juno X welcome message."
        if enabled else
        "🔴 <b>Welcome system is now OFF.</b>\nNew members will not receive the welcome message."
    )


# ==========================================================
# BOT ADDED IN GROUP
# ==========================================================
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
