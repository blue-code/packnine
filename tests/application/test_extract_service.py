"""ExtractService 테스트."""
from __future__ import annotations

import pathlib
import sys

import pytest

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
from packnine.application.inspect_service import InspectService
from packnine.domain.entities import ArchiveManifest
from packnine.domain.exceptions import UnsafeArchiveEntryError
from packnine.domain.security_policy import ArchiveSecurityPolicy
from tests.infrastructure.conftest import assert_tree_equal, make_sample_source_tree


@pytest.mark.parametrize("suffix", [".zip", ".7z"])
def test_extract_round_trip_matches_original(tmp_path: pathlib.Path, suffix: str) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / f"out{suffix}"
    CompressService().compress([src_dir], archive_path)

    destination = tmp_path / "extracted"
    manifest = ExtractService().extract(archive_path, destination)

    assert isinstance(manifest, ArchiveManifest)
    # add_files가 src_dir.name을 루트로 담으므로, 그 하위 경로에서 비교한다.
    assert_tree_equal(src_dir, destination / src_dir.name)


def test_extract_with_progress_callback_invoked(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    calls: list[tuple[str, int, int]] = []

    def on_progress(name: str, done: int, total: int) -> None:
        calls.append((name, done, total))

    destination = tmp_path / "extracted"
    ExtractService().extract(archive_path, destination, on_progress=on_progress)

    assert len(calls) > 0


def test_extract_creates_destination_directory(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    destination = tmp_path / "nested" / "does" / "not" / "exist"
    assert not destination.exists()

    ExtractService().extract(archive_path, destination)

    assert destination.exists()


def test_extract_rejects_when_total_size_exceeds_policy(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    # 매우 낮은 상한을 가진 정책을 주입해 정상 아카이브도 거부되는지 검증한다.
    strict_policy = ArchiveSecurityPolicy(max_total_uncompressed_size=1)
    service = ExtractService(security_policy=strict_policy)

    destination = tmp_path / "extracted"
    with pytest.raises(UnsafeArchiveEntryError):
        service.extract(archive_path, destination)


def test_extract_with_wrong_password_raises(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.7z"
    CompressService().compress([src_dir], archive_path, password="correct-horse")

    destination = tmp_path / "extracted"
    with pytest.raises(Exception):
        ExtractService().extract(archive_path, destination, password="wrong-password")


@pytest.mark.skipif(sys.platform != "win32", reason="MoTW(Zone.Identifier)는 Windows/NTFS 전용 기능입니다")
def test_extract_propagates_zone_identifier_from_downloaded_archive(tmp_path: pathlib.Path) -> None:
    # 웹에서 받은 것처럼 아카이브 자체에 Zone.Identifier를 붙인다.
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)
    with open(f"{archive_path}:Zone.Identifier", "wb") as f:
        f.write(b"[ZoneTransfer]\r\nZoneId=3\r\n")

    destination = tmp_path / "extracted"
    ExtractService().extract(archive_path, destination)

    extracted_file = next((destination / src_dir.name).rglob("*.txt"))
    with open(f"{extracted_file}:Zone.Identifier", "rb") as f:
        assert b"ZoneId=3" in f.read()


def test_extract_entries_only_extracts_requested_subset(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    manifest = InspectService().list_contents(archive_path)
    file_entries = [e.name for e in manifest.entries if not e.is_dir]
    assert len(file_entries) >= 2, "샘플 트리에 파일이 최소 2개는 있어야 하는 테스트 전제"
    only_one = file_entries[:1]

    destination = tmp_path / "partial"
    ExtractService().extract_entries(archive_path, only_one, destination)

    extracted_files = [p for p in destination.rglob("*") if p.is_file()]
    assert len(extracted_files) == 1


def test_smart_extract_single_top_level_folder_does_not_wrap_again(tmp_path: pathlib.Path) -> None:
    # add_files는 소스 폴더 자체(src.name/)를 유일한 최상위 항목으로 담으므로,
    # smart_extract는 base_destination을 그대로 사용해야 한다(추가 폴더로 감싸지 않음).
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    base_destination = tmp_path / "extracted"
    manifest = ExtractService().smart_extract(archive_path, base_destination)

    assert isinstance(manifest, ArchiveManifest)
    assert_tree_equal(src_dir, base_destination / src_dir.name)


def test_smart_extract_multiple_loose_files_wraps_in_archive_name_folder(
    tmp_path: pathlib.Path,
) -> None:
    # 최상위에 파일이 여러 개 흩어져 있는 아카이브를 만든다(loose files).
    parent = tmp_path / "loose"
    parent.mkdir()
    a = parent / "a.txt"
    a.write_text("hello a", encoding="utf-8")
    b = parent / "b.txt"
    b.write_text("hello b " * 20, encoding="utf-8")

    archive_path = tmp_path / "bundle.zip"
    CompressService().compress([a, b], archive_path)

    base_destination = tmp_path / "extracted"
    ExtractService().smart_extract(archive_path, base_destination)

    wrapped_folder = base_destination / "bundle"
    assert (wrapped_folder / "a.txt").read_text(encoding="utf-8") == "hello a"
    assert (wrapped_folder / "b.txt").read_text(encoding="utf-8") == "hello b " * 20
