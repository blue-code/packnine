"""zip_adapter.py 에 대한 TDD 테스트 (RED 단계에서 먼저 작성).

표준 zipfile 기반 어댑터의 round-trip, 진행률 콜백, 그리고
보안 정책(ArchiveSecurityPolicy)이 인프라 계층에서도 실제로 작동하는지를 검증한다.
"""
from __future__ import annotations

import pathlib
import zipfile

import pytest

from packnine.domain.exceptions import (
    CorruptedArchiveError,
    InvalidPasswordError,
    UnsafeArchiveEntryError,
)
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
        # pyzipper 기반 AES-256 암호화 zip의 round-trip. 과거에는 표준 zipfile의 한계로
        # password를 받아놓고 조용히 무시했는데(사용자는 암호가 걸렸다고 믿는 최악의 동작),
        # pyzipper 도입으로 진짜 암호화를 적용한다.
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

    def test_password_zip_is_really_encrypted(self, tmp_path: pathlib.Path):
        # 암호를 지정해 만든 zip은 틀린 암호/무암호로는 내용물을 꺼낼 수 없어야 한다.
        src = make_sample_source_tree(tmp_path, name="secure_source")
        archive_path = tmp_path / "really_secure.zip"

        writer = ZipArchiveWriter(archive_path, password="s3cr3t!")
        writer.add_files([src])
        writer.close()

        for bad_password in ("wrong-password", None):
            reader = ZipArchiveReader(archive_path, password=bad_password)
            dest = tmp_path / f"should_fail_{bad_password}"
            with pytest.raises(InvalidPasswordError):
                reader.extract_all(dest)
            reader.close()
            # 암호가 틀렸으면 파일이 하나라도 평문으로 남으면 안 된다.
            assert not any(dest.rglob("*")) if dest.exists() else True

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


class _Cp949ZipInfo(zipfile.ZipInfo):
    """UTF-8 플래그 없이 cp949 바이트로 파일명을 기록하는 레거시 zip 재현용.

    표준 zipfile은 비ASCII 이름을 쓰면 무조건 UTF-8 플래그를 세우므로, 알집/구형
    도구가 만드는 "cp949 바이트 + 플래그 없음" zip은 내부 인코딩 훅을 오버라이드해야만
    테스트에서 재현할 수 있다(비공개 API지만 테스트 전용이라 허용).
    """

    def _encodeFilenameFlags(self):  # noqa: N802 - zipfile 내부 훅 이름 유지
        return self.filename.encode("cp949"), self.flag_bits


class TestZipLegacyKoreanFilenames:
    def _make_legacy_zip(self, tmp_path: pathlib.Path) -> pathlib.Path:
        archive_path = tmp_path / "legacy.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            info = _Cp949ZipInfo("한글폴더/보고서.txt")
            zf.writestr(info, "내용".encode("utf-8"))
        return archive_path

    def test_list_entries_decodes_cp949_names(self, tmp_path: pathlib.Path):
        # 알집 등이 만든 레거시 zip은 파일명이 cp949 바이트인데, zipfile이 cp437로
        # 잘못 디코딩해 한글이 깨진다. 반디집처럼 자동 감지해서 복원해야 한다.
        archive_path = self._make_legacy_zip(tmp_path)

        reader = ZipArchiveReader(archive_path)
        names = {e.name for e in reader.list_entries()}
        reader.close()

        assert "한글폴더/보고서.txt" in names

    def test_extract_all_writes_decoded_korean_paths(self, tmp_path: pathlib.Path):
        archive_path = self._make_legacy_zip(tmp_path)
        dest = tmp_path / "extracted"

        reader = ZipArchiveReader(archive_path)
        reader.extract_all(dest)
        reader.close()

        target = dest / "한글폴더" / "보고서.txt"
        assert target.read_text(encoding="utf-8") == "내용"

    def test_utf8_flagged_names_are_untouched(self, tmp_path: pathlib.Path):
        # 정상 UTF-8 zip(플래그 있음)은 재판별 대상이 아니어야 한다(회귀 방지).
        archive_path = tmp_path / "utf8.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("한글.txt", "ok")

        reader = ZipArchiveReader(archive_path)
        names = {e.name for e in reader.list_entries()}
        reader.close()

        assert names == {"한글.txt"}


class TestZipCorruptedArchive:
    def test_corrupted_zip_raises_corrupted_archive_error(self, tmp_path: pathlib.Path):
        # 라이브러리 예외(BadZipFile)가 그대로 새어 나가면 CLI가 traceback을 뿜는다.
        # 어댑터가 도메인 예외로 변환해야 presentation 계층이 일관되게 안내할 수 있다.
        broken = tmp_path / "broken.zip"
        broken.write_bytes(b"PK\x03\x04" + b"\x00" * 32)

        with pytest.raises(CorruptedArchiveError):
            ZipArchiveReader(broken)


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


class TestZipVolumes:
    def _make_incompressible_source(self, tmp_path: pathlib.Path) -> pathlib.Path:
        # 랜덤 바이트는 압축되지 않으므로 볼륨 크기 계산이 예측 가능하다.
        import os

        src = tmp_path / "blob"
        src.mkdir()
        (src / "data.bin").write_bytes(os.urandom(300_000))
        return src

    def test_split_round_trip_creates_three_digit_volumes(self, tmp_path: pathlib.Path):
        from packnine.domain.value_objects import VolumeSize

        src = self._make_incompressible_source(tmp_path)
        archive_path = tmp_path / "out.zip"

        writer = ZipArchiveWriter(archive_path, volume_size=VolumeSize(bytes=100_000))
        writer.add_files([src])
        writer.close()

        assert not archive_path.exists()
        volumes = sorted(p.name for p in tmp_path.glob("out.zip.*"))
        assert volumes[:2] == ["out.zip.001", "out.zip.002"]
        assert writer.output_path == archive_path.with_name("out.zip.001")
        assert writer.volume_count == len(volumes)

        reader = ZipArchiveReader(writer.output_path)
        dest = tmp_path / "extracted"
        reader.extract_all(dest)
        reader.close()
        assert_tree_equal(src, dest / "blob")

    def test_single_volume_result_drops_001_suffix(self, tmp_path: pathlib.Path):
        from packnine.domain.value_objects import VolumeSize

        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "out.zip"

        writer = ZipArchiveWriter(archive_path, volume_size=VolumeSize.from_megabytes(10))
        writer.add_files([src])
        writer.close()

        assert archive_path.exists()
        assert list(tmp_path.glob("out.zip.*")) == []
        assert writer.output_path == archive_path
        assert writer.volume_count == 1

        reader = ZipArchiveReader(archive_path)
        assert {e.name for e in reader.list_entries()} >= {"source/a.txt"}
        reader.close()

    def test_split_with_password_round_trip(self, tmp_path: pathlib.Path):
        from packnine.domain.value_objects import VolumeSize

        src = self._make_incompressible_source(tmp_path)
        archive_path = tmp_path / "secret.zip"

        writer = ZipArchiveWriter(
            archive_path, password="pw", volume_size=VolumeSize(bytes=100_000)
        )
        writer.add_files([src])
        writer.close()

        reader = ZipArchiveReader(writer.output_path, password="pw")
        dest = tmp_path / "extracted"
        reader.extract_all(dest)
        reader.close()
        assert_tree_equal(src, dest / "blob")

    def test_missing_later_volume_raises_corrupted(self, tmp_path: pathlib.Path):
        from packnine.domain.value_objects import VolumeSize

        src = self._make_incompressible_source(tmp_path)
        archive_path = tmp_path / "out.zip"
        writer = ZipArchiveWriter(archive_path, volume_size=VolumeSize(bytes=100_000))
        writer.add_files([src])
        writer.close()
        # 마지막 볼륨(중앙 디렉터리가 들어 있는 조각)을 지우면 zip으로 열 수 없어야 한다.
        sorted(tmp_path.glob("out.zip.*"))[-1].unlink()

        with pytest.raises(CorruptedArchiveError):
            ZipArchiveReader(writer.output_path)
