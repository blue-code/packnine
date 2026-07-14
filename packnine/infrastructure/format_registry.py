"""확장자 -> 포맷 어댑터 매핑 레지스트리.

application 계층은 이 모듈의 get_reader/get_writer만 알면 되고,
개별 어댑터 클래스를 직접 import할 필요가 없다(계층 경계 유지).
"""
from __future__ import annotations

import pathlib

from packnine.domain.exceptions import UnsupportedFormatError
from packnine.domain.value_objects import CompressionLevel
from packnine.infrastructure.rar_adapter import RarArchiveReader
from packnine.infrastructure.sevenzip_adapter import (
    SevenZipArchiveReader,
    SevenZipArchiveWriter,
)
from packnine.infrastructure.singlefile_adapter import SingleFileArchiveReader
from packnine.infrastructure.tar_adapter import TarArchiveReader, TarArchiveWriter
from packnine.infrastructure.zip_adapter import ZipArchiveReader, ZipArchiveWriter

# .tar.gz 같은 복합 확장자를 .gz보다 먼저 매칭해야 하므로 순서가 중요하다.
_SUPPORTED_EXTENSIONS = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tgz",
    ".tar",
    ".zip",
    ".7z",
    ".rar",
    # 복합(.tar.*)에 해당하지 않는 순수 단일 파일 압축 - 반드시 tar 계열 뒤에 둔다.
    ".gz",
    ".bz2",
    ".xz",
)

_READER_CLASSES: dict[str, type] = {
    ".zip": ZipArchiveReader,
    ".7z": SevenZipArchiveReader,
    ".tar": TarArchiveReader,
    ".tar.gz": TarArchiveReader,
    ".tgz": TarArchiveReader,
    ".tar.bz2": TarArchiveReader,
    ".tar.xz": TarArchiveReader,
    ".rar": RarArchiveReader,
    ".gz": SingleFileArchiveReader,
    ".bz2": SingleFileArchiveReader,
    ".xz": SingleFileArchiveReader,
}

_WRITER_CLASSES: dict[str, type] = {
    ".zip": ZipArchiveWriter,
    ".7z": SevenZipArchiveWriter,
    ".tar": TarArchiveWriter,
    ".tar.gz": TarArchiveWriter,
    ".tgz": TarArchiveWriter,
    ".tar.bz2": TarArchiveWriter,
    ".tar.xz": TarArchiveWriter,
    # .rar는 의도적으로 제외 - RAR 쓰기는 라이선스상 미지원(get_writer에서 명시적으로 거부)
}


def _resolve_extension(path: pathlib.Path) -> str:
    name = path.name.lower()
    for ext in _SUPPORTED_EXTENSIONS:
        if name.endswith(ext):
            return ext
    raise UnsupportedFormatError(f"지원하지 않는 압축 확장자입니다: {path.name}")


def get_reader(path: pathlib.Path, password: str | None = None):
    """확장자에 맞는 ArchiveReader 어댑터 인스턴스를 반환한다."""
    path = pathlib.Path(path)
    ext = _resolve_extension(path)
    reader_cls = _READER_CLASSES[ext]
    return reader_cls(path, password=password)


def get_writer(
    path: pathlib.Path,
    password: str | None = None,
    compression_level: CompressionLevel = CompressionLevel.NORMAL,
):
    """확장자에 맞는 ArchiveWriter 어댑터 인스턴스를 반환한다.

    RAR 확장자로 쓰기를 요청하면 UnsupportedFormatError를 던진다
    (RAR 압축은 라이선스상 지원하지 않음. rar_adapter.RarArchiveWriter는
    실수 방지를 위한 안내용일 뿐 정상 사용 경로가 아니다).
    """
    path = pathlib.Path(path)
    ext = _resolve_extension(path)
    if ext == ".rar":
        raise UnsupportedFormatError("RAR 포맷으로의 쓰기는 지원하지 않습니다 (라이선스 제약)")
    if ext not in _WRITER_CLASSES:
        raise UnsupportedFormatError(
            f"{ext} 포맷으로의 압축은 지원하지 않습니다 (해제 전용). ZIP/7Z/TAR를 사용하세요."
        )
    writer_cls = _WRITER_CLASSES[ext]
    return writer_cls(path, password=password, compression_level=compression_level)
