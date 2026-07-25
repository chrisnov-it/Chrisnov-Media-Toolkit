"""UI constants — combobox option lists and presets."""

APP_VERSION = "0.1.0-beta.5"

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
