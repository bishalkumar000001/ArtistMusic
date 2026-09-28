"""Central label registry for all known user-facing Telegram buttons.

Edit BUTTON_LABELS values to rename buttons without changing callback data/actions.
"""
import re

BUTTON_LABELS = {
    # Start, navigation, help and links
    "help": "ㅤㅤHelpㅤㅤ",
    "source": "ꜱᴏᴜʀᴄᴇ",
    "languages": "ㅤʟᴀɴɢꜱㅤ",
    "back": "ㅤㅤʙᴀᴄᴋㅤㅤ",
    "admins": "ㅤᴀᴅᴍɪɴꜱㅤ",
    "auth": "ㅤㅤᴀᴜᴛʜㅤㅤ",
    "broadcast": "ʙʀᴏᴀᴅᴄᴀꜱᴛ",
    "blacklist_chats": "ㅤʙʟ-ᴄʜᴀᴛㅤ",
    "blacklist_users": "ㅤʙʟ-ᴜꜱᴇʀㅤ",
    "gban": "ㅤɢ-ʙᴀɴㅤ",
    "loop_help": "ㅤㅤʟᴏᴏᴘㅤㅤ",
    "play_help": "ㅤㅤᴘʟᴀʏㅤㅤ",
    "queue_help": "ㅤǫᴜᴇᴜᴇㅤ",
    "seek_help": "ㅤㅤꜱᴇᴇᴋㅤㅤ",
    "shuffle_help": "ㅤꜱʜᴜꜰꜰʟᴇㅤ",
    "ping_help": "ㅤㅤᴘɪɴɢㅤㅤ",
    "stats_help": "ㅤㅤꜱᴛᴀᴛꜱㅤㅤ",
    "sudo_help": "ㅤㅤꜱᴜᴅᴏㅤㅤ",
    "maintenance_help": "ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ",
    "help_back": "ㅤㅤʙᴀᴄᴋㅤㅤ",
    "help_languages": "ㅤㅤ🌐 ʟᴀɴɢꜱㅤㅤ",
    "channel": "ㅤㅤChannelㅤㅤ",
    "support": "ㅤㅤSupportㅤㅤ",
    "add_me": " Add Me to Your Group",
    "add_me_short": "ㅤㅤㅤㅤㅤㅤAdd Meㅤㅤㅤㅤㅤㅤ",
    "support_channel": "ㅤㅤsupport channelㅤㅤ",
    "close_lower": "close",
    "cancel_download": "Cancel",
    "copy_link": "ᴄᴏᴘʏ ʟɪɴᴋ",
    "open_youtube": "ᴏᴘᴇɴ ɪɴ ʏᴏᴜᴛᴜʙᴇ",
    # Main/player keyboard icons (kept separate from text labels)
    "pause_icon": "⏸",
    "resume_icon": "▶",
    "replay_icon": "↻",
    "skip_icon": "⏭",
    "stop_icon": "⏹",
    "auto_icon": "AUTO",
    "queue_resume_icon": "▷",
    "queue_pause_icon": "∣ ∣",
    "queue_skip_icon": ">>",
    "queue_stop_icon": "▣",
    "queue_close_icon": "🗑",
    # Music player and queue Rich Message controls
    "pause": "Pause",
    "resume": "Resume",
    "replay": "Replay",
    "shuffle": "Shuffle",
    "skip": "Skip",
    "stop": "Stop",
    "close": "Close",
    "loop": "Loop",
    "autoplay_on": "ㅤㅤㅤㅤㅤㅤㅤAutoplay: ONㅤㅤㅤㅤㅤㅤㅤ",
    "autoplay_off": "ㅤㅤㅤㅤㅤㅤㅤAutoplay: OFFㅤㅤㅤㅤㅤㅤㅤ",
    "play_now": "ㅤㅤㅤㅤPʟᴀʏ Nᴏᴡㅤㅤㅤㅤ",
    "queue_stop": "ㅤㅤSᴛᴏᴘㅤㅤ",
    "queue_close": "ㅤㅤCʟᴏsᴇㅤㅤ",
    # Player/settings mode labels
    "auto": "AUTO",
    "play_mode": "Play Mode",
    "force_mode": "Force Mode",
    "everyone": "Everyone",
    "admin_only": "Admin Only",
    "play_mode_arrow": "Play Mode ➜",
    "force_mode_arrow": "Force Mode ➜",
    # Settings/selection buttons
    "loop_off": "➡️ Loop: Off",
    "loop_queue": "🔁 Loop: Queue",
    "loop_single": "🔂 Loop: Single Track",
    "language_back": "ʙᴀᴄᴋ",
    # Additional existing menus and utility keyboards
    "start": "Start",
    "settings": "Settings",
    "play_settings": "Play Settings",
    "language": "Language",
    "english": "🇬🇧 English",
    "hindi": "🇮🇳 Hindi",
    "cancel_lower": "Cancel",
    "confirm_action": "Confirm",
    "owner": "Owner",
    "reload": "Reload",
    "check": "Check",
    "status": "Status",
    "update": "Update",
    "help_main": "Help",
    "help_admins": "Admins",
    "help_auth": "Auth",
    "help_broadcast": "Broadcast",
    "help_blacklist_chats": "Blacklist Chats",
    "help_blacklist_users": "Blacklist Users",
    "help_gban": "Global Ban",
    "help_loop": "Loop Help",
    "help_play": "Play Help",
    "help_queue": "Queue Help",
    "help_seek": "Seek Help",
    "help_shuffle": "Shuffle Help",
    "help_ping": "Ping Help",
    "help_stats": "Stats Help",
    "help_sudo": "Sudo Help",
    "help_maintenance": "Maintenance Help",
    "play_mode_label": "Play Mode",
    "force_mode_label": "Force Mode",
    "loop_single_label": "🔂 Loop: Single Track",
    "loop_queue_label": "🔁 Loop: Queue",
    "loop_off_label": "➡️ Loop: Off",
    "next_track": "Next Track",
    "previous_track": "Previous Track",
    "add_me_group": "➕ Add Me to Your Group",
    "source_code": "Source Code",
    "open_link": "Open Link",
    "copy_text": "Copy Text",
    # Generic optional labels used by plugin keyboards
    "confirm": "Confirm",
    "cancel": "Cancel",
    "yes": "Yes",
    "no": "No",
    "next": "Next",
    "previous": "Previous",
    "refresh": "Refresh",
    "download": "Download",
    "play": "Play",
    "delete": "Delete",
    "remove": "Remove",
}

# Match original displayed strings to editable keys. Matching is case-insensitive
# and whitespace-insensitive; callback_data and URLs are never modified.
_ALIASES = {
    "help": "help", "ʜᴇʟᴘ": "help",
    "source": "source", "ꜱᴏᴜʀᴄᴇ": "source",
    "langs": "languages", "languages": "languages", "ʟᴀɴɢꜱ": "languages", "🌐 ʟᴀɴɢꜱ": "languages",
    "back": "back", "ʙᴀᴄᴋ": "back",
    "admins": "admins", "ᴀᴅᴍɪɴꜱ": "admins",
    "auth": "auth", "ᴀᴜᴛʜ": "auth",
    "broadcast": "broadcast", "ʙʀᴏᴀᴅᴄᴀꜱᴛ": "broadcast",
    "bl-chat": "blacklist_chats", "ʙʟ-ᴄʜᴀᴛ": "blacklist_chats",
    "bl-user": "blacklist_users", "ʙʟ-ᴜꜱᴇʀ": "blacklist_users",
    "g-ban": "gban", "ɢ-ʙᴀɴ": "gban",
    "loop": "loop", "ʟᴏᴏᴘ": "loop",
    "play": "play_help", "ᴘʟᴀʏ": "play_help",
    "queue": "queue_help", "ǫᴜᴇᴜᴇ": "queue_help",
    "seek": "seek_help", "ꜱᴇᴇᴋ": "seek_help",
    "shuffle": "shuffle", "ꜱʜᴜꜰꜰʟᴇ": "shuffle_help",
    "ping": "ping_help", "ᴘɪɴɢ": "ping_help",
    "stats": "stats_help", "ꜱᴛᴀᴛꜱ": "stats_help",
    "sudo": "sudo_help", "ꜱᴜᴅᴏ": "sudo_help",
    "maintenance": "maintenance_help", "ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ": "maintenance_help",
    "📢 channel": "channel", "channel": "channel", "ᴄʜᴀɴɴᴇʟ": "channel",
    "🆘 support": "support", "support": "support", "ꜱᴜᴘᴘᴏʀᴛ": "support",
    "➕ add me to your group": "add_me", "ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ": "add_me", "add me": "add_me_short",
    "support channel": "support_channel", "close": "close", "cancel": "cancel_download", "auto": "auto",
    "ᴄᴏᴘʏ ʟɪɴᴋ": "copy_link", "copy link": "copy_link",
    "ᴏᴘᴇɴ ɪɴ ʏᴏᴜᴛᴜʙᴇ": "open_youtube", "open in youtube": "open_youtube",
    "pause": "pause", "resume": "resume", "replay": "replay", "skip": "skip",
    "stop": "stop", "close player": "close", "shuffle": "shuffle", "loop": "loop",
    "⏸": "pause_icon", "▶": "resume_icon", "↻": "replay_icon", "⏭": "skip_icon", "⏹": "stop_icon",
    "▷": "queue_resume_icon", "∣ ∣": "queue_pause_icon", ">>": "queue_skip_icon", "▣": "queue_stop_icon", "🗑": "queue_close_icon",
    "play mode ➜": "play_mode_arrow", "force mode ➜": "force_mode_arrow",
    "➡️ loop: off": "loop_off", "🔁 loop: queue": "loop_queue", "🔂 loop: single track": "loop_single",
    "confirm": "confirm", "yes": "yes", "no": "no", "next": "next", "previous": "previous",
    "refresh": "refresh", "download": "download", "delete": "delete", "remove": "remove",
    "start": "start", "settings": "settings", "play settings": "play_settings",
    "language": "language", "english": "english", "🇬🇧 english": "english",
    "hindi": "hindi", "🇮🇳 hindi": "hindi", "reload": "reload", "check": "check",
    "status": "status", "update": "update", "owner": "owner", "open link": "open_link",
    "copy text": "copy_text", "source code": "source_code", "next track": "next_track",
    "previous track": "previous_track", "play mode": "play_mode_label", "force mode": "force_mode_label",
    "loop: off": "loop_off_label", "loop: queue": "loop_queue_label", "loop: single track": "loop_single_label",
}

def _normalize(value):
    return re.sub(r"\s+", " ", str(value if value is not None else "Button")).strip().casefold()

def get_label(key, default=None):
    return BUTTON_LABELS.get(key, default if default is not None else key)

def display_label(value):
    """Return the central label for known existing button text."""
    original = str(value if value is not None else "Button")
    key = _ALIASES.get(_normalize(original))
    if key:
        return get_label(key, original)
    # Direct override: add the original visible button text as a key in
    # BUTTON_LABELS to rename any button, including translated/dynamic labels.
    normalized = _normalize(original)
    if normalized in BUTTON_LABELS:
        return get_label(normalized, original)
    # Also allow a button to be configured by using its symbolic key as text.
    for candidate in BUTTON_LABELS:
        if _normalize(candidate) == normalized:
            return get_label(candidate, original)
    return original
