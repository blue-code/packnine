"""도메인 엔티티 모음. 외부 압축 라이브러리에 의존하지 않는다."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass


@dataclass
class ArchiveEntry:
    """아카이브 내부의 파일/디렉터리 한 항목."""

    name: str  # 아카이브 내부 경로, '/' 구분자로 정규화된 값
    size: int  # 압축해제 후 크기 (bytes)
    compressed_size: int
    is_dir: bool = False
    is_symlink: bool = False
    modified_at: float | None = None

    @property
    def compression_ratio(self) -> float:
        # compressed_size가 0이면 0으로 나누기가 발생하므로 max(compressed_size, 1)로 방지
        return self.size / max(self.compressed_size, 1)


@dataclass
class ArchiveManifest:
    """아카이브 전체 목록 정보."""

    entries: list[ArchiveEntry]
    format_name: str
    # 분할 압축 결과를 호출자가 알 수 있도록 남기는 메타 정보. 압축 결과가 볼륨 하나에
    # 들어가면 .001 없이 저장되므로, 사용자가 지정한 경로와 실제 파일 경로가 다를 수 있다.
    archive_path: pathlib.Path | None = None
    volume_count: int = 1

    @property
    def total_uncompressed_size(self) -> int:
        return sum(entry.size for entry in self.entries)

    @property
    def total_compressed_size(self) -> int:
        return sum(entry.compressed_size for entry in self.entries)
