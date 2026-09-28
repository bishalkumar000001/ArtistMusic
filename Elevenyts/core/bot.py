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
    """Pyrogram client that sends supported inline-keyboard messages as Rich Messages."""

    def __init__(self):
        super().__init__(
            name="Elevenyts",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            parse_mode=pyrogram.enums.ParseMode.HTML,
            max_concurrent_transmissions=7,
            link_preview_options=pyrogram.types.LinkPreviewOptions(is_disabled=True),
        )
        self.owner: int = config.OWNER_ID
        self.logger: int = config.LOGGER_ID
        self.bl_users: pyrogram.filters.Filter = pyrogram.filters.user()
        self.sudoers: set = {self.owner}
        self.sudo_filter: pyrogram.filters.Filter = pyrogram.filters.user(self.owner)
        self.id: Optional[int] = None
        self.name: Optional[str] = None
        self.username: Optional[str] = None
        self.mention: Optional[str] = None

    async def _fetch_rich_message(self, chat_id, result):
        msg = (result or {}).get("result") or {}
        message_id = msg.get("message_id")
        if not message_id:
            raise RuntimeError("sendRichMessage returned no message_id")
        try:
            return await self.get_messages(int(chat_id), int(message_id))
        except Exception:
            # Do not send a duplicate normal message if fetch-by-id briefly fails.
            # Most Pyrogram versions accept a message_id as the second argument.
            return message_id

    async def _send_rich_text_if_needed(self, chat_id, text, markup, args, kwargs):
        if not rich_buttons.is_inline_markup(markup) or args:
            return None
        sender = getattr(rich_buttons, "send_rich_text", None) or getattr(rich_buttons, "send_rich_for_text")
        result = await sender(chat_id, text or "", markup, **kwargs)
        if result is None:
            return None
        return await self._fetch_rich_message(chat_id, result)

    async def _send_rich_media_if_needed(self, chat_id, media, text, markup, kind, args, kwargs):
        if not rich_buttons.is_inline_markup(markup) or args:
            return None
        sender = getattr(rich_buttons, "send_rich_media", None) or getattr(rich_buttons, "send_rich_for_media")
        result = await sender(chat_id, text or "", markup, kind, media, **kwargs)
        if result is None:
            return None
        return await self._fetch_rich_message(chat_id, result)

    async def _rich_after_send(self, message, text, markup):
        # Kept for compatibility with unsupported media/input sources.
        if rich_buttons.is_inline_markup(markup):
            try:
                converted = await rich_buttons.convert_existing(
                    message, text or getattr(message, "caption", "") or "", markup
                )
                if not converted:
                    logger.warning("Rich button conversion did not complete for message %s", getattr(message, "id", "?"))
            except Exception as ex:
                logger.warning("Rich button conversion failed: %s", ex)
        return message

    @staticmethod
    def _bind_positional(args, kwargs, names):
        """Normalize Pyrogram's positional reply_* arguments to keywords.

        Message.reply_photo/reply/send_message pass optional arguments positionally.
        The Rich Message path needs the same values as keywords so it can send the
        Rich Message directly instead of first sending a normal keyboard message.
        """
        values = dict(kwargs)
        for name, value in zip(names, args):
            if name not in values:
                values[name] = value
        return values

    async def send_message(self, chat_id, text=None, *args, reply_markup=None, **kwargs):
        names = (
            "parse_mode", "entities", "disable_web_page_preview", "disable_notification",
            "reply_to_message_id", "schedule_date", "protect_content", "reply_markup",
            "message_thread_id", "reply_parameters", "business_connection_id",
            "message_effect_id", "allow_paid_broadcast", "direct_messages_topic_id",
            "suggested_post_parameters",
        )
        kwargs = self._bind_positional(args, kwargs, names)
        reply_markup = kwargs.pop("reply_markup", reply_markup)
        rich = await self._send_rich_text_if_needed(chat_id, text, reply_markup, (), kwargs)
        if rich is not None:
            return rich
        message = await super().send_message(chat_id, text, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, text, reply_markup)

    async def _send_media_wrapper(self, method, chat_id, media, args, caption, reply_markup, kwargs, kind):
        names = (
            "caption", "parse_mode", "caption_entities", "has_spoiler", "disable_notification",
            "reply_to_message_id", "schedule_date", "protect_content", "reply_markup",
            "message_thread_id", "business_connection_id", "message_effect_id",
            "allow_paid_broadcast", "reply_parameters", "direct_messages_topic_id",
        )
        kwargs = self._bind_positional(args, kwargs, names)
        caption = kwargs.pop("caption", caption)
        reply_markup = kwargs.pop("reply_markup", reply_markup)
        rich = await self._send_rich_media_if_needed(chat_id, media, caption, reply_markup, kind, (), kwargs)
        if rich is not None:
            return rich
        sender = getattr(super(Bot, self), method)
        message = await sender(chat_id, media, caption=caption, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def send_photo(self, chat_id, photo, *args, caption=None, reply_markup=None, **kwargs):
        return await self._send_media_wrapper("send_photo", chat_id, photo, args, caption, reply_markup, kwargs, "photo")

    async def send_video(self, chat_id, video, *args, caption=None, reply_markup=None, **kwargs):
        return await self._send_media_wrapper("send_video", chat_id, video, args, caption, reply_markup, kwargs, "video")

    async def send_audio(self, chat_id, audio, *args, caption=None, reply_markup=None, **kwargs):
        return await self._send_media_wrapper("send_audio", chat_id, audio, args, caption, reply_markup, kwargs, "audio")

    async def send_animation(self, chat_id, animation, *args, caption=None, reply_markup=None, **kwargs):
        return await self._send_media_wrapper("send_animation", chat_id, animation, args, caption, reply_markup, kwargs, "animation")

    async def send_document(self, chat_id, document, *args, caption=None, reply_markup=None, **kwargs):
        return await self._send_media_wrapper("send_document", chat_id, document, args, caption, reply_markup, kwargs, "document")

    async def send_voice(self, chat_id, voice, *args, caption=None, reply_markup=None, **kwargs):
        return await self._send_media_wrapper("send_voice", chat_id, voice, args, caption, reply_markup, kwargs, "voice")

    async def edit_message_text(self, chat_id, message_id, text, *args, reply_markup=None, **kwargs):
        message = await super().edit_message_text(chat_id, message_id, text, *args, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, text, reply_markup)

    async def edit_message_caption(self, chat_id, message_id, caption=None, *args, reply_markup=None, **kwargs):
        message = await super().edit_message_caption(chat_id, message_id, caption=caption, *args, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def boot(self) -> None:
        await super().start()
        self.id = self.me.id
        self.name = self.me.first_name
        self.username = self.me.username
        self.mention = self.me.mention
        try:
            await self.send_message(self.logger, "🤖 ʙᴏᴛ ꜱᴛᴀʀᴛᴇᴅ")
            member = await self.get_chat_member(self.logger, self.id)
        except Exception as ex:
            raise SystemExit(
                f"❌ ʙᴏᴛ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴀᴄᴄᴇꜱꜱ ʟᴏɢɢᴇʀ ɢʀᴏᴜᴘ: {self.logger}\n"
                f"ʀᴇᴀꜱᴏɴ: {ex}\n"
                f"ᴘʟᴇᴀꜱᴇ ᴇɴꜱᴜʀᴇ ᴛʜᴇ ʙᴏᴛ ɪꜱ ᴀᴅᴅᴇᴅ ᴛᴏ ᴛʜᴇ ʟᴏɢɢᴇʀ ɢʀᴏᴜᴘ."
            )
        if member.status != pyrogram.enums.ChatMemberStatus.ADMINISTRATOR:
            raise SystemExit(
                f"❌ ʙᴏᴛ ɪꜱ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴɪꜱᴛʀᴀᴛᴏʀ ɪɴ ʟᴏɢɢᴇʀ ɢʀᴏᴜᴘ: {self.logger}\n"
                f"ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴍᴏᴛᴇ ᴛʜᴇ ʙᴏᴛ ᴛᴏ ᴀᴅᴍɪɴɪꜱᴛʀᴀᴛᴏʀ ᴡɪᴛʜ ɴᴇᴄᴇꜱꜱᴀʀʏ ᴘᴇʀᴍɪꜱꜱɪᴏɴꜱ."
            )
        logger.info(f"🤖 Bot started successfully as @{self.username}")

    async def exit(self) -> None:
        await super().stop()
        logger.info("🤖 Bot client stopped.")
