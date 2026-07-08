"""rar_adapter.py 에 대한 TDD 테스트 (RED 단계에서 먼저 작성).

RAR은 해제 전용이다(라이선스상 압축 미지원). 시스템에 unrar/bsdtar가 없으면
실제 rar 파일을 만들 수 없으므로 round-trip 테스트는 조건부 스킵 처리한다.
외부 도구 부재 시 ExternalToolMissingError를 내는지, 그리고 쓰기 시도 시
RarCompressionNotSupportedError를 내는지는 도구 유무와 무관하게 항상 검증 가능하다.
"""
from __future__ import annotations

import pathlib
import shutil

import pytest

from packnine.domain.exceptions import ExternalToolMissingError
from packnine.infrastructure.rar_adapter import (
    RarArchiveReader,
    RarArchiveWriter,
    RarCompressionNotSupportedError,
)

_HAS_UNRAR_TOOL = shutil.which("unrar") is not None or shutil.which("bsdtar") is not None


class TestRarWriterNotSupported:
    def test_writer_construction_raises_not_supported(self, tmp_path: pathlib.Path):
        with pytest.raises(RarCompressionNotSupportedError):
            RarArchiveWriter(tmp_path / "out.rar")


@pytest.mark.skipif(_HAS_UNRAR_TOOL, reason="unrar/bsdtar가 설치되어 있어 도구 누락 케이스를 재현할 수 없음")
class TestRarExternalToolMissing:
    def test_reader_raises_when_tool_missing(self, tmp_path: pathlib.Path):
        # 실제 rar 파일이 없어도, 생성자에서 외부 도구 존재 여부부터 검사해야 한다.
        with pytest.raises(ExternalToolMissingError) as exc_info:
            RarArchiveReader(tmp_path / "does_not_matter.rar")
        message = str(exc_info.value)
        assert "unrar" in message or "bsdtar" in message


@pytest.mark.skipif(
    not _HAS_UNRAR_TOOL, reason="unrar/bsdtar가 설치되어 있지 않아 RAR round-trip 테스트를 스킵함"
)
class TestRarReaderRoundTrip:
    def test_list_entries_and_extract_existing_rar_fixture(self, tmp_path: pathlib.Path):
        # 순수 파이썬만으로 유효한 rar 아카이브를 생성할 수는 없으므로(rarfile은 해제 전용
        # 라이브러리), 이 테스트는 unrar/bsdtar가 있는 환경에서 fixtures 경로에 있는
        # 샘플 .rar가 있을 때만 의미 있게 동작한다. fixture가 없으면 스킵한다.
        fixture_path = (
            pathlib.Path(__file__).parent.parent / "fixtures" / "sample.rar"
        )
        if not fixture_path.exists():
            pytest.skip("tests/fixtures/sample.rar 없음 - RAR round-trip fixture 미준비")

        reader = RarArchiveReader(fixture_path)
        entries = reader.list_entries()
        assert len(entries) > 0

        dest = tmp_path / "extracted"
        reader.extract_all(dest)
        reader.close()
        assert dest.exists()
