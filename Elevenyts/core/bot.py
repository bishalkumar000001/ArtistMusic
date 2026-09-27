# ==========================================================
# Copyright (c) 2026 VelocityBots
# All Rights Reserved.
#
# Project      : VelocityBots ꭙ Music Telegram Bot
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
import pyrogram
from typing import Optional

from Elevenyts import config, logger
from Elevenyts.core import rich_buttons


class Bot(pyrogram.Client):
    """
    Main bot client class extending Pyrogram's Client.

    This class initializes the Telegram bot with proper configuration
    and provides methods for starting and stopping the bot.

    Attributes:
        owner (int): Owner's user ID
        logger (int): Logger group/channel ID
        bl_users (Filter): Filter for blacklisted users
        sudoers (set): Set of sudo user IDs
        sudo_filter (Filter): Filter for sudo users
        id (int): Bot's user ID (set after boot)
        name (str): Bot's first name (set after boot)
        username (str): Bot's username (set after boot)
        mention (str): Bot's mention tag (set after boot)
    """

    def __init__(self):
        """Initialize the bot client with configuration settings."""
        super().__init__(
            name="Elevenyts",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            parse_mode=pyrogram.enums.ParseMode.HTML,
            max_concurrent_transmissions=7,
            link_preview_options=pyrogram.types.LinkPreviewOptions(
                is_disabled=True),
        )

        self.owner: int = config.OWNER_ID
        self.logger: int = config.LOGGER_ID
        self.bl_users: pyrogram.filters.Filter = pyrogram.filters.user()
        self.sudoers: set = {self.owner}  # Set of sudo user IDs
        self.sudo_filter: pyrogram.filters.Filter = pyrogram.filters.user(
            self.owner)

        # These will be set after boot()
        self.id: Optional[int] = None
        self.name: Optional[str] = None
        self.username: Optional[str] = None
        self.mention: Optional[str] = None

    async def _rich_fetch(self, chat_id, result):
        """Return the normal Pyrogram Message object for a Rich Message."""
        mid = int((result.get("result") or {}).get("message_id") or 0)
        if not mid:
            raise RuntimeError("Rich Message response did not contain message_id")
        try:
            msg = await self.get_messages(int(chat_id), mid)
            if msg:
                return msg
        except Exception:
            pass
        return None

    async def _rich_options(self, kwargs):
        options = {}
        if kwargs.get("reply_to_message_id"):
            options["reply_to_message_id"] = kwargs["reply_to_message_id"]
        for key in (
            "message_thread_id", "direct_messages_topic_id", "disable_notification",
            "protect_content", "allow_paid_broadcast", "message_effect_id",
            "suggested_post_parameters", "business_connection_id",
        ):
            if key in kwargs and kwargs[key] is not None:
                options[key] = kwargs[key]
        return options

    async def _send_rich_or_fallback(self, *, method, chat_id, text=None,
                                     media=None, markup=None, media_kind=None,
                                     args=(), kwargs=None):
        kwargs = kwargs or {}
        if not rich_buttons.is_inline_markup(markup):
            call_kwargs = dict(kwargs)
            if media_kind is not None:
                call_kwargs["caption"] = text
                call_kwargs["reply_markup"] = markup
                return await getattr(super(), method)(chat_id, media, *(args or ()), **call_kwargs)
            call_kwargs["reply_markup"] = markup
            return await getattr(super(), method)(chat_id, text, *(args or ()), **call_kwargs)

        # Rich Messages do not use Pyrogram's parse_mode/reply_markup arguments.
        # The bot already runs in HTML mode, so the existing text is retained as
        # HTML. If an unsupported option is present, use the old sender safely.
        unsupported = set(kwargs) - {
            "reply_to_message_id", "message_thread_id", "direct_messages_topic_id",
            "disable_notification", "protect_content", "allow_paid_broadcast",
            "message_effect_id", "suggested_post_parameters", "business_connection_id",
            "parse_mode", "quote", "reply_to_message", "caption_entities",
            "show_caption_above_media", "has_spoiler", "thumb", "duration", "width",
            "height", "performer", "title", "file_name", "force_document",
        }
        if unsupported:
            call_kwargs = dict(kwargs)
            call_kwargs["reply_markup"] = markup
            if media_kind is not None:
                call_kwargs["caption"] = text
                return await getattr(super(), method)(chat_id, media, *(args or ()), **call_kwargs)
            return await getattr(super(), method)(chat_id, text, *(args or ()), **call_kwargs)

        try:
            opts = await self._rich_options(kwargs)
            if media_kind is None:
                result = await rich_buttons.send_rich_for_message(
                    chat_id, text or "", markup, **opts
                )
            else:
                result = await rich_buttons.send_rich_for_media(
                    chat_id, text or "", markup, media_kind, media, **opts
                )
            fetched = await self._rich_fetch(chat_id, result)
            if fetched is not None:
                return fetched
            # The send succeeded even if Pyrogram could not fetch the Message.
            return result
        except Exception as ex:
            logger.warning(f"Rich button conversion failed: {ex}")
            # Never break an existing bot action just because Rich Messages are
            # unavailable in a particular chat/client version.
            call_kwargs = dict(kwargs)
            call_kwargs["reply_markup"] = markup
            if media_kind is not None:
                call_kwargs["caption"] = text
                return await getattr(super(), method)(chat_id, media, *(args or ()), **call_kwargs)
            return await getattr(super(), method)(chat_id, text, *(args or ()), **call_kwargs)

    async def _rich_after_send(self, message, text, markup):
        """Compatibility path for code that already sent a normal message."""
        if not rich_buttons.is_inline_markup(markup):
            return message
        try:
            return await rich_buttons.replace_with_rich(
                message, text or getattr(message, "caption", "") or "", markup
            )
        except Exception as ex:
            logger.warning(f"Rich button conversion failed: {ex}")
            return message

    async def send_message(self, chat_id, text=None, *args, reply_markup=None, **kwargs):
        if rich_buttons.is_inline_markup(reply_markup):
            return await self._send_rich_or_fallback(
                method="send_message", chat_id=chat_id, text=text,
                markup=reply_markup, args=args, kwargs=kwargs
            )
        return await super().send_message(chat_id, text, *args, reply_markup=reply_markup, **kwargs)

    async def send_photo(self, chat_id, photo, *args, caption=None, reply_markup=None, **kwargs):
        if rich_buttons.is_inline_markup(reply_markup):
            return await self._send_rich_or_fallback(
                method="send_photo", chat_id=chat_id, text=caption,
                media=photo, media_kind="photo", markup=reply_markup,
                args=args, kwargs=kwargs
            )
        return await super().send_photo(chat_id, photo, *args, caption=caption, reply_markup=reply_markup, **kwargs)

    async def send_video(self, chat_id, video, *args, caption=None, reply_markup=None, **kwargs):
        if rich_buttons.is_inline_markup(reply_markup):
            return await self._send_rich_or_fallback(
                method="send_video", chat_id=chat_id, text=caption,
                media=video, media_kind="video", markup=reply_markup,
                args=args, kwargs=kwargs
            )
        return await super().send_video(chat_id, video, *args, caption=caption, reply_markup=reply_markup, **kwargs)

    async def send_animation(self, chat_id, animation, *args, caption=None, reply_markup=None, **kwargs):
        if rich_buttons.is_inline_markup(reply_markup):
            return await self._send_rich_or_fallback(
                method="send_animation", chat_id=chat_id, text=caption,
                media=animation, media_kind="animation", markup=reply_markup,
                args=args, kwargs=kwargs
            )
        return await super().send_animation(chat_id, animation, *args, caption=caption, reply_markup=reply_markup, **kwargs)

    async def send_audio(self, chat_id, audio, *args, caption=None, reply_markup=None, **kwargs):
        if rich_buttons.is_inline_markup(reply_markup):
            return await self._send_rich_or_fallback(
                method="send_audio", chat_id=chat_id, text=caption,
                media=audio, media_kind="audio", markup=reply_markup,
                args=args, kwargs=kwargs
            )
        return await super().send_audio(chat_id, audio, *args, caption=caption, reply_markup=reply_markup, **kwargs)

    async def send_document(self, chat_id, document, *args, caption=None, reply_markup=None, **kwargs):
        if rich_buttons.is_inline_markup(reply_markup):
            return await self._send_rich_or_fallback(
                method="send_document", chat_id=chat_id, text=caption,
                media=document, media_kind="document", markup=reply_markup,
                args=args, kwargs=kwargs
            )
        return await super().send_document(chat_id, document, *args, caption=caption, reply_markup=reply_markup, **kwargs)

    async def send_voice(self, chat_id, voice, *args, caption=None, reply_markup=None, **kwargs):
        if rich_buttons.is_inline_markup(reply_markup):
            return await self._send_rich_or_fallback(
                method="send_voice", chat_id=chat_id, text=caption,
                media=voice, media_kind="voice", markup=reply_markup,
                args=args, kwargs=kwargs
            )
        return await super().send_voice(chat_id, voice, *args, caption=caption, reply_markup=reply_markup, **kwargs)

    async def boot(self) -> None:
        """
        Start the bot and perform initial setup.

        This method:
        - Starts the Pyrogram client
        - Retrieves bot information
        - Verifies access to logger group
        - Checks bot admin status in logger group

        Raises:
            SystemExit: If bot cannot access logger group or is not an admin.
        """
        await super().start()

        # Set bot information
        self.id = self.me.id
        self.name = self.me.first_name
        self.username = self.me.username
        self.mention = self.me.mention

        # Verify logger group access
        try:
            await self.send_message(self.logger, "🤖 ʙᴏᴛ ꜱᴛᴀʀᴛᴇᴅ")
            member = await self.get_chat_member(self.logger, self.id)
        except Exception as ex:
            raise SystemExit(
                f"❌ ʙᴏᴛ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴀᴄᴄᴇꜱꜱ ʟᴏɢɢᴇʀ ɢʀᴏᴜᴘ: {self.logger}\n"
                f"ʀᴇᴀꜱᴏɴ: {ex}\n"
                f"ᴘʟᴇᴀꜱᴇ ᴇɴꜱᴜʀᴇ ᴛʜᴇ ʙᴏᴛ ɪꜱ ᴀᴅᴅᴇᴅ ᴛᴏ ᴛʜᴇ ʟᴏɢɢᴇʀ ɢʀᴏᴜᴘ."
            )

        # Verify admin status
        if member.status != pyrogram.enums.ChatMemberStatus.ADMINISTRATOR:
            raise SystemExit(
                f"❌ ʙᴏᴛ ɪꜱ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴɪꜱᴛʀᴀᴛᴏʀ ɪɴ ʟᴏɢɢᴇʀ ɢʀᴏᴜᴘ: {self.logger}\n"
                f"ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴍᴏᴛᴇ ᴛʜᴇ ʙᴏᴛ ᴛᴏ ᴀᴅᴍɪɴɪꜱᴛʀᴀᴛᴏʀ ᴡɪᴛʜ ɴᴇᴄᴇꜱꜱᴀʀʏ ᴘᴇʀᴍɪꜱꜱɪᴏɴꜱ."
            )

        logger.info(f"🤖 Bot started successfully as @{self.username}")

    async def exit(self) -> None:
        """
        Gracefully stop the bot client.

        This method stops the Pyrogram client and logs the shutdown.
        """
        await super().stop()
        logger.info("🤖 Bot client stopped.")

# ---------------------------------------------------------------------------
# Global edit hooks
# ---------------------------------------------------------------------------
# A large part of the bot uses Message.reply_* through the app client, but
# callback handlers also call query.edit_message_text/caption directly.  These
# hooks make those existing keyboards Rich Buttons too, without rewriting every
# plugin/callback file individually.

_ORIG_MESSAGE_EDIT_TEXT = pyrogram.types.Message.edit_text
_ORIG_MESSAGE_EDIT_CAPTION = pyrogram.types.Message.edit_caption
_ORIG_MESSAGE_EDIT_MEDIA = pyrogram.types.Message.edit_media
_ORIG_CALLBACK_EDIT_TEXT = pyrogram.types.CallbackQuery.edit_message_text
_ORIG_CALLBACK_EDIT_CAPTION = pyrogram.types.CallbackQuery.edit_message_caption


async def _rich_message_edit_text(self, text=None, *args, reply_markup=None, **kwargs):
    if rich_buttons.is_inline_markup(reply_markup):
        try:
            return await rich_buttons.replace_with_rich(self, text or "", reply_markup)
        except Exception as ex:
            logger.warning(f"Rich button edit failed: {ex}")
    return await _ORIG_MESSAGE_EDIT_TEXT(self, text, *args, reply_markup=reply_markup, **kwargs)


async def _rich_message_edit_caption(self, caption=None, *args, reply_markup=None, **kwargs):
    if rich_buttons.is_inline_markup(reply_markup):
        try:
            return await rich_buttons.replace_with_rich(self, caption or "", reply_markup)
        except Exception as ex:
            logger.warning(f"Rich button caption edit failed: {ex}")
    return await _ORIG_MESSAGE_EDIT_CAPTION(self, caption, *args, reply_markup=reply_markup, **kwargs)


async def _rich_message_edit_media(self, media, *args, reply_markup=None, **kwargs):
    result = await _ORIG_MESSAGE_EDIT_MEDIA(self, media, *args, reply_markup=reply_markup, **kwargs)
    if rich_buttons.is_inline_markup(reply_markup):
        try:
            refreshed = await self._client.get_messages(int(self.chat.id), int(self.id))
            if refreshed:
                return await rich_buttons.replace_with_rich(
                    refreshed,
                    refreshed.caption or refreshed.text or "",
                    reply_markup,
                )
        except Exception as ex:
            logger.warning(f"Rich button media edit failed: {ex}")
    return result


async def _rich_callback_edit_text(self, text=None, *args, reply_markup=None, **kwargs):
    message = getattr(self, "message", None)
    if message is not None and rich_buttons.is_inline_markup(reply_markup):
        try:
            return await rich_buttons.replace_with_rich(message, text or "", reply_markup)
        except Exception as ex:
            logger.warning(f"Rich callback text edit failed: {ex}")
    return await _ORIG_CALLBACK_EDIT_TEXT(self, text, *args, reply_markup=reply_markup, **kwargs)


async def _rich_callback_edit_caption(self, caption=None, *args, reply_markup=None, **kwargs):
    message = getattr(self, "message", None)
    if message is not None and rich_buttons.is_inline_markup(reply_markup):
        try:
            return await rich_buttons.replace_with_rich(message, caption or "", reply_markup)
        except Exception as ex:
            logger.warning(f"Rich callback caption edit failed: {ex}")
    return await _ORIG_CALLBACK_EDIT_CAPTION(self, caption, *args, reply_markup=reply_markup, **kwargs)


pyrogram.types.Message.edit_text = _rich_message_edit_text
pyrogram.types.Message.edit_caption = _rich_message_edit_caption
pyrogram.types.Message.edit_media = _rich_message_edit_media
pyrogram.types.CallbackQuery.edit_message_text = _rich_callback_edit_text
pyrogram.types.CallbackQuery.edit_message_caption = _rich_callback_edit_caption
