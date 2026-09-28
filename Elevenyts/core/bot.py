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

    async def _rich_after_send(self, message, text, markup):
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

    async def send_message(self, chat_id, text=None, *args, reply_markup=None, **kwargs):
        message = await super().send_message(chat_id, text, *args, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, text, reply_markup)

    async def send_photo(self, chat_id, photo, *args, caption=None, reply_markup=None, **kwargs):
        message = await super().send_photo(chat_id, photo, *args, caption=caption, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def send_video(self, chat_id, video, *args, caption=None, reply_markup=None, **kwargs):
        message = await super().send_video(chat_id, video, *args, caption=caption, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def send_audio(self, chat_id, audio, *args, caption=None, reply_markup=None, **kwargs):
        message = await super().send_audio(chat_id, audio, *args, caption=caption, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def send_animation(self, chat_id, animation, *args, caption=None, reply_markup=None, **kwargs):
        message = await super().send_animation(chat_id, animation, *args, caption=caption, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def send_document(self, chat_id, document, *args, caption=None, reply_markup=None, **kwargs):
        message = await super().send_document(chat_id, document, *args, caption=caption, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def send_voice(self, chat_id, voice, *args, caption=None, reply_markup=None, **kwargs):
        message = await super().send_voice(chat_id, voice, *args, caption=caption, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

    async def edit_message_text(self, chat_id, message_id, text, *args, reply_markup=None, **kwargs):
        message = await super().edit_message_text(chat_id, message_id, text, *args, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, text, reply_markup)

    async def edit_message_caption(self, chat_id, message_id, caption=None, *args, reply_markup=None, **kwargs):
        message = await super().edit_message_caption(chat_id, message_id, caption=caption, *args, reply_markup=reply_markup, **kwargs)
        return await self._rich_after_send(message, caption, reply_markup)

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
