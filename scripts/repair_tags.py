#!/usr/bin/env python
"""One-off tag repair for files downloaded by older app versions.

Fixes what earlier releases left behind, without re-downloading:

* **title** — strip fluff tags (``Official Music Video`` …) and split
  ``Artist - Song`` into the artist tag
* **year**  — collapse ``20261001`` → ``2026`` (the m4a ``10377`` bug)
* **description** — trim the YouTube promo wall to the first real paragraph
* **comment** — drop the bare source-URL comments yt-dlp writes
* **filename** — optionally rename the file the same way Clean Title would
  (``--rename``; off by default because the script first runs as a preview)

Usage::

    # 1. preview (nothing is written)
    python scripts/repair_tags.py "D:\\Music" --dry-run

    # 2. repair tags in place, recursively, audio + video
    python scripts/repair_tags.py "D:\\Music" --recursive

    # 3. also rename files the way Clean Title does
    python scripts/repair_tags.py "D:\\Music" --recursive --rename

Only mp3/m4a/mp4/opus/ogg/flac/mkv — anything mutagen can open. Every
operation is per-file and self-fenced: an unreadable file is reported and
skipped, never fatal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cleaner import DEFAULT_CLEAN_TAGS, clean_title, parse_tag_list
from app.tags import plan_tag_repairs, sync_embedded_tags

AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".opus", ".ogg", ".flac"}
VIDEO_EXTS = {".mkv", ".mp4", ".webm"}
# What the key means in the preview output
_KEY_LABELS = {
    "TIT2": "title", "\xa9nam": "title",
    "TPE1": "artist", "\xa9ART": "artist",
    "TDRC": "year", "TYER": "year", "\xa9day": "year",
    "date": "year", "DATE": "year", "year": "year",
}


def _label(key: object) -> str:
    s = str(key)
    return _KEY_LABELS.get(s, s)


def _short(value: object, limit: int = 60) -> str:
    from app.tags import _frame_text  # local: trivial helper reuse

    text = _frame_text(value).replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text or "(empty)"


def collect_files(root: Path, recursive: bool, video: bool) -> list[Path]:
    exts = AUDIO_EXTS | (VIDEO_EXTS if video else set())
    if root.is_file():
        return [root]
    it = root.rglob("*") if recursive else root.iterdir()
    return sorted(p for p in it
                  if p.is_file() and p.suffix.lower() in exts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Repair embedded tags (title/year/description/comment) "
                    "of files downloaded by older app versions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage::", 1)[-1],
    )
    ap.add_argument("path", type=Path, help="file or folder to repair")
    ap.add_argument("--dry-run", action="store_true",
                    help="show planned changes without writing (default: "
                         "writes; pass --dry-run to preview)")
    ap.add_argument("--recursive", action="store_true",
                    help="descend into subfolders")
    ap.add_argument("--rename", action="store_true",
                    help="also rename files the way Clean Title would")
    ap.add_argument("--tags", default=", ".join(DEFAULT_CLEAN_TAGS),
                    help="comma-separated cleanup tags (same defaults the "
                         "app uses)")
    ap.add_argument("--video", action="store_true",
                    help="include video containers (.mkv/.webm/.mp4 video)")
    args = ap.parse_args(argv)

    if not args.path.exists():
        ap.error(f"no such path: {args.path}")

    tags = parse_tag_list(args.tags)
    files = collect_files(args.path, args.recursive, args.video)
    if not files:
        print("No matching files found.")
        return 0

    changed = skipped = renamed = 0
    for fp in files:
        plan = plan_tag_repairs(fp, tags)
        do_rename = False
        if args.rename and fp.suffix.lower() in AUDIO_EXTS | VIDEO_EXTS:
            cleaned = clean_title(fp.stem, tags)
            do_rename = bool(cleaned and cleaned != fp.stem)

        if not plan and not do_rename:
            skipped += 1
            continue

        print(f"{fp}")
        for key, value, new in plan:
            if new is None:
                print(f"    {_label(key)}: delete (was: {_short(value)})")
            else:
                print(f"    {_label(key)}: {_short(value)}  ->  {_short(new)}")
        if do_rename:
            new_name = f"{clean_title(fp.stem, tags)}{fp.suffix}"
            print(f"    file: rename -> {new_name}")

        if args.dry_run:
            changed += 1
            continue

        if sync_embedded_tags(fp, tags):
            changed += 1
        if args.rename and do_rename:
            target = fp.with_name(f"{clean_title(fp.stem, tags)}{fp.suffix}")
            counter = 1
            while target.exists() and target != fp:
                target = fp.with_name(
                    f"{clean_title(fp.stem, tags)} ({counter}){fp.suffix}")
                counter += 1
            try:
                # rename_with_cleanup would also sync, but tags are already
                # repaired above — just move the file.
                fp.rename(target)
                renamed += 1
            except OSError as exc:
                print(f"    !! rename failed: {exc}")

    print()
    mode = "Would change" if args.dry_run else "Changed"
    print(f"{len(files)} file(s) scanned — {mode}: {changed}, "
          f"already clean: {skipped}"
          + (f", renamed: {renamed}" if renamed else ""))
    if args.dry_run and changed:
        print("Dry run: nothing was written. Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
