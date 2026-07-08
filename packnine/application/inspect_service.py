"""아카이브 내용 미리보기(목록 조회) 유스케이스."""
from __future__ import annotations

import pathlib

from packnine.domain.entities import ArchiveManifest
from packnine.infrastructure import format_registry


class InspectService:
    """디스크에 아무것도 쓰지 않고 아카이브 내부 목록만 조회하는 유스케이스."""

    def list_contents(
        self, archive_path: pathlib.Path, *, password: str | None = None
    ) -> ArchiveManifest:
        archive_path = pathlib.Path(archive_path)
        reader = format_registry.get_reader(archive_path, password=password)
        try:
            entries = reader.list_entries()
        finally:
            reader.close()
        return ArchiveManifest(entries=entries, format_name=archive_path.suffix)
