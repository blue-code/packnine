"""singlefile_adapter.py 에 대한 TDD 테스트 (RED 단계에서 먼저 작성).

tar가 아닌 순수 단일 파일 압축(.gz/.bz2/.xz)의 해제를 검증한다.
반디집은 이런 파일도 기본으로 풀어주므로 PackNine도 지원해야 한다.
"""
from __future__ import annotations

import bz2
import gzip
import lzma
import pathlib

import pytest

from packnine.domain.exceptions import UnsafeArchiveEntryError
from packnine.infrastructure.singlefile_adapter import SingleFileArchiveReader

_COMPRESSORS = {
    ".gz": gzip.compress,
    ".bz2": bz2.compress,
    ".xz": lzma.compress,
}


@pytest.mark.parametrize("suffix", [".gz", ".bz2", ".xz"])
class TestSingleFileRoundTrip:
    def _make_archive(self, tmp_path: pathlib.Path, suffix: str) -> pathlib.Path:
        payload = "단일 파일 압축 내용\n" * 10
        archive_path = tmp_path / f"notes.txt{suffix}"
        archive_path.write_bytes(_COMPRESSORS[suffix](payload.encode("utf-8")))
        return archive_path

    def test_list_entries_returns_inner_filename(self, tmp_path: pathlib.Path, suffix: str):
        archive_path = self._make_archive(tmp_path, suffix)

        reader = SingleFileArchiveReader(archive_path)
        entries = reader.list_entries()
        reader.close()

        # 확장자만 벗긴 이름(notes.txt) 하나가 유일한 엔트리여야 한다.
        assert len(entries) == 1
        assert entries[0].name == "notes.txt"
        assert entries[0].is_dir is False

    def test_extract_all_restores_content(self, tmp_path: pathlib.Path, suffix: str):
        archive_path = self._make_archive(tmp_path, suffix)
        dest = tmp_path / "out"

        reader = SingleFileArchiveReader(archive_path)
        reader.extract_all(dest)
        reader.close()

        restored = (dest / "notes.txt").read_text(encoding="utf-8")
        assert restored == "단일 파일 압축 내용\n" * 10

    def test_extract_all_reports_progress(self, tmp_path: pathlib.Path, suffix: str):
        archive_path = self._make_archive(tmp_path, suffix)
        calls: list[tuple[str, int, int]] = []

        reader = SingleFileArchiveReader(archive_path)
        reader.extract_all(tmp_path / "out2", on_progress=lambda n, d, t: calls.append((n, d, t)))
        reader.close()

        assert calls
        assert calls[-1][1] == calls[-1][2]


class TestSingleFileBombDefense:
    def test_decompression_bomb_is_blocked_during_streaming(self, tmp_path: pathlib.Path):
        # gzip 헤더의 원본 크기(ISIZE)는 32비트 모듈러 값이라 신뢰할 수 없으므로,
        # 해제 스트리밍 중 실제 쓰인 바이트가 압축 크기 대비 상한을 넘으면 중단해야 한다.
        bomb_payload = b"\x00" * (200 * 1024 * 1024)  # 200MB의 0 -> gz로 수백 KB
        archive_path = tmp_path / "bomb.gz"
        archive_path.write_bytes(gzip.compress(bomb_payload, compresslevel=9))

        reader = SingleFileArchiveReader(archive_path)
        with pytest.raises(UnsafeArchiveEntryError):
            reader.extract_all(tmp_path / "bomb_out")
        reader.close()
