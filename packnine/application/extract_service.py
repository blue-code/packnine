"""압축 해제 유스케이스 오케스트레이션."""
from __future__ import annotations

import pathlib

from packnine.domain.entities import ArchiveManifest
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy
from packnine.infrastructure import format_registry


class ExtractService:
    """아카이브를 지정한 디렉터리에 안전하게 해제하는 유스케이스."""

    def __init__(self, security_policy: ArchiveSecurityPolicy | None = None) -> None:
        # 정책을 주입 가능하게 해 호출자가 용량/압축률 상한 등을 테스트/커스터마이즈할 수 있게 한다.
        self._security_policy = security_policy or ArchiveSecurityPolicy()

    def extract(
        self,
        archive_path: pathlib.Path,
        destination: pathlib.Path,
        *,
        password: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        archive_path = pathlib.Path(archive_path)
        destination = pathlib.Path(destination)

        # RAR인데 외부 도구(unrar/bsdtar)가 없으면 get_reader 생성 시점에
        # ExternalToolMissingError가 올라온다 — 여기서 잡지 않고 그대로 전파한다.
        reader = format_registry.get_reader(archive_path, password=password)
        try:
            entries = reader.list_entries()
            manifest = ArchiveManifest(entries=entries, format_name=archive_path.suffix)

            # 실제 추출을 시도하기 전에 전체 용량 등을 먼저 검사해, 위험하면
            # 추출 시도 자체를 하지 않는다(UnsafeArchiveEntryError는 즉시 전파).
            self._security_policy.validate_manifest(manifest)

            destination.mkdir(parents=True, exist_ok=True)
            # 엔트리별 Zip Slip/심볼릭링크/압축률 검증은 인프라 어댑터가 이미
            # security_policy로 수행하므로 여기서 중복하지 않는다.
            reader.extract_all(destination, on_progress=on_progress)
        finally:
            reader.close()

        return manifest
