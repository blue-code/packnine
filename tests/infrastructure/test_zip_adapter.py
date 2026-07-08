"""zip_adapter.py 에 대한 TDD 테스트 (RED 단계에서 먼저 작성).

표준 zipfile 기반 어댑터의 round-trip, 진행률 콜백, 그리고
보안 정책(ArchiveSecurityPolicy)이 인프라 계층에서도 실제로 작동하는지를 검증한다.
"""
from __future__ import annotations

import pathlib
import zipfile

import pytest

from packnine.domain.exceptions import UnsafeArchiveEntryError
from packnine.domain.value_objects import CompressionLevel
from packnine.infrastructure.zip_adapter import ZipArchiveReader, ZipArchiveWriter
from tests.infrastructure.conftest import assert_tree_equal, make_sample_source_tree


class TestZipRoundTrip:
    def test_round_trip_without_password(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "out.zip"

        writer = ZipArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        reader = ZipArchiveReader(archive_path)
        entries = reader.list_entries()
        assert len(entries) > 0
        names = {e.name for e in entries}
        assert "source/a.txt" in names
        assert "source/sub/c.txt" in names

        dest = tmp_path / "extracted"
        reader.extract_all(dest)
        reader.close()

        assert_tree_equal(src, dest / "source")

    def test_round_trip_with_store_level(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "store.zip"

        writer = ZipArchiveWriter(archive_path, compression_level=CompressionLevel.STORE)
        writer.add_files([src])
        writer.close()

        reader = ZipArchiveReader(archive_path)
        dest = tmp_path / "extracted_store"
        reader.extract_all(dest)
        reader.close()

        assert_tree_equal(src, dest / "source")

    def test_round_trip_with_password(self, tmp_path: pathlib.Path):
        # 참고: 표준 zipfile은 쓰기 시 실제 암호화(AES)를 지원하지 않는다(WHY: zip_adapter.py 주석 참고).
        # 진짜 AES256 암호화는 7z 어댑터가 담당하므로, 여기서는 password 인자를 넘겨도
        # 압축 자체가 정상 동작하고 read-back이 되는지만 검증한다.
        src = make_sample_source_tree(tmp_path, name="secure_source")
        archive_path = tmp_path / "secure.zip"

        writer = ZipArchiveWriter(archive_path, password="s3cr3t!")
        writer.add_files([src])
        writer.close()

        reader = ZipArchiveReader(archive_path, password="s3cr3t!")
        entries = reader.list_entries()
        assert len(entries) > 0

        dest = tmp_path / "extracted_secure"
        reader.extract_all(dest)
        reader.close()

        assert_tree_equal(src, dest / "secure_source")

    def test_extract_one_extracts_single_entry(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "one.zip"

        writer = ZipArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        reader = ZipArchiveReader(archive_path)
        dest = tmp_path / "extracted_one"
        reader.extract_one("source/a.txt", dest)
        reader.close()

        assert (dest / "source" / "a.txt").read_text(encoding="utf-8") == "hello a"
        assert not (dest / "source" / "b.txt").exists()


class TestZipProgressCallback:
    def test_extract_all_calls_progress_callback(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "progress.zip"

        writer = ZipArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        calls: list[tuple[str, int, int]] = []

        def on_progress(name: str, done: int, total: int) -> None:
            calls.append((name, done, total))

        reader = ZipArchiveReader(archive_path)
        reader.extract_all(tmp_path / "extracted_progress", on_progress=on_progress)
        reader.close()

        assert len(calls) > 0
        last_name, last_done, last_total = calls[-1]
        assert last_done == last_total
        assert last_total == len(calls)

    def test_add_files_calls_progress_callback(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "write_progress.zip"

        calls: list[tuple[str, int, int]] = []

        def on_progress(name: str, done: int, total: int) -> None:
            calls.append((name, done, total))

        writer = ZipArchiveWriter(archive_path)
        writer.add_files([src], on_progress=on_progress)
        writer.close()

        assert len(calls) > 0


class TestZipSecurityRegression:
    def test_extract_all_rejects_zip_slip_and_writes_nothing(self, tmp_path: pathlib.Path):
        # zipfile을 직접 사용해 '../evil.txt' 라는 악성 엔트리를 가진 zip을 만든다.
        malicious_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(malicious_path, "w") as zf:
            zf.writestr("safe.txt", "safe content")
            zf.writestr("../evil.txt", "evil content")

        dest = tmp_path / "extract_here"
        reader = ZipArchiveReader(malicious_path)
        with pytest.raises(UnsafeArchiveEntryError):
            reader.extract_all(dest)
        reader.close()

        # all-or-nothing: 목적지 디렉터리 자체가 생성되지 않아야 하고,
        # dest.parent(=tmp_path) 밖으로 유출된 evil.txt도 없어야 한다.
        assert not dest.exists()
        assert not (tmp_path / "evil.txt").exists()

    def test_extract_one_rejects_zip_slip(self, tmp_path: pathlib.Path):
        malicious_path = tmp_path / "evil_one.zip"
        with zipfile.ZipFile(malicious_path, "w") as zf:
            zf.writestr("../../evil.txt", "evil content")

        dest = tmp_path / "extract_here_one"
        reader = ZipArchiveReader(malicious_path)
        with pytest.raises(UnsafeArchiveEntryError):
            reader.extract_one("../../evil.txt", dest)
        reader.close()

        assert not (tmp_path.parent / "evil.txt").exists()
