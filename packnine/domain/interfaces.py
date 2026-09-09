"""도메인 계층에서 정의하는 포트(Protocol) 모음.

실제 구현(zipfile, py7zr 등 사용)은 infrastructure 계층에서 담당하며,
domain은 이 Protocol에만 의존한다.
"""
from __future__ import annotations

import pathlib
from typing import Callable, Protocol, runtime_checkable

from packnine.domain.entities import ArchiveEntry

# 진행률 콜백: (현재 처리 중인 엔트리 이름, 처리된 바이트/개수, 전체 바이트/개수)
ProgressCallback = Callable[[str, int, int], None]


@runtime_checkable
class ArchiveReader(Protocol):
    """아카이브를 읽어 목록을 조회하거나 압축을 해제하는 포트."""

    def list_entries(self) -> list[ArchiveEntry]:
        ...

    def extract_all(
        self,
        destination: pathlib.Path,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        ...

    def extract_one(self, entry_name: str, destination: pathlib.Path) -> None:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class ArchiveWriter(Protocol):
    """새 아카이브를 생성/추가하는 포트.

    output_path/volume_count는 close() 이후에 확정된다. 분할 압축이면 첫 볼륨 경로와
    볼륨 수가 들어가고, 분할하지 않았거나 결과가 한 조각이면 지정 경로와 1이다.
    """

    output_path: pathlib.Path
    volume_count: int

    def add_files(
        self,
        paths: list[pathlib.Path],
        on_progress: ProgressCallback | None = None,
    ) -> None:
        ...

    def close(self) -> None:
        ...
