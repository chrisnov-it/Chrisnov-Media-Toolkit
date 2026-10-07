"""Title-cleaning utilities."""

import re
import sys
from pathlib import Path

# Default tags to strip from titles
DEFAULT_CLEAN_TAGS = [
    # --- English ---
    "Official Music Video",
    "Official Video",
    "Official Lyrics Video",
    "Official Lyric Video",
    "Official Live Video",
    "Official Visualizer",
    "Music Video",
    "Lyric Video",
    "Lyrics Video",
    "Official Audio",
    "Audio",
    "Topic",
    "Full Album",
    "Album Stream",
    "Live Performance",
    "Live Session",
    "Acoustic Version",
    "Official Acoustic",
    "Visualizer",
    "HD",
    "HQ",
    "4K",
    "MV",
    # --- Indonesian ---
    "Video Lirik",
    "Lirik Video",
    "Lirik Lagu",
    "Lirik",
    "Video Klip",
    "Musik Video",
    "Audio Visual",
    "Lagu Resmi",
    "Resmi",
    "Versi Akustik",
    "Live",
]


def parse_tag_list(raw: str) -> list[str]:
    """Parse a comma-separated tag string into a clean list of non-empty tags."""
    return [t.strip() for t in raw.split(",") if t.strip()]


def clean_title(title: str, tags: list[str]) -> str:
    """Strip common fluff tags like 'Official Music Video' from a title.

    Handles:
      - bare words anywhere
      - [bracketed tag] or (parenthesised tag)
      - dash/pipe/forward-slash separators
    Whitespace is normalised and trailing punctuation trimmed.
    """
    result = title
    # Sort tags longest-first so 'Official Music Video' beats 'Music Video'
    sorted_tags = sorted(set(tags), key=lambda s: -len(s))
    for tag in sorted_tags:
        t = re.escape(tag)
        # 1. Fully bracketed: [tag], (tag), [some tag], (some tag)
        bracket_pat = r"[\[\(][^\[\]\(\)]*?" + t + r"[^\[\]\(\)]*?[\]\)]"
        result = re.sub(bracket_pat, " ", result, flags=re.IGNORECASE)
        # 2. Unclosed bracket at end: (tag  or  [tag  (no closing bracket)
        unclosed_pat = r"[\[\(][^\[\]\(\)]*?" + t + r"[^\[\]\(\)]*?\s*$"
        result = re.sub(unclosed_pat, " ", result, flags=re.IGNORECASE)
        # 3. Opener without closing at the start/middle: capture up to end or next opener
        unclosed_mid = r"[\[\(][^\[\]\(\)]*?" + t + r"[^\[\]\(\)]*?"
        result = re.sub(unclosed_mid, " ", result, flags=re.IGNORECASE)
        # 4. Bare tag (surrounded by whitespace / separators)
        bare_pat = r"(?:^|[\s\-|])(?:" + t + r")(?:[\s\-|]|$)"
        result = re.sub(bare_pat, " ", result, flags=re.IGNORECASE)
        # 5. Plain fallback — any remaining occurrence of the raw tag text,
        #    but only as a whole word. Without the boundaries this rule eats
        #    substrings: tag "Live" turned "Alive" into "A", "HD" turned
        #    "UHD" into "U", tag "Topic" turned "Topical" into "ical".
        #    (\b only where the tag actually starts/ends with a word char, so
        #    custom tags like "R&B" still match.)
        left = r"\b" if re.match(r"\w", tag) else ""
        right = r"\b" if re.search(r"\w$", tag) else ""
        result = re.sub(left + t + right, " ", result, flags=re.IGNORECASE)

    # Remove leftover dangling bracket characters (opened but never closed, or vice versa)
    # e.g. a lone "(" or "[" at end, or "]" / ")" at start, possibly with surrounding spaces
    result = re.sub(r"[\[\(][^\[\]\(\)]*$", "", result)      # unclosed ( or [ at tail
    result = re.sub(r"^[^\[\]\(\)]*[\]\)]", "", result)       # unmatched ) or ] at head
    result = re.sub(r"\s+[\[\(]\s*$", "", result)             # trailing orphan opener
    result = re.sub(r"^\s*[\]\)]\s+", "", result)             # leading orphan closer

    # Collapse whitespace and trim noisy punctuation
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"(?:\s*[\|\/,–—\-]\s*){2,}", " - ", result)
    result = re.sub(r"[\s\|\/,–—\-:]+$", "", result)
    result = re.sub(r"^[\s\|\/,–—\-:]+", "", result).strip()
    # Remove any remaining empty or whitespace-only brackets
    result = re.sub(r"\[\s*\]|\(\s*\)", "", result).strip()
    result = re.sub(r"\s+", " ", result).strip()
    return result


def rename_with_cleanup(path: str | Path, tags: list[str] | None) -> Path | None:
    """If `tags` is set and non-empty, rename the file with a cleaned title.

    Embedded tags are always repaired afterwards (year normalization and
    description trimming are independent of Clean Title; the title/artist
    split only runs when *tags* is set) — see app/tags.py.

    Returns the new Path if renamed, else None. Collisions get a numeric suffix.
    """
    fp = Path(path)
    if not fp.exists() or not fp.is_file():
        return None
    try:
        from .tags import sync_embedded_tags

        def _sync(target: Path) -> None:
            try:
                sync_embedded_tags(target, tags)
            except Exception:  # noqa: BLE001 — tag repair is best-effort
                pass

        if not tags:
            _sync(fp)
            return None
        new_name = clean_title(fp.stem, tags)
        if new_name == fp.stem:
            # Filename is already clean, but the embedded tags may still need
            # repair (year/description/title) — fix tags without renaming.
            _sync(fp)
            return None
        new_path = fp.parent / f"{new_name}{fp.suffix}"
        counter = 1
        while new_path.exists() and new_path != fp:
            new_path = fp.parent / f"{new_name} ({counter}){fp.suffix}"
            counter += 1
        if new_path == fp:
            _sync(fp)
            return None
        try:
            fp.rename(new_path)
        except OSError:
            return None
        _sync(new_path)
        return new_path
    except Exception:  # noqa: BLE001 — tag repair import/call is best-effort
        return None


def discover_new_files(
    outdir: str | Path,
    start_ts: float,
    extensions: set[str],
) -> list[Path]:
    """Return files in outdir newer than start_ts matching the given extensions.

    A file that already existed before the batch is never returned, even when
    something else bumps its mtime while we download: Windows reports creation
    time as st_ctime and macOS/BSD as st_birthtime, and those are checked in
    addition to the mtime. Linux has no creation-time stat, so it keeps the
    mtime-only behaviour (best the platform can offer).
    """
    out = Path(outdir)
    if not out.is_dir():
        return []
    found: list[Path] = []
    cutoff = start_ts - 1  # 1-second fudge
    for p in out.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lstrip(".").lower() not in extensions:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_mtime < cutoff:
            continue
        created = getattr(st, "st_birthtime", None)
        if created is None and sys.platform == "win32":
            created = st.st_ctime  # creation time on Windows
        if created is not None and created < cutoff:
            continue
        found.append(p)
    return found
