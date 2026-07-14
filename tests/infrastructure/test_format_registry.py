"""format_registry.py 에 대한 TDD 테스트 (RED 단계에서 먼저 작성).

확장자 -> 어댑터 매핑이 올바른지, 미지원 확장자에서 UnsupportedFormatError가
발생하는지, RAR 확장자로 writer를 요청하면 거부되는지를 검증한다.
"""
from __future__ import annotations

import pathlib

import pytest

from packnine.domain.exceptions import UnsupportedFormatError
from packnine.infrastructure import format_registry
from packnine.infrastructure.rar_adapter import RarArchiveReader
from packnine.infrastructure.sevenzip_adapter import (
    SevenZipArchiveReader,
    SevenZipArchiveWriter,
)
from packnine.infrastructure.tar_adapter import TarArchiveReader, TarArchiveWriter
from packnine.infrastructure.zip_adapter import ZipArchiveReader, ZipArchiveWriter
from tests.infrastructure.conftest import make_sample_source_tree


class TestGetReader:
    @pytest.mark.parametrize(
        "filename, expected_cls",
        [
            ("archive.zip", ZipArchiveReader),
            ("archive.7z", SevenZipArchiveReader),
            ("archive.tar", TarArchiveReader),
            ("archive.tar.gz", TarArchiveReader),
            ("archive.tgz", TarArchiveReader),
            ("archive.tar.bz2", TarArchiveReader),
            ("archive.tar.xz", TarArchiveReader),
            ("archive.rar", RarArchiveReader),
        ],
    )
    def test_maps_extension_to_expected_reader_class(
        self, tmp_path: pathlib.Path, filename: str, expected_cls: type
    ):
        # 실제로 유효한 아카이브가 아니어도, 매핑 로직 자체는 생성자 호출 전에
        # UnsupportedFormatError 를 던지지 않는지 확인할 수 있어야 하므로
        # 실제 존재하는 zip/tar 파일을 만들어 최소한 zip/tar류는 진짜로 열어본다.
        path = tmp_path / filename
        if expected_cls in (ZipArchiveReader, TarArchiveReader, SevenZipArchiveReader):
            src = make_sample_source_tree(tmp_path)
            writer_cls = format_registry._WRITER_CLASSES[format_registry._resolve_extension(path)]
            writer = writer_cls(path)
            writer.add_files([src])
            writer.close()
            reader = format_registry.get_reader(path)
            assert isinstance(reader, expected_cls)
            reader.close()
        else:
            # rar는 실제 아카이브 생성이 불가하므로 클래스 매핑만 검증(도구 없으면 예외가 나되
            # 클래스 자체는 RarArchiveReader여야 함을 별도로 보증하기 위해 매핑 딕셔너리로 확인)
            assert format_registry._READER_CLASSES[format_registry._resolve_extension(path)] is expected_cls


class TestGetWriter:
    @pytest.mark.parametrize(
        "filename, expected_cls",
        [
            ("archive.zip", ZipArchiveWriter),
            ("archive.7z", SevenZipArchiveWriter),
            ("archive.tar", TarArchiveWriter),
            ("archive.tar.gz", TarArchiveWriter),
            ("archive.tgz", TarArchiveWriter),
            ("archive.tar.bz2", TarArchiveWriter),
            ("archive.tar.xz", TarArchiveWriter),
        ],
    )
    def test_maps_extension_to_expected_writer_class(
        self, tmp_path: pathlib.Path, filename: str, expected_cls: type
    ):
        path = tmp_path / filename
        writer = format_registry.get_writer(path)
        assert isinstance(writer, expected_cls)
        writer.close()

    def test_rar_writer_request_raises_unsupported_format(self, tmp_path: pathlib.Path):
        with pytest.raises(UnsupportedFormatError):
            format_registry.get_writer(tmp_path / "archive.rar")


class TestUnsupportedExtension:
    # .gz는 v0.3 이후 단일 파일 해제를 지원하므로 미지원 목록에서 제외되었다.
    @pytest.mark.parametrize("filename", ["archive.txt", "archive.unknown", "noext"])
    def test_unsupported_extension_raises_for_reader(self, tmp_path: pathlib.Path, filename: str):
        with pytest.raises(UnsupportedFormatError):
            format_registry.get_reader(tmp_path / filename)

    # 단일 파일 압축(.gz/.bz2/.xz)은 해제 전용 - 쓰기는 여전히 거부해야 한다.
    @pytest.mark.parametrize(
        "filename", ["archive.txt", "archive.gz", "archive.bz2", "archive.xz", "noext"]
    )
    def test_unsupported_extension_raises_for_writer(self, tmp_path: pathlib.Path, filename: str):
        with pytest.raises(UnsupportedFormatError):
            format_registry.get_writer(tmp_path / filename)

    @pytest.mark.parametrize("suffix", [".gz", ".bz2", ".xz"])
    def test_single_file_extensions_resolve_to_reader(self, tmp_path: pathlib.Path, suffix: str):
        import gzip, bz2, lzma  # noqa: E401 - 테스트 데이터 생성용

        compressor = {".gz": gzip.compress, ".bz2": bz2.compress, ".xz": lzma.compress}[suffix]
        path = tmp_path / f"single{suffix}"
        path.write_bytes(compressor(b"data"))

        reader = format_registry.get_reader(path)
        assert reader.list_entries()[0].name == "single"
        reader.close()
