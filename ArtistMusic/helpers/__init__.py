# ==========================================================
# Copyright (c) 2026 VelocityBots
# All Rights Reserved.
#
# Project      : VelocityBots API Telegram Music Bot
# Powered By   : ⎯꯭̽𓆩꯭͈〬𝐉͢αη𝐡νί ✗ Μυδί𝛓꯭ ̽🤍͢
# Type         : API Based Telegram Music Bot
#
# Bot          : @JanhvixmusicRobot
# Channel      : https://t.me/VelocityBots
# GitHub       : https://github.com/bishalkumar000001/ArtistMusic
#
# Unauthorized copying, modification, or redistribution
# of this source code without permission is prohibited.
# ==========================================================
from ._admins import admin_check, can_manage_vc, is_admin, reload_admins, can_manage_vc_channel
from ._dataclass import Media, Track
from ._exec import format_exception, meval
from ._inline import Inline
from ._queue import Queue
from ._thumbnails import Thumbnail
from ._utilities import Utilities

buttons = Inline()
thumb = Thumbnail()
utils = Utilities()
