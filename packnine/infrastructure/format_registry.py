"""확장자 -> 포맷 어댑터 매핑 레지스트리.

application 계층은 이 모듈의 get_reader/get_writer만 알면 되고,
개별 어댑터 클래스를 직접 import할 필요가 없다(계층 경계 유지).
"""
from __future__ import annotations

import pathlib

from packnine.domain.exceptions import UnsupportedFormatError
from packnine.domain.file_filter import ExcludeFilter
from packnine.domain.value_objects import CompressionLevel, VolumeSize
from packnine.infrastructure import volume_io
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


# 분할(볼륨) 압축을 지원하는 포맷. tar 계열은 스트림 포맷이라 기술적으로는 가능하지만
# 수요가 없고, RAR은 쓰기 자체가 없다. 어댑터가 multivolumefile을 다루는 것도 이 둘뿐이다.
_VOLUME_CAPABLE_EXTENSIONS = (".zip", ".7z")


def _resolve_extension(path: pathlib.Path) -> str:
    name = path.name.lower()
    if volume_io.is_first_volume(path):
        # `이름.zip.001`은 zip 어댑터가 볼륨 묶음으로 연다. 원래 포맷이 분할 지원 포맷이어야 한다.
        base_ext = _resolve_extension(volume_io.strip_volume_suffix(path))
        if base_ext not in _VOLUME_CAPABLE_EXTENSIONS:
            raise UnsupportedFormatError(
                f"{base_ext} 포맷의 분할 파일은 지원하지 않습니다: {path.name}"
            )
        return base_ext
    if volume_io.strip_volume_suffix(path) != path:
        raise UnsupportedFormatError(
            f"분할 파일은 첫 번째 볼륨(.001)을 열어야 합니다: {path.name}"
        )
    for ext in _SUPPORTED_EXTENSIONS:
        if name.endswith(ext):
            return ext
    raise UnsupportedFormatError(f"지원하지 않는 압축 확장자입니다: {path.name}")


def get_reader(path: pathlib.Path, password: str | None = None):
    """확장자에 맞는 ArchiveReader 어댑터 인스턴스를 반환한다.

    분할 첫 볼륨(.zip.001/.7z.001)도 받는다 - 어댑터가 경로 이름을 보고 볼륨 묶음으로 연다.
    """
    path = pathlib.Path(path)
    ext = _resolve_extension(path)
    reader_cls = _READER_CLASSES[ext]
    return reader_cls(path, password=password)


def get_writer(
    path: pathlib.Path,
    password: str | None = None,
    compression_level: CompressionLevel = CompressionLevel.NORMAL,
    volume_size: VolumeSize | None = None,
    exclude_filter: ExcludeFilter | None = None,
):
    """확장자에 맞는 ArchiveWriter 어댑터 인스턴스를 반환한다.

    RAR 확장자로 쓰기를 요청하면 UnsupportedFormatError를 던진다
    (RAR 압축은 라이선스상 지원하지 않음. rar_adapter.RarArchiveWriter는
    실수 방지를 위한 안내용일 뿐 정상 사용 경로가 아니다).
    volume_size가 주어지면 zip/7z만 허용한다. 출력 경로 자체가 `.001`이면 `.001.001`이
    생기므로 거부한다(분할 여부는 volume_size로만 정한다).
    """
    path = pathlib.Path(path)
    if volume_io.strip_volume_suffix(path) != path:
        raise UnsupportedFormatError(
            f"출력 경로에는 볼륨 번호(.001)를 붙이지 마세요. 분할 크기를 지정하면 자동으로 붙습니다: {path.name}"
        )
    ext = _resolve_extension(path)
    if ext == ".rar":
        raise UnsupportedFormatError("RAR 포맷으로의 쓰기는 지원하지 않습니다 (라이선스 제약)")
    if ext not in _WRITER_CLASSES:
        raise UnsupportedFormatError(
            f"{ext} 포맷으로의 압축은 지원하지 않습니다 (해제 전용). ZIP/7Z/TAR를 사용하세요."
        )
    if volume_size is not None and ext not in _VOLUME_CAPABLE_EXTENSIONS:
        raise UnsupportedFormatError(
            f"{ext} 포맷은 분할 압축을 지원하지 않습니다. ZIP 또는 7Z를 사용하세요."
        )
    writer_cls = _WRITER_CLASSES[ext]
    if volume_size is not None:
        return writer_cls(
            path,
            password=password,
            compression_level=compression_level,
            volume_size=volume_size,
            exclude_filter=exclude_filter,
        )
    return writer_cls(
        path,
        password=password,
        compression_level=compression_level,
        exclude_filter=exclude_filter,
    )
