"""Title-cleaning utilities."""

import re
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
        bracket_pat = rf"[\[\(][^\[\]\(\)]*?" + t + r"[^\[\]\(\)]*?[\]\)]"
        result = re.sub(bracket_pat, " ", result, flags=re.IGNORECASE)
        # 2. Unclosed bracket at end: (tag  or  [tag  (no closing bracket)
        unclosed_pat = rf"[\[\(][^\[\]\(\)]*?" + t + r"[^\[\]\(\)]*?\s*$"
        result = re.sub(unclosed_pat, " ", result, flags=re.IGNORECASE)
        # 3. Opener without closing at the start/middle: capture up to end or next opener
        unclosed_mid = rf"[\[\(][^\[\]\(\)]*?" + t + r"[^\[\]\(\)]*?"
        result = re.sub(unclosed_mid, " ", result, flags=re.IGNORECASE)
        # 4. Bare tag (surrounded by whitespace / separators)
        bare_pat = rf"(?:^|[\s\-|])(?:" + t + r")(?:[\s\-|]|$)"
        result = re.sub(bare_pat, " ", result, flags=re.IGNORECASE)
        # 5. Plain fallback — any remaining occurrence of the raw tag text
        result = re.sub(t, " ", result, flags=re.IGNORECASE)

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

    Returns the new Path if renamed, else None. Collisions get a numeric suffix.
    """
    if not tags:
        return None
    fp = Path(path)
    if not fp.exists() or not fp.is_file():
        return None
    new_name = clean_title(fp.stem, tags)
    if new_name == fp.stem:
        return None
    new_path = fp.parent / f"{new_name}{fp.suffix}"
    counter = 1
    while new_path.exists() and new_path != fp:
        new_path = fp.parent / f"{new_name} ({counter}){fp.suffix}"
        counter += 1
    if new_path == fp:
        return None
    try:
        fp.rename(new_path)
        return new_path
    except OSError:
        return None


def discover_new_files(
    outdir: str | Path,
    start_ts: float,
    extensions: set[str],
) -> list[Path]:
    """Return files in outdir newer than start_ts matching the given extensions."""
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
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            found.append(p)
    return found
