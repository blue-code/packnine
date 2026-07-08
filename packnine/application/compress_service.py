"""압축 유스케이스 오케스트레이션.

application 계층은 domain의 포트(interfaces)만 알고, 실제 구현체는
format_registry를 통해서만 얻는다(개별 어댑터 클래스를 직접 import하지 않는다).
"""
from __future__ import annotations

import pathlib

from packnine.application import smart_naming
from packnine.domain.entities import ArchiveManifest
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.value_objects import CompressionLevel
from packnine.infrastructure import format_registry


class CompressService:
    """여러 소스 경로를 하나의 아카이브로 압축하는 유스케이스."""

    def compress(
        self,
        source_paths: list[pathlib.Path],
        destination: pathlib.Path,
        *,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        destination = pathlib.Path(destination)

        # writer를 만들기(=대상 파일을 여는 시점) 전에 소스 존재 여부를 먼저 검증한다.
        # 그래야 존재하지 않는 소스로 인해 빈 아카이브 파일이 생성되는 일이 없다.
        for source_path in source_paths:
            if not pathlib.Path(source_path).exists():
                raise FileNotFoundError(f"압축할 소스 경로가 존재하지 않습니다: {source_path}")

        # RAR 확장자면 get_writer가 UnsupportedFormatError를 던지며,
        # 여기서는 그대로 전파시킨다(RAR 쓰기는 라이선스상 미지원).
        writer = format_registry.get_writer(
            destination, password=password, compression_level=compression_level
        )
        writer.add_files(list(source_paths), on_progress=on_progress)
        writer.close()

        # 호출자가 결과를 바로 요약할 수 있도록, 방금 만든 아카이브를 다시 열어 목록을 읽는다.
        reader = format_registry.get_reader(destination, password=password)
        try:
            entries = reader.list_entries()
        finally:
            reader.close()

        return ArchiveManifest(entries=entries, format_name=destination.suffix)

    def smart_compress(
        self,
        source_paths: list[pathlib.Path],
        *,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        """반디집 "알아서 압축"처럼 목적지 경로를 자동으로 정해 바로 압축한다.

        목적지 이름 결정 규칙은 smart_naming에 위임하고, 실제 압축은 기존 compress()를
        그대로 재사용한다(로직 중복 금지).
        """
        destination = smart_naming.resolve_smart_compress_destination(source_paths)
        return self.compress(
            source_paths,
            destination,
            password=password,
            compression_level=compression_level,
            on_progress=on_progress,
        )
