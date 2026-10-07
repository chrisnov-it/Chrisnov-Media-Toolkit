"""UI constants — combobox option lists and presets."""

from pathlib import Path

APP_VERSION = "0.2.0-beta.5"

# Per-user config dir: download history + skip-duplicates archives live here.
CONFIG_DIR = Path.home() / ".config" / "chrisnov-media-toolkit"

RES_PRESETS = [
    ("Best (no limit)", None),
    ("1080p", 1080),
    ("720p", 720),
    ("480p", 480),
    ("360p", 360),
]

VIDEO_CONTAINERS = ["mp4", "mkv", "webm"]
AUDIO_CONTAINERS = ["mp3", "m4a", "opus"]
AUDIO_BITRATES = ["96", "128", "160", "192", "256", "320"]  # kbps

PLAYLIST_CONFIRM_THRESHOLD = 50
MAX_HISTORY_ENTRIES = 1000

# Clearing a queue/list of at least this many rows asks first (P3): Clear All
# history already confirmed, but wiping 20 queued URLs or files with one click
# had no guard at all. Below the threshold clearing stays instant — few rows
# are cheap to re-add.
CLEAR_CONFIRM_ROWS = 5

# Muted gray for secondary text that must read on both Light and Dark
# backgrounds: the About dialog's credit links and the palette fallbacks
# in icon.py/theme.py when the theme is mid-update. One literal, several
# callers — change it here.
NEUTRAL_GRAY = "#8a94a0"
