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
from pathlib import Path

from ArtistMusic import logger


def ensure_dirs():
    """
    Create necessary directories if they don't exist.

    Creates:
    - cache/: For temporary cache files
    - downloads/: For downloaded media files
    """
    # List of required directories
    for dir in ["cache", "downloads"]:
        # Create directory (and parents if needed)
        Path(dir).mkdir(parents=True, exist_ok=True)
    logger.info("📁 Cache directories updated.")
