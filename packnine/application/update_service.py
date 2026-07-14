"""아카이브 편집(파일 추가/엔트리 삭제) 유스케이스.

zipfile은 append만 되고 삭제가 안 되며, py7zr은 append 시 솔리드 블록 제약이 있고,
tar.gz는 둘 다 불가능하다. 포맷별 편차를 사용자에게 노출하지 않기 위해
"임시 폴더에 전체 해제 -> 변경 적용 -> 같은 포맷/암호로 재압축 -> 원자적 교체"
재작성 방식으로 통일한다. 대용량에서는 느리지만 정확성과 일관성이 우선이다.

교체는 아카이브와 같은 폴더의 임시 파일에 쓴 뒤 os.replace()로 수행한다
(%TEMP%가 다른 드라이브일 수 있어 cross-volume rename 실패를 피하고,
실패 시 원본이 절대 손상되지 않게 하기 위함).
"""
from __future__ import annotations

import os
import pathlib
import shutil
import tempfile

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
from packnine.application.inspect_service import InspectService
from packnine.domain.entities import ArchiveManifest
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.value_objects import CompressionLevel


class UpdateService:
    """기존 아카이브에 파일을 추가하거나 엔트리를 삭제한다(재작성 방식)."""

    def add_files(
        self,
        archive_path: pathlib.Path,
        new_paths: list[pathlib.Path],
        *,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        archive_path = pathlib.Path(archive_path)
        # 재작성 전에 입력을 먼저 검증해야 실패 시 원본이 그대로 남는다.
        for new_path in new_paths:
            if not pathlib.Path(new_path).exists():
                raise FileNotFoundError(f"추가할 경로가 존재하지 않습니다: {new_path}")

        def apply_changes(content_dir: pathlib.Path) -> None:
            for new_path in new_paths:
                source = pathlib.Path(new_path)
                target = content_dir / source.name
                # 같은 이름이 이미 있으면 덮어쓴다(반디집 기본 동작과 동일).
                if source.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)

        return self._rebuild(
            archive_path,
            apply_changes,
            password=password,
            compression_level=compression_level,
            on_progress=on_progress,
        )

    def remove_entries(
        self,
        archive_path: pathlib.Path,
        entry_names: list[str],
        *,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        archive_path = pathlib.Path(archive_path)

        def apply_changes(content_dir: pathlib.Path) -> None:
            for entry_name in entry_names:
                # 엔트리명은 아카이브 내부 표기('/' 구분, 디렉터리는 후행 '/' 가능성)
                relative = pathlib.PurePosixPath(entry_name.rstrip("/"))
                target = content_dir.joinpath(*relative.parts)
                if not target.exists():
                    raise KeyError(f"아카이브에 존재하지 않는 엔트리입니다: {entry_name}")
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()

        return self._rebuild(
            archive_path,
            apply_changes,
            password=password,
            compression_level=compression_level,
            on_progress=on_progress,
        )

    def _rebuild(
        self,
        archive_path: pathlib.Path,
        apply_changes,
        *,
        password: str | None,
        compression_level: CompressionLevel,
        on_progress: ProgressCallback | None,
    ) -> ArchiveManifest:
        work_dir = pathlib.Path(tempfile.mkdtemp(prefix="packnine_edit_"))
        # 원자적 교체를 위해 원본과 같은 폴더/같은 확장자로 임시 아카이브를 만든다
        # (확장자가 포맷 판별 기준이므로 이름 앞에만 접두어를 붙인다).
        temp_archive = archive_path.with_name(f"~packnine_edit_{archive_path.name}")
        try:
            content_dir = work_dir / "content"
            ExtractService().extract(archive_path, content_dir, password=password)

            apply_changes(content_dir)

            sources = sorted(content_dir.iterdir())
            CompressService().compress(
                sources,
                temp_archive,
                password=password,
                compression_level=compression_level,
                on_progress=on_progress,
            )
            os.replace(temp_archive, archive_path)
        finally:
            temp_archive.unlink(missing_ok=True)
            shutil.rmtree(work_dir, ignore_errors=True)

        return InspectService().list_contents(archive_path, password=password)
