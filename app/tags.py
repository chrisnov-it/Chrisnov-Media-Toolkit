"""Embedded-tag fixes — keep the title tag in step with the cleaned
filename, split "Artist - Song" titles into their proper tags, and strip
YouTube promo junk from the description tag.

FFmpegMetadata writes the *raw* YouTube title (which is usually
"Artist - Song (Official Video)") and, for YouTube, a huge promo-laden
description into the file, while ``cleaner.rename_with_cleanup`` only
renames the file on disk — so a file with both Clean Title and Embed
Metadata enabled ends up with a filename and an embedded title that
disagree. This module repairs the embedded tags after the rename.

Everything here is best-effort and self-fenced: a missing/broken tag layer
(mutagen, mutagen-less formats, permissions) must never fail a batch.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Format-specific title keys written by ffmpeg/yt-dlp:
#   mp3 (ID3)  -> TIT2
#   mp4/m4a    -> ©nam (stored here as '\xa9nam')
#   ogg/matroska (vorbis comment) -> title / TITLE
_TITLE_KEYS = ("title", "TITLE", "Title", "TIT2", "\xa9nam")

# Artist keys, mirroring the title keys per format (TPE1/©ART/artist).
_ARTIST_KEYS = ("artist", "ARTIST", "Artist", "TPE1", "\xa9ART")

# Date/year keys per format. FFmpegMetadata writes the full upload date
# (e.g. "20261001") into them; some players truncate the m4a ©day value to a
# 16-bit int (20261001 & 0xFFFF == 10377), so these get normalized to the
# bare 4-digit year below.
_DATE_KEYS = ("\xa9day", "TDRC", "TYER", "date", "DATE", "Date", "year")

# The artist key to CREATE when the title carries "Artist - Song" but the
# file has no artist tag yet, keyed by the title key actually found.
_ARTIST_KEY_FOR_TITLE = {
    "TIT2": "TPE1",       # mp3/ID3
    "\xa9nam": "\xa9ART",  # mp4/m4a
    "TITLE": "ARTIST",    # matroska/vorbis, uppercase style
    "title": "artist",    # ogg/vorbis, lowercase style
}

# Description-ish keys written by FFmpegMetadata, per format:
#   mp3 -> TXXX:description / TXXX:synopsis / COMM
#   mp4 -> desc / ldes
#   ogg/matroska -> description / DESCRIPTION
_DESC_KEYS = (
    "TXXX:description", "TXXX:synopsis",
    "desc", "ldes",
    "description", "DESCRIPTION", "Description",
)

# Comment keys that yt-dlp fills with the source YouTube URL:
#   mp3 -> COMM:* (any lang/desc), TXXX:comment, TXXX:purl
#   mp4 -> ©cmt
#   ogg/matroska -> comment / COMMENT
# Only values that ARE a bare URL are removed — a real user comment survives.
_COMMENT_KEYS = (
    "TXXX:comment", "TXXX:purl", "\xa9cmt",
    "comment", "COMMENT", "Comment",
)

# ID3 COMM frame keys carry the language/description suffix
# (e.g. "COMM:ID3v1 Comment:eng"), so they match by prefix instead.
_COMMENT_KEY_PREFIX = "COMM"

# A paragraph starting with one of these (lowercase) is promo spam.
_PROMO_MARKERS = (
    "follow ", "subscribe", "watch ", "listen", "streaming", "merch",
    "tour ", "newsletter", "download ", "buy ", "support ", "patreon",
)

_MAX_DESC_CHARS = 1000


def split_artist_title(title: str) -> tuple[str, str] | None:
    """Split an ``Artist - Song`` title into (artist, song).

    Returns None when the title doesn't have the two-part shape (no
    separator, or an empty side). The separator is the classic " - " (plus
    en/em dashes) and only the FIRST occurrence splits, so songs whose own
    name contains a dash keep the rest intact:
        "Rick Astley - Never Gonna Give You Up" -> ("Rick Astley", "Never Gonna Give You Up")
        "A - B - C"                            -> ("A", "B - C")
    """
    if not isinstance(title, str):
        return None
    parts = re.split(r"\s+[-–—]\s+", title.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    artist, song = parts[0].strip(), parts[1].strip()
    if not artist or not song:
        return None
    return artist, song


def normalize_year(value: object) -> str | None:
    """Return a bare ``YYYY`` when *value* is an 8-digit date, else None.

    FFmpegMetadata writes the YouTube upload date as ``20261001``. Players
    that read the m4a ``©day`` atom as a 16-bit int overflow it
    (``20261001 & 0xFFFF == 10377``). Year precision is what every player
    displays anyway, so full dates are collapsed to their year.
    """
    text = _frame_text(value).strip()
    if re.fullmatch(r"\d{8}", text):
        return text[:4]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text[:4]
    return None


def _is_url(value: object) -> bool:
    """True when a tag value is just a URL (the source link yt-dlp writes)."""
    return bool(re.fullmatch(r"https?://\S+", _frame_text(value).strip()))


def plan_tag_repairs(
    path: str | Path,
    clean_tags: list[str] | None = None,
) -> list[tuple[object, object, str | None]]:
    """Compute the tag repairs for *path* without writing anything.

    Returns a list of ``(key, current_value, new_value_or_None)`` where
    ``new_value`` of None means "delete this key". Empty list = no changes
    needed (or the file can't be read at all). Never raises; shared by
    ``sync_embedded_tags()`` (the writer) and ``scripts/repair_tags.py``
    (the preview).
    """
    # Local import: mutagen is an optional-but-pinned dependency and this
    # module must stay importable in stripped environments (e.g. tests).
    from .cleaner import clean_title
    try:
        import mutagen
    except ImportError:  # pragma: no cover — mutagen is pinned in requirements
        return []

    try:
        audio = mutagen.File(path)
    except Exception:
        log.debug("plan_tag_repairs: cannot open %s", path, exc_info=True)
        return []
    if audio is None or audio.tags is None:
        return []

    tags = audio.tags
    plan: list[tuple[object, object, str | None]] = []

    # --- title: strip fluff tags, then split "Artist - Song" ---------------
    # The split runs even without Clean Title — it repairs yt-dlp's metadata,
    # not the filename.
    try:
        for key in _TITLE_KEYS:
            try:
                value = tags[key]
            except (KeyError, TypeError):
                continue
            old = _frame_text(value)
            new = clean_title(old, clean_tags) if clean_tags else old
            split = split_artist_title(new)
            if split:
                artist, new = split          # split returns (artist, song)
                plan.extend(_plan_artist(tags, key, artist))
            if new and new != old:
                plan.append((key, value, new))
            break  # first title key found is the one to use
    except Exception:
        log.debug("plan_tag_repairs: title failed for %s", path, exc_info=True)

    # --- date: collapse 20261001 -> 2026 -----------------------------------
    try:
        for key in _DATE_KEYS:
            try:
                value = tags[key]
            except (KeyError, TypeError):
                continue
            year = normalize_year(value)
            if year:
                plan.append((key, value, year))
            break  # first date key found is the one to use
    except Exception:
        log.debug("plan_tag_repairs: date failed for %s", path, exc_info=True)

    # --- description: trim promo spam ---------------------------------------
    try:
        for key in _DESC_KEYS:
            try:
                value = tags[key]
            except (KeyError, TypeError):
                continue
            new = trim_description(_frame_text(value))
            if new is None:
                plan.append((key, value, None))       # delete pure-junk desc
            elif new != _frame_text(value):
                plan.append((key, value, new))
    except Exception:
        log.debug("plan_tag_repairs: description failed for %s", path,
                  exc_info=True)

    # --- comments: drop bare YouTube/source URLs ---------------------------
    try:
        seen: set[object] = set()
        for key in tuple(_COMMENT_KEYS) + tuple(
            k for k in tags.keys() if str(k).startswith(_COMMENT_KEY_PREFIX)
        ):
            if key in seen:
                continue
            seen.add(key)
            try:
                value = tags[key]
            except (KeyError, TypeError):
                continue
            if _is_url(value):
                plan.append((key, value, None))       # delete the URL comment
    except Exception:
        log.debug("plan_tag_repairs: comment failed for %s", path, exc_info=True)

    return plan


def _plan_artist(tags: object, title_key: object, artist: str
                 ) -> list[tuple[object, object, str | None]]:
    """Plan writing *artist* when the artist tag is missing or empty.

    Never overwrites a real artist value. Creates the correct key for the
    container (ID3 TPE1 frame, MP4 ©ART, vorbis comment) when absent —
    ``value`` of None means "create this key" for the writer.
    """
    for key in _ARTIST_KEYS:
        try:
            value = tags[key]
        except (KeyError, TypeError):
            continue
        if _frame_text(value).strip():
            return []             # a real artist is already there
        return [(key, value, artist)]

    # No artist key at all — create it in the container's shape.
    new_key = _ARTIST_KEY_FOR_TITLE.get(str(title_key))
    if new_key is None:
        return []
    return [(new_key, None, artist)]


def trim_description(text: object) -> str | None:
    """Return the first useful paragraph of a YouTube description, or None.

    YouTube descriptions start with the real blurb and then a wall of promo
    links/subscribe spam. Keep the leading paragraphs until one contains a
    URL or a promo phrase, cap the length, and drop empty results (the tag
    is then removed rather than rewritten).
    """
    if not isinstance(text, str) or not text.strip():
        return None
    kept: list[str] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        low = para.lower()
        if "http" in low or any(m in low for m in _PROMO_MARKERS):
            break
        kept.append(para)
        if sum(len(p) for p in kept) > _MAX_DESC_CHARS:
            break
    if not kept:
        return None
    out = "\n\n".join(kept).strip()
    if len(out) > _MAX_DESC_CHARS:
        out = out[:_MAX_DESC_CHARS].rstrip()
    return out or None


def _iter_tag_values(tags: object, keys: tuple[str, ...]):
    """Yield (key, value) for the first matching key present in *tags*.

    ID3 frames (mutagen) are not plain strings — they are frame objects, so
    extraction differs from dict-style tags (MP4/vorbis/matroska).
    """
    for key in keys:
        try:
            value = tags[key]
        except (KeyError, TypeError):
            continue
        yield key, value


def _frame_text(value: object) -> str:
    """Best-effort plain text out of a mutagen tag value."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and value:
        return _frame_text(value[0])
    text = getattr(value, "text", None)
    if isinstance(text, list) and text:
        return str(text[0])
    if isinstance(text, str):
        return text
    return str(value)


def _write_tag(tags: object, key: object, value: object, new: str) -> None:
    """Write *new* back to *tags[key]*, preserving the value's shape:
    ID3 frames keep their frame type, MP4/vorbis lists stay lists."""
    if isinstance(getattr(value, "text", None), list):
        value.text = [new]        # type: ignore[union-attr]
        tags[key] = value         # type: ignore[index]
    elif isinstance(value, (list, tuple)):
        tags[key] = [new]         # type: ignore[index]
    else:
        tags[key] = new           # type: ignore[index]


def sync_embedded_tags(path: str | Path, clean_tags: list[str] | None) -> bool:
    """Repair the embedded tags of *path* (see ``plan_tag_repairs()``):

    * **title** — strip fluff tags (needs *clean_tags*) and split
      ``Artist - Song`` into the artist tag
    * **description** — trim YouTube promo spam
    * **date** — collapse ``20261001`` to ``2026`` (some players overflow
      the m4a ©day atom's 16-bit read: 20261001 → 10377)
    * **comment** — drop bare source-URL comments yt-dlp writes

    The description/date/artist-split/comment repairs run even with an
    empty *clean_tags* list — they repair yt-dlp's metadata, which is
    independent of the Clean Title option. Returns True when anything was
    written. Safe to call on files with no embedded tags (returns False),
    and never raises.
    """
    try:
        import mutagen
    except ImportError:  # pragma: no cover — mutagen is pinned in requirements
        return False

    plan = plan_tag_repairs(path, clean_tags)
    if not plan:
        return False

    try:
        audio = mutagen.File(path)
    except Exception:
        log.debug("sync_embedded_tags: cannot open %s", path, exc_info=True)
        return False
    if audio is None or audio.tags is None:
        return False

    tags = audio.tags
    changed = False
    for key, value, new in plan:
        try:
            if new is None:
                del tags[key]                       # type: ignore[union-attr]
            elif value is None:
                # Create a missing key in the container's shape (artist).
                if str(key) == "TPE1":
                    from mutagen.id3 import TPE1
                    tags[key] = TPE1(encoding=3, text=[new])  # type: ignore[index]
                else:
                    tags[key] = [new]                           # type: ignore[index]
            else:
                _write_tag(tags, key, value, new)
            changed = True
        except (KeyError, TypeError, ValueError):
            log.debug("sync_embedded_tags: %s failed for %s", key, path,
                      exc_info=True)

    if not changed:
        return False
    try:
        audio.save()
        return True
    except Exception:
        log.debug("sync_embedded_tags: save failed for %s", path, exc_info=True)
        return False
