"""Tests for app.cleaner — title cleaning, tag parsing, rename, discovery."""

import time
from pathlib import Path

import pytest

from app.cleaner import (
    DEFAULT_CLEAN_TAGS,
    clean_title,
    discover_new_files,
    parse_tag_list,
    rename_with_cleanup,
)


# -- parse_tag_list ---------------------------------------------------------

class TestParseTagList:
    def test_simple_comma_separated(self):
        assert parse_tag_list("HD, MV, Live") == ["HD", "MV", "Live"]

    def test_strips_whitespace(self):
        assert parse_tag_list("  HD  ,   Live  ") == ["HD", "Live"]

    def test_drops_empty_entries(self):
        assert parse_tag_list("HD,, ,Live,") == ["HD", "Live"]

    def test_empty_string(self):
        assert parse_tag_list("") == []

    def test_whitespace_only(self):
        assert parse_tag_list("   ") == []

    def test_single_tag(self):
        assert parse_tag_list("Official Music Video") == ["Official Music Video"]


# -- clean_title ------------------------------------------------------------

class TestCleanTitle:
    """Test the title-cleaning regex chain against common real-world shapes."""

    @pytest.mark.parametrize("title,expected", [
        # Bracketed English tag
        ("Song Title (Official Music Video)", "Song Title"),
        ("Song Title [Official Video]",       "Song Title"),
        ("Song Title (Official Lyric Video)", "Song Title"),
        # Indonesian tags
        ("Lagu Bagus (Video Lirik)",          "Lagu Bagus"),
        ("Lagu Bagus [Lirik]",                "Lagu Bagus"),
        # Separator forms
        ("Artist - Song | Official Music Video", "Artist - Song"),
        ("Artist - Song / Lyric Video",          "Artist - Song"),
        # Multiple tags in one title
        ("Song (Official Music Video) [HD]",   "Song"),
        # No tag — title unchanged
        ("Just A Song", "Just A Song"),
        # Empty
        ("", ""),
        # Pickup the non-bracketed tail
        ("Song - Official Music Video",        "Song"),
    ])
    def test_common_shapes(self, title, expected):
        assert clean_title(title, DEFAULT_CLEAN_TAGS) == expected

    def test_longest_tag_wins_first(self):
        """'Official Music Video' must beat 'Music Video'. If shorter comes
        first, the longer pattern has nothing left to match."""
        title = "Song Title (Official Music Video)"
        out = clean_title(title, ["Music Video", "Official Music Video"])
        assert out == "Song Title"

        out_reversed = clean_title(title, ["Official Music Video", "Music Video"])
        assert out_reversed == "Song Title"

    def test_unclosed_bracket_at_end(self):
        out = clean_title("Song Title (Official Music Video", DEFAULT_CLEAN_TAGS)
        assert out == "Song Title"

    def test_unclosed_bracket_at_start(self):
        out = clean_title("(Official Music Video) Song Title", DEFAULT_CLEAN_TAGS)
        assert out == "Song Title"

    def test_custom_tags(self):
        """Tags list is configurable — should respect whatever's passed."""
        out = clean_title("Hello (sample)", ["sample"])
        assert out == "Hello"

    def test_case_insensitive(self):
        out = clean_title("song (official music video)", DEFAULT_CLEAN_TAGS)
        assert out == "song"

    def test_orphan_brackets_cleaned_up(self):
        """A bare '(' or ')' left behind after stripping should be removed."""
        out = clean_title("Song Title [", DEFAULT_CLEAN_TAGS)
        assert "[" not in out and "(" not in out

    def test_trailing_separator_stripped(self):
        out = clean_title("Song Title - ", DEFAULT_CLEAN_TAGS)
        assert not out.endswith(" -")
        assert not out.endswith("-")


# -- rename_with_cleanup ---------------------------------------------------

class TestRenameWithCleanup:
    def test_returns_none_when_tags_none(self, tmp_path: Path):
        f = tmp_path / "Song (Official Music Video).mp3"
        f.write_text("x")
        assert rename_with_cleanup(f, None) is None

    def test_returns_none_when_tags_empty(self, tmp_path: Path):
        f = tmp_path / "Song (Official Music Video).mp3"
        f.write_text("x")
        assert rename_with_cleanup(f, []) is None

    def test_returns_none_when_no_cleanup_needed(self, tmp_path: Path):
        f = tmp_path / "Song Title.mp3"
        f.write_text("x")
        assert rename_with_cleanup(f, DEFAULT_CLEAN_TAGS) is None

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        f = tmp_path / "does-not-exist.mp3"
        assert rename_with_cleanup(f, DEFAULT_CLEAN_TAGS) is None

    def test_renames_file(self, tmp_path: Path):
        f = tmp_path / "Song (Official Music Video).mp3"
        f.write_text("x")
        out = rename_with_cleanup(f, DEFAULT_CLEAN_TAGS)
        assert out == tmp_path / "Song.mp3"
        assert out.exists()
        assert not f.exists()

    def test_collision_adds_numeric_suffix(self, tmp_path: Path):
        (tmp_path / "Song (Official Music Video).mp3").write_text("old")
        new = tmp_path / "Song.mp3"
        new.write_text("collision")
        out = rename_with_cleanup(tmp_path / "Song (Official Music Video).mp3",
                                  DEFAULT_CLEAN_TAGS)
        assert out is not None
        assert out.parent == tmp_path
        assert out.name.startswith("Song (")
        assert out.name != "Song.mp3"
        assert "1" in out.name or "2" in out.name or "3" in out.name

    def test_handles_path_string(self, tmp_path: Path):
        f = tmp_path / "Song (Official Music Video).mp3"
        f.write_text("x")
        out = rename_with_cleanup(str(f), DEFAULT_CLEAN_TAGS)
        assert out is not None
        assert out.exists()


# -- discover_new_files ----------------------------------------------------

class TestDiscoverNewFiles:
    def test_returns_files_newer_than_cutoff(self, tmp_path: Path):
        old = tmp_path / "old.mp3"
        new = tmp_path / "new.mp3"
        old.write_text("a")
        new.write_text("b")

        # Backdate 'old' to two seconds before the cutoff, but 'new' stays at now
        cutoff = time.time() - 1
        import os
        os.utime(old, (cutoff - 10, cutoff - 10))

        found = discover_new_files(tmp_path, cutoff, {"mp3"})
        names = sorted(p.name for p in found)
        assert names == ["new.mp3"]

    def test_filters_by_extension(self, tmp_path: Path):
        cutoff = time.time() - 60
        for name in ("a.mp3", "b.txt", "c.MP3", "d.m4a"):
            (tmp_path / name).write_text("x")

        found = discover_new_files(tmp_path, cutoff, {"mp3"})
        names = sorted(p.name for p in found)
        # case-insensitive match
        assert "a.mp3" in names
        assert "d.m4a" not in names
        assert "b.txt" not in names

    def test_nonexistent_outdir_returns_empty(self, tmp_path: Path):
        ghost = tmp_path / "does-not-exist"
        assert discover_new_files(ghost, time.time() - 60, {"mp3"}) == []

    def test_skip_directories(self, tmp_path: Path):
        cutoff = time.time() - 60
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.mp3").write_text("x")
        (tmp_path / "top.mp3").write_text("y")

        found = discover_new_files(tmp_path, cutoff, {"mp3"})
        names = [p.name for p in found]
        assert "top.mp3" in names
        assert "nested.mp3" not in names
