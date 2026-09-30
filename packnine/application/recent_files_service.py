"""최근 연 아카이브 목록 유스케이스.

presentation 계층이 infrastructure의 저장 구현을 직접 참조하지 않도록 얇게 감싼다
(계층 경계 유지). 실제 파일 입출력은 infrastructure.recent_files가 한다.
"""
from __future__ import annotations

import pathlib

from packnine.infrastructure import recent_files


class RecentFilesService:
    """최근 연 아카이브 목록을 읽고 갱신한다."""

    def list_recent(self) -> list[pathlib.Path]:
        return recent_files.load()

    def remember(self, archive_path: pathlib.Path) -> None:
        recent_files.remember(archive_path)

    def clear(self) -> None:
        recent_files.clear()
