"""ExtractService 테스트."""
from __future__ import annotations

import pathlib

import pytest

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
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
