"""sevenzip_adapter.py 에 대한 TDD 테스트 (RED 단계에서 먼저 작성).

py7zr 기반 어댑터의 round-trip(무암호/암호 포함)과, 인프라 계층에서도
ArchiveSecurityPolicy가 실제로 작동하는지(Zip Slip류 방어)를 검증한다.
"""
from __future__ import annotations

import pathlib

import py7zr
import pytest

from packnine.domain.exceptions import InvalidPasswordError, UnsafeArchiveEntryError
from packnine.infrastructure.sevenzip_adapter import (
    SevenZipArchiveReader,
    SevenZipArchiveWriter,
)
from tests.infrastructure.conftest import assert_tree_equal, make_sample_source_tree


class TestSevenZipRoundTrip:
    def test_round_trip_without_password(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "out.7z"

        writer = SevenZipArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        reader = SevenZipArchiveReader(archive_path)
        entries = reader.list_entries()
        assert len(entries) > 0
        names = {e.name.replace("\\", "/") for e in entries}
        assert "source/a.txt" in names
        assert "source/sub/c.txt" in names

        dest = tmp_path / "extracted"
        reader.extract_all(dest)
        reader.close()

        assert_tree_equal(src, dest / "source")

    def test_round_trip_with_password_uses_real_aes256_encryption(self, tmp_path: pathlib.Path):
        # py7zr은 header_encryption=True로 진짜 AES-256 암호화를 지원한다.
        src = make_sample_source_tree(tmp_path, name="secure_source")
        archive_path = tmp_path / "secure.7z"

        writer = SevenZipArchiveWriter(archive_path, password="s3cr3t!")
        writer.add_files([src])
        writer.close()

        # 잘못된 비밀번호(또는 비밀번호 없음)로는 열리지 않아야 한다.
        with pytest.raises(Exception):
            bad_reader = py7zr.SevenZipFile(archive_path, mode="r", password="wrong-password")
            bad_reader.extractall(path=tmp_path / "should_not_extract")

        reader = SevenZipArchiveReader(archive_path, password="s3cr3t!")
        entries = reader.list_entries()
        assert len(entries) > 0

        dest = tmp_path / "extracted_secure"
        reader.extract_all(dest)
        reader.close()

        assert_tree_equal(src, dest / "secure_source")


class TestSevenZipPasswordErrors:
    def _make_encrypted_archive(self, tmp_path: pathlib.Path) -> pathlib.Path:
        src = make_sample_source_tree(tmp_path, name="secure_source")
        archive_path = tmp_path / "secure.7z"
        writer = SevenZipArchiveWriter(archive_path, password="s3cr3t!")
        writer.add_files([src])
        writer.close()
        return archive_path

    def test_wrong_password_raises_invalid_password_error(self, tmp_path: pathlib.Path):
        # py7zr은 헤더 암호화된 7z를 틀린 암호로 열면 깨진 헤더를 읽다가 TypeError 같은
        # 내부 예외를 그대로 던진다. 사용자에게는 "비밀번호가 틀렸다"로 보여야 하므로
        # 어댑터가 도메인 예외(InvalidPasswordError)로 변환해야 한다.
        archive_path = self._make_encrypted_archive(tmp_path)

        with pytest.raises(InvalidPasswordError):
            reader = SevenZipArchiveReader(archive_path, password="wrong-password")
            reader.extract_all(tmp_path / "should_not_extract")

    def test_missing_password_raises_invalid_password_error(self, tmp_path: pathlib.Path):
        archive_path = self._make_encrypted_archive(tmp_path)

        with pytest.raises(InvalidPasswordError):
            reader = SevenZipArchiveReader(archive_path)
            reader.list_entries()


class TestSevenZipProgressCallback:
    def test_extract_all_calls_progress_callback(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "progress.7z"

        writer = SevenZipArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        calls: list[tuple[str, int, int]] = []

        def on_progress(name: str, done: int, total: int) -> None:
            calls.append((name, done, total))

        reader = SevenZipArchiveReader(archive_path)
        reader.extract_all(tmp_path / "extracted_progress", on_progress=on_progress)
        reader.close()

        assert len(calls) > 0


class TestSevenZipSecurityRegression:
    def test_extract_all_rejects_path_traversal_and_writes_nothing(self, tmp_path: pathlib.Path):
        # py7zr의 write()는 절대경로만 막고 '..' 상대경로는 그대로 허용하므로
        # 악성 아카이브를 직접 만들 수 있다.
        payload = tmp_path / "payload.txt"
        payload.write_text("evil content", encoding="utf-8")

        malicious_path = tmp_path / "evil.7z"
        with py7zr.SevenZipFile(malicious_path, mode="w") as z:
            z.write(payload, arcname="../evil.txt")

        dest = tmp_path / "extract_here"
        reader = SevenZipArchiveReader(malicious_path)
        with pytest.raises(UnsafeArchiveEntryError):
            reader.extract_all(dest)
        reader.close()

        assert not dest.exists()
        assert not (tmp_path / "evil.txt").exists()
