"""Tests for app.tags — embedded title/description repair after Clean Title.

The tag-layer tests generate a real silent mp3/m4a with ffmpeg (skipped when
ffmpeg is unavailable, mirroring tests/test_converter_worker.py) because
mutagen needs a parseable container, not just an ID3 header.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import ClassVar

import pytest
from mutagen import File as MutagenFile
from mutagen.id3 import COMM, ID3, TDRC, TIT2, TPE1, TXXX
from mutagen.mp4 import MP4

from app.cleaner import clean_title, rename_with_cleanup
from app.tags import (
    normalize_year,
    split_artist_title,
    sync_embedded_tags,
    trim_description,
)

FFMPEG = shutil.which("ffmpeg")

needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")


# -- trim_description ---------------------------------------------------------

class TestTrimDescription:
    def test_keeps_leading_blurb(self):
        text = "A nice blurb.\n\nFollow me: https://example.com\nSubscribe!"
        assert trim_description(text) == "A nice blurb."

    def test_drops_pure_promo(self):
        assert trim_description("Subscribe! https://x.io\n\nBuy merch") is None

    def test_empty_and_non_string(self):
        assert trim_description("   ") is None
        assert trim_description(None) is None
        assert trim_description(42) is None

    def test_long_blurb_is_capped(self):
        text = ("word " * 400).strip()
        out = trim_description(text)
        assert out is not None
        assert len(out) <= 1000

    def test_truncation_keeps_paragraphs(self):
        text = "First.\n\nSecond still fine.\n\nhttps://promo.example"
        assert trim_description(text) == "First.\n\nSecond still fine."


# -- split_artist_title -------------------------------------------------------

class TestSplitArtistTitle:
    def test_basic_split(self):
        assert split_artist_title(
            "Rick Astley - Never Gonna Give You Up"
        ) == ("Rick Astley", "Never Gonna Give You Up")

    def test_only_first_separator_splits(self):
        assert split_artist_title("A - B - C") == ("A", "B - C")

    def test_en_and_em_dash(self):
        assert split_artist_title("Artist – Song") == ("Artist", "Song")
        assert split_artist_title("Artist — Song") == ("Artist", "Song")

    def test_no_split_without_separator(self):
        assert split_artist_title("Just A Song Title") is None

    def test_empty_sides_do_not_split(self):
        assert split_artist_title(" - Song") is None
        assert split_artist_title("Artist - ") is None
        assert split_artist_title("") is None

    def test_non_string(self):
        assert split_artist_title(None) is None  # type: ignore[arg-type]

    def test_no_space_around_dash_is_not_split(self):
        # "AC/DC-style" hyphens inside words must not trigger a split
        assert split_artist_title("A-BC") is None


# -- normalize_year -----------------------------------------------------------

class TestNormalizeYear:
    def test_compact_date_becomes_year(self):
        assert normalize_year("20261001") == "2026"

    def test_iso_date_becomes_year(self):
        assert normalize_year("2026-10-01") == "2026"

    def test_bare_year_is_left_alone(self):
        assert normalize_year("2026") is None

    def test_non_date_values(self):
        assert normalize_year("10377") is None
        assert normalize_year("Live") is None
        assert normalize_year(None) is None


# -- sync_embedded_tags -------------------------------------------------------

RAW_TITLE = "Some Song (Official Video) [4K]"
CLEAN_TITLE = "Some Song"


def _make_mp3(path) -> str:
    subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100",
         "-t", "1", "-q:a", "9", str(path)],
        capture_output=True, check=True,
    )
    mp3 = ID3(str(path))
    mp3.add(TIT2(encoding=3, text=[RAW_TITLE]))
    mp3.add(TXXX(encoding=3, desc="description",
                 text=["A blurb.\n\nSubscribe: https://x.io"]))
    mp3.save(str(path))
    return str(path)


def _make_m4a(path) -> str:
    subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100",
         "-t", "1", "-c:a", "aac", "-b:a", "64k", str(path)],
        capture_output=True, check=True,
    )
    m4a = MP4(str(path))
    m4a.tags["\xa9nam"] = [RAW_TITLE]
    m4a.tags["desc"] = ["A blurb.\n\nSubscribe: https://x.io"]
    m4a.save(str(path))
    return str(path)


@needs_ffmpeg
class TestSyncEmbeddedTags:
    TAGS: ClassVar[list[str]] = ["Official Video", "4K"]

    def test_mp3_title_cleaned_and_description_trimmed(self, tmp_path):
        p = _make_mp3(tmp_path / "in.mp3")
        assert sync_embedded_tags(p, self.TAGS) is True

        f = MutagenFile(p)
        assert str(f.tags["TIT2"].text[0]) == CLEAN_TITLE
        assert str(f.tags["TXXX:description"].text[0]) == "A blurb."

    def test_m4a_title_cleaned_and_description_trimmed(self, tmp_path):
        p = _make_m4a(tmp_path / "in.m4a")
        assert sync_embedded_tags(p, self.TAGS) is True

        f = MutagenFile(p)
        assert f.tags["\xa9nam"][0] == CLEAN_TITLE
        assert f.tags["desc"][0] == "A blurb."

    def test_noop_when_already_clean(self, tmp_path):
        p = _make_mp3(tmp_path / "in.mp3")
        # First call trims the junk; a second run has nothing left to change.
        sync_embedded_tags(p, self.TAGS)
        assert sync_embedded_tags(p, self.TAGS) is False

    def test_noop_without_tags(self, tmp_path):
        subprocess.run(
            [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100",
             "-t", "1", "-q:a", "9", str(tmp_path / "plain.mp3")],
            capture_output=True, check=True,
        )
        p = str(tmp_path / "plain.mp3")
        # No embedded title/description at all → nothing to write, no crash.
        assert sync_embedded_tags(p, self.TAGS) is False

    def test_empty_tag_list_still_repairs_date_and_description(self, tmp_path):
        """Clean Title off → no title/artist rewrite, but the year/description
        repairs still run (they fix yt-dlp's metadata, not the filename)."""
        p = _make_mp3(tmp_path / "in.mp3")
        assert sync_embedded_tags(p, []) is True

        f = MutagenFile(p)
        # title untouched (Clean Title disabled)
        assert str(f.tags["TIT2"].text[0]) == RAW_TITLE
        # description trimmed anyway
        assert str(f.tags["TXXX:description"].text[0]) == "A blurb."

    def test_artist_prefix_moves_to_artist_tag(self, tmp_path):
        """'Artist - Song' title: song in title, artist filled in TPE1."""
        p = tmp_path / "split.mp3"
        subprocess.run(
            [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100",
             "-t", "1", "-q:a", "9", str(p)],
            capture_output=True, check=True,
        )
        mp3 = ID3(str(p))
        mp3.add(TIT2(encoding=3, text=["Rick Astley - Never Gonna Give You Up"]))
        mp3.save(str(p))

        assert sync_embedded_tags(str(p), self.TAGS) is True

        f = MutagenFile(str(p))
        assert str(f.tags["TIT2"].text[0]) == "Never Gonna Give You Up"
        assert str(f.tags["TPE1"].text[0]) == "Rick Astley"

    def test_existing_artist_is_not_overwritten(self, tmp_path):
        p = tmp_path / "keep.mp3"
        subprocess.run(
            [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100",
             "-t", "1", "-q:a", "9", str(p)],
            capture_output=True, check=True,
        )
        mp3 = ID3(str(p))
        mp3.add(TIT2(encoding=3, text=["Wrong Artist - Some Song"]))
        mp3.add(TPE1(encoding=3, text=["Real Artist"]))
        mp3.save(str(p))

        assert sync_embedded_tags(str(p), self.TAGS) is True

        f = MutagenFile(str(p))
        assert str(f.tags["TIT2"].text[0]) == "Some Song"
        assert str(f.tags["TPE1"].text[0]) == "Real Artist"

    def test_m4a_artist_split(self, tmp_path):
        p = _make_m4a(tmp_path / "split.m4a")
        m4a = MP4(p)
        m4a.tags["\xa9nam"] = ["Rick Astley - Never Gonna Give You Up"]
        m4a.save(p)

        assert sync_embedded_tags(p, self.TAGS) is True

        f = MutagenFile(p)
        assert f.tags["\xa9nam"][0] == "Never Gonna Give You Up"
        assert f.tags["\xa9ART"][0] == "Rick Astley"

    def test_m4a_full_date_collapsed_to_year(self, tmp_path):
        """20261001 must not leak into ©day — players that read it as a
        16-bit int display 10377 (20261001 & 0xFFFF)."""
        p = _make_m4a(tmp_path / "year.m4a")
        m4a = MP4(p)
        m4a.tags["\xa9day"] = ["20261001"]
        m4a.save(p)

        assert sync_embedded_tags(p, self.TAGS) is True

        f = MutagenFile(p)
        assert f.tags["\xa9day"][0] == "2026"

    def test_mp3_full_date_collapsed_to_year(self, tmp_path):
        p = _make_mp3(tmp_path / "year.mp3")
        mp3 = ID3(p)
        mp3.add(TDRC(encoding=3, text=["20261001"]))
        mp3.save(p)

        assert sync_embedded_tags(p, self.TAGS) is True

        f = MutagenFile(p)
        assert str(f.tags["TDRC"].text[0]) == "2026"

    def test_comment_urls_are_removed(self, tmp_path):
        """yt-dlp writes the source URL into ©cmt / COMM / TXXX:comment —
        a bare URL is junk; a real comment survives."""
        p = _make_m4a(tmp_path / "url.m4a")
        m4a = MP4(p)
        m4a.tags["\xa9cmt"] = ["https://www.youtube.com/watch?v=1l7wbZmdtys"]
        m4a.save(p)

        assert sync_embedded_tags(p, self.TAGS) is True

        f = MutagenFile(p)
        assert "\xa9cmt" not in f.tags

    def test_mp3_url_comment_removed_but_real_comment_kept(self, tmp_path):
        p = _make_mp3(tmp_path / "comments.mp3")
        mp3 = ID3(p)
        mp3.add(COMM(encoding=3, lang="eng", desc="",
                     text=["https://www.youtube.com/watch?v=abc123"]))
        mp3.add(COMM(encoding=3, lang="eng", desc="my note",
                     text=["my favourite bit"]))
        mp3.add(TXXX(encoding=3, desc="comment", text=["https://youtu.be/x"]))
        mp3.save(p)

        assert sync_embedded_tags(p, self.TAGS) is True

        f = MutagenFile(p)
        comms = [str(fr.text[0]) for fr in f.tags.getall("COMM")]
        assert comms == ["my favourite bit"]
        assert "TXXX:comment" not in f.tags

    def test_plan_does_not_write(self, tmp_path):
        from app.tags import plan_tag_repairs
        p = _make_m4a(tmp_path / "plan.m4a")
        m4a = MP4(p)
        m4a.tags["\xa9day"] = ["20261001"]
        m4a.save(p)

        plan = plan_tag_repairs(p, self.TAGS)
        assert plan, "expected a year repair in the plan"

        # nothing written by planning
        f = MutagenFile(p)
        assert f.tags["\xa9day"][0] == "20261001"

        assert sync_embedded_tags(p, self.TAGS) is True
        f = MutagenFile(p)
        assert f.tags["\xa9day"][0] == "2026"

    def test_missing_file_returns_false(self, tmp_path):
        assert sync_embedded_tags(tmp_path / "nope.mp3", self.TAGS) is False


# -- rename_with_cleanup integration -----------------------------------------

class TestRenameIntegration:
    def test_rename_cleans_embedded_title(self, tmp_path):
        """Clean Title renames the file AND the embedded title tag follows."""
        src = tmp_path / f"{RAW_TITLE}.mp3"
        _make_mp3(src)

        new = rename_with_cleanup(src, ["Official Video", "4K"])
        assert new is not None
        assert new.name == f"{CLEAN_TITLE}.mp3"

        f = MutagenFile(str(new))
        assert str(f.tags["TIT2"].text[0]) == CLEAN_TITLE

    def test_already_clean_name_still_trims_description(self, tmp_path):
        """Even with no rename, the promo description gets repaired."""
        src = tmp_path / f"{clean_title(RAW_TITLE, ['Official Video', '4K'])}.mp3"
        _make_mp3(src)

        assert rename_with_cleanup(src, ["Official Video", "4K"]) is None

        f = MutagenFile(str(src))
        assert str(f.tags["TXXX:description"].text[0]) == "A blurb."
