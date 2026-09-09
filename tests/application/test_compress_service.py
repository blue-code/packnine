"""CompressService 테스트."""
from __future__ import annotations

import pathlib

import pytest

from packnine.application.compress_service import CompressService
from packnine.domain.entities import ArchiveManifest
from packnine.domain.exceptions import UnsupportedFormatError
from packnine.domain.value_objects import CompressionLevel
from tests.infrastructure.conftest import make_sample_source_tree


def _expected_entry_count(src_dir: pathlib.Path) -> int:
    # add_files는 소스 디렉터리 자체(src.name/)를 루트로 담으므로,
    # 그 하위 파일/디렉터리 전부가 아카이브 엔트리가 된다는 점은 각 어댑터 구현에 맡기고
    # 여기서는 "최소 파일 3개(a.txt, b.txt, sub/c.txt)는 포함되어야 한다"만 검증한다.
    return len([p for p in src_dir.rglob("*") if p.is_file()])


@pytest.mark.parametrize("suffix", [".zip", ".7z"])
def test_compress_creates_archive_and_returns_manifest(tmp_path: pathlib.Path, suffix: str) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    destination = tmp_path / f"out{suffix}"
    service = CompressService()

    manifest = service.compress([src_dir], destination)

    assert destination.exists()
    assert isinstance(manifest, ArchiveManifest)
    assert manifest.format_name == suffix
    # 최소한 파일 3개(a.txt, b.txt, sub/c.txt)가 엔트리로 포함되어야 한다.
    file_entry_names = [e.name for e in manifest.entries if not e.is_dir]
    assert len(file_entry_names) >= _expected_entry_count(src_dir)


def test_compress_with_progress_callback_invoked(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    destination = tmp_path / "out.zip"
    service = CompressService()

    calls: list[tuple[str, int, int]] = []

    def on_progress(name: str, done: int, total: int) -> None:
        calls.append((name, done, total))

    service.compress([src_dir], destination, on_progress=on_progress)

    assert len(calls) > 0
    # 마지막 콜백은 done == total 이어야 한다.
    last_name, last_done, last_total = calls[-1]
    assert last_done == last_total


def test_compress_missing_source_raises_file_not_found(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "does_not_exist.txt"
    destination = tmp_path / "out.zip"
    service = CompressService()

    with pytest.raises(FileNotFoundError):
        service.compress([missing], destination)

    assert not destination.exists()


def test_compress_creates_missing_destination_directory(tmp_path: pathlib.Path) -> None:
    # 우클릭 "PackNine으로 압축하기"에서 --dest-dir이 아직 없는 폴더를 가리키면
    # FileNotFoundError로 죽는 문제가 있었다. 해제(extract)는 대상 폴더를 자동
    # 생성하므로 압축도 동일하게 출력 폴더를 만들어 주는 것이 일관된 동작이다.
    src_dir = make_sample_source_tree(tmp_path)
    destination = tmp_path / "not_yet" / "deep" / "out.zip"
    service = CompressService()

    manifest = service.compress([src_dir], destination)

    assert destination.exists()
    assert isinstance(manifest, ArchiveManifest)


def test_compress_missing_source_does_not_create_destination_directory(
    tmp_path: pathlib.Path,
) -> None:
    # 소스 검증 실패 시에는 부수 효과(빈 출력 폴더 생성)도 없어야 한다.
    missing = tmp_path / "does_not_exist.txt"
    destination = tmp_path / "not_yet" / "out.zip"
    service = CompressService()

    with pytest.raises(FileNotFoundError):
        service.compress([missing], destination)

    assert not destination.parent.exists()


def test_compress_rar_destination_raises_unsupported_format(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    destination = tmp_path / "out.rar"
    service = CompressService()

    with pytest.raises(UnsupportedFormatError):
        service.compress([src_dir], destination)


def test_compress_accepts_compression_level(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    destination = tmp_path / "out.zip"
    service = CompressService()

    manifest = service.compress(
        [src_dir], destination, compression_level=CompressionLevel.MAXIMUM
    )

    assert destination.exists()
    assert isinstance(manifest, ArchiveManifest)


def test_smart_compress_single_folder_names_archive_after_folder(tmp_path: pathlib.Path) -> None:
    src_dir = make_sample_source_tree(tmp_path, name="myphotos")
    service = CompressService()

    manifest = service.smart_compress([src_dir])

    expected_destination = tmp_path / "myphotos.zip"
    assert expected_destination.exists()
    assert isinstance(manifest, ArchiveManifest)
    file_entry_names = [e.name for e in manifest.entries if not e.is_dir]
    assert len(file_entry_names) >= _expected_entry_count(src_dir)


def test_smart_compress_multiple_files_names_archive_after_common_parent(
    tmp_path: pathlib.Path,
) -> None:
    parent = tmp_path / "myfolder"
    parent.mkdir()
    a = parent / "a.txt"
    a.write_text("hello a", encoding="utf-8")
    b = parent / "b.txt"
    b.write_text("hello b " * 20, encoding="utf-8")
    service = CompressService()

    manifest = service.smart_compress([a, b])

    expected_destination = parent / "myfolder.zip"
    assert expected_destination.exists()
    file_entry_names = {e.name for e in manifest.entries if not e.is_dir}
    assert {"a.txt", "b.txt"} <= file_entry_names


class TestSplitCompress:
    def _incompressible_source(self, tmp_path: pathlib.Path) -> pathlib.Path:
        import os

        src = tmp_path / "blob"
        src.mkdir()
        (src / "data.bin").write_bytes(os.urandom(300_000))
        return src

    @pytest.mark.parametrize("suffix", [".zip", ".7z"])
    def test_volume_size_splits_and_manifest_points_to_first_volume(
        self, tmp_path: pathlib.Path, suffix: str
    ) -> None:
        from packnine.domain.value_objects import VolumeSize

        src = self._incompressible_source(tmp_path)
        destination = tmp_path / f"out{suffix}"

        manifest = CompressService().compress(
            [src], destination, volume_size=VolumeSize(bytes=100_000)
        )

        assert manifest.volume_count >= 3
        assert manifest.archive_path == destination.with_name(f"out{suffix}.001")
        assert manifest.format_name == suffix
        assert not destination.exists()

    def test_small_result_is_written_as_plain_archive(self, tmp_path: pathlib.Path) -> None:
        from packnine.domain.value_objects import VolumeSize

        src_dir = make_sample_source_tree(tmp_path)
        destination = tmp_path / "out.zip"

        manifest = CompressService().compress(
            [src_dir], destination, volume_size=VolumeSize.from_megabytes(10)
        )

        assert manifest.volume_count == 1
        assert manifest.archive_path == destination
        assert destination.exists()

    def test_without_volume_size_manifest_reports_single_volume(self, tmp_path: pathlib.Path) -> None:
        src_dir = make_sample_source_tree(tmp_path)
        destination = tmp_path / "out.zip"

        manifest = CompressService().compress([src_dir], destination)

        assert manifest.volume_count == 1
        assert manifest.archive_path == destination

    def test_tar_with_volume_size_is_rejected_before_writing(self, tmp_path: pathlib.Path) -> None:
        from packnine.domain.value_objects import VolumeSize

        src_dir = make_sample_source_tree(tmp_path)
        destination = tmp_path / "out.tar.gz"

        with pytest.raises(UnsupportedFormatError):
            CompressService().compress(
                [src_dir], destination, volume_size=VolumeSize.from_megabytes(1)
            )
        assert not destination.exists()

    def test_split_archive_extracts_from_first_volume(self, tmp_path: pathlib.Path) -> None:
        from packnine.application.extract_service import ExtractService
        from packnine.domain.value_objects import VolumeSize
        from tests.infrastructure.conftest import assert_tree_equal

        src = self._incompressible_source(tmp_path)
        manifest = CompressService().compress(
            [src], tmp_path / "out.7z", volume_size=VolumeSize(bytes=100_000)
        )

        dest = tmp_path / "extracted"
        ExtractService().extract(manifest.archive_path, dest)

        assert_tree_equal(src, dest / "blob")
