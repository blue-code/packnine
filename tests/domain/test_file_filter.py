"""압축 대상 제외 패턴 필터 테스트.

".git, node_modules, *.tmp 빼고 압축"을 위한 규칙이다. 패턴은 사용자가 직접 입력하므로
오타나 빈 항목이 섞여도 동작해야 하고, 무엇보다 **의도치 않게 전부 제외되는 일**이
없어야 한다(압축했더니 빈 아카이브가 나오는 최악의 실패).
"""
from __future__ import annotations

import pathlib

from packnine.domain.file_filter import ExcludeFilter


def test_empty_filter_keeps_everything():
    f = ExcludeFilter.from_text("")

    assert f.is_empty
    assert not f.excludes(pathlib.PurePosixPath("a/b/c.txt"))


def test_matches_by_wildcard_on_file_name():
    f = ExcludeFilter.from_text("*.tmp")

    assert f.excludes(pathlib.PurePosixPath("work/cache.tmp"))
    assert not f.excludes(pathlib.PurePosixPath("work/cache.txt"))


def test_matches_folder_name_at_any_depth():
    # node_modules는 어느 깊이에 있든 통째로 빠져야 한다.
    f = ExcludeFilter.from_text("node_modules")

    assert f.excludes(pathlib.PurePosixPath("node_modules"))
    assert f.excludes(pathlib.PurePosixPath("app/node_modules"))
    assert f.excludes(pathlib.PurePosixPath("app/node_modules/pkg/index.js"))
    assert not f.excludes(pathlib.PurePosixPath("app/node_modules_backup/x.js"))


def test_hidden_dot_folder():
    f = ExcludeFilter.from_text(".git")

    assert f.excludes(pathlib.PurePosixPath(".git/config"))
    assert f.excludes(pathlib.PurePosixPath("repo/.git/HEAD"))
    assert not f.excludes(pathlib.PurePosixPath("repo/.gitignore"))


def test_several_patterns_separated_by_comma_or_newline():
    f = ExcludeFilter.from_text("*.tmp, .git\nnode_modules")

    assert f.excludes(pathlib.PurePosixPath("a.tmp"))
    assert f.excludes(pathlib.PurePosixPath("x/.git/HEAD"))
    assert f.excludes(pathlib.PurePosixPath("x/node_modules/y"))
    assert not f.excludes(pathlib.PurePosixPath("keep.txt"))


def test_blank_and_whitespace_entries_are_ignored():
    # 빈 항목을 패턴으로 받아들이면 전부 제외될 수 있다 - 절대 그러면 안 된다.
    f = ExcludeFilter.from_text(" , ,,\n  \n")

    assert f.is_empty
    assert not f.excludes(pathlib.PurePosixPath("anything.txt"))


def test_matching_is_case_insensitive_like_windows():
    f = ExcludeFilter.from_text("*.TMP")

    assert f.excludes(pathlib.PurePosixPath("cache.tmp"))


def test_pattern_with_path_separator_matches_relative_path():
    f = ExcludeFilter.from_text("build/*")

    assert f.excludes(pathlib.PurePosixPath("build/out.o"))
    assert not f.excludes(pathlib.PurePosixPath("src/build.txt"))


def test_patterns_round_trip_to_text():
    f = ExcludeFilter.from_text("*.tmp, .git")

    assert f.patterns == ("*.tmp", ".git")
