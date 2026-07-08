"""smart_naming 순수 함수 테스트.

목적지 자동 결정 로직(단일 폴더/단일 파일/다중 항목, 이름 충돌 시 _2 접미사,
압축해제 시 단일 최상위 항목 vs 다중 항목, 빈 아카이브)을 촘촘히 커버한다.
"""
from __future__ import annotations

import pathlib

import pytest

from packnine.application import smart_naming
from packnine.domain.entities import ArchiveEntry, ArchiveManifest


def _entry(name: str, is_dir: bool = False) -> ArchiveEntry:
    return ArchiveEntry(name=name, size=1, compressed_size=1, is_dir=is_dir)


# ----------------------------------------------------------------------
# resolve_smart_compress_destination
# ----------------------------------------------------------------------


def test_single_folder_uses_folder_name(tmp_path: pathlib.Path) -> None:
    folder = tmp_path / "photos"
    folder.mkdir()

    destination = smart_naming.resolve_smart_compress_destination([folder])

    assert destination == tmp_path / "photos.zip"


def test_single_file_uses_file_stem(tmp_path: pathlib.Path) -> None:
    file_path = tmp_path / "report.docx"
    file_path.write_text("dummy", encoding="utf-8")

    destination = smart_naming.resolve_smart_compress_destination([file_path])

    assert destination == tmp_path / "report.zip"


def test_multiple_items_uses_common_parent_name(tmp_path: pathlib.Path) -> None:
    parent = tmp_path / "myfolder"
    parent.mkdir()
    a = parent / "a.txt"
    a.write_text("a", encoding="utf-8")
    b = parent / "b.txt"
    b.write_text("b", encoding="utf-8")

    destination = smart_naming.resolve_smart_compress_destination([a, b])

    assert destination == parent / "myfolder.zip"


def test_custom_extension_is_used(tmp_path: pathlib.Path) -> None:
    folder = tmp_path / "photos"
    folder.mkdir()

    destination = smart_naming.resolve_smart_compress_destination([folder], extension=".7z")

    assert destination == tmp_path / "photos.7z"


def test_collision_appends_numeric_suffix(tmp_path: pathlib.Path) -> None:
    folder = tmp_path / "photos"
    folder.mkdir()
    # 이미 photos.zip이 존재하는 상태를 만든다.
    (tmp_path / "photos.zip").write_bytes(b"")

    destination = smart_naming.resolve_smart_compress_destination([folder])

    assert destination == tmp_path / "photos_2.zip"


def test_collision_appends_incrementing_suffix_until_free(tmp_path: pathlib.Path) -> None:
    folder = tmp_path / "photos"
    folder.mkdir()
    (tmp_path / "photos.zip").write_bytes(b"")
    (tmp_path / "photos_2.zip").write_bytes(b"")
    (tmp_path / "photos_3.zip").write_bytes(b"")

    destination = smart_naming.resolve_smart_compress_destination([folder])

    assert destination == tmp_path / "photos_4.zip"


# ----------------------------------------------------------------------
# resolve_smart_extract_destination
# ----------------------------------------------------------------------


def test_empty_manifest_returns_base_destination_unchanged(tmp_path: pathlib.Path) -> None:
    manifest = ArchiveManifest(entries=[], format_name=".zip")
    archive_path = tmp_path / "empty.zip"
    base_destination = tmp_path / "extracted"

    destination = smart_naming.resolve_smart_extract_destination(
        manifest, archive_path, base_destination
    )

    assert destination == base_destination


def test_single_top_level_folder_returns_base_destination_unchanged(tmp_path: pathlib.Path) -> None:
    manifest = ArchiveManifest(
        entries=[
            _entry("photos/", is_dir=True),
            _entry("photos/a.jpg"),
            _entry("photos/sub/b.jpg"),
        ],
        format_name=".zip",
    )
    archive_path = tmp_path / "photos.zip"
    base_destination = tmp_path / "extracted"

    destination = smart_naming.resolve_smart_extract_destination(
        manifest, archive_path, base_destination
    )

    assert destination == base_destination


def test_single_top_level_file_returns_base_destination_unchanged(tmp_path: pathlib.Path) -> None:
    manifest = ArchiveManifest(entries=[_entry("only_file.txt")], format_name=".zip")
    archive_path = tmp_path / "only_file.zip"
    base_destination = tmp_path / "extracted"

    destination = smart_naming.resolve_smart_extract_destination(
        manifest, archive_path, base_destination
    )

    assert destination == base_destination


def test_multiple_top_level_items_wraps_in_archive_stem_folder(tmp_path: pathlib.Path) -> None:
    manifest = ArchiveManifest(
        entries=[_entry("a.txt"), _entry("b.txt"), _entry("sub/c.txt")],
        format_name=".zip",
    )
    archive_path = tmp_path / "photos.zip"
    base_destination = tmp_path / "extracted"

    destination = smart_naming.resolve_smart_extract_destination(
        manifest, archive_path, base_destination
    )

    assert destination == base_destination / "photos"


def test_multiple_top_level_items_collision_appends_numeric_suffix(tmp_path: pathlib.Path) -> None:
    manifest = ArchiveManifest(
        entries=[_entry("a.txt"), _entry("b.txt")],
        format_name=".zip",
    )
    archive_path = tmp_path / "photos.zip"
    base_destination = tmp_path / "extracted"
    base_destination.mkdir()
    (base_destination / "photos").mkdir()

    destination = smart_naming.resolve_smart_extract_destination(
        manifest, archive_path, base_destination
    )

    assert destination == base_destination / "photos_2"


@pytest.mark.parametrize(
    "entry_names",
    [
        ["a.txt", "b.txt"],
        ["dir1/x.txt", "dir2/y.txt"],
        ["a.txt", "dir/b.txt", "dir/c.txt"],
    ],
)
def test_multiple_distinct_top_level_names_detected(
    tmp_path: pathlib.Path, entry_names: list[str]
) -> None:
    manifest = ArchiveManifest(entries=[_entry(n) for n in entry_names], format_name=".zip")
    archive_path = tmp_path / "archive.zip"
    base_destination = tmp_path / "extracted"

    destination = smart_naming.resolve_smart_extract_destination(
        manifest, archive_path, base_destination
    )

    assert destination == base_destination / "archive"
