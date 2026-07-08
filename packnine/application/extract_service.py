"""압축 해제 유스케이스 오케스트레이션."""
from __future__ import annotations

import pathlib

from packnine.application import smart_naming
from packnine.application.inspect_service import InspectService
from packnine.domain.entities import ArchiveManifest
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy
from packnine.infrastructure import format_registry, motw


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

        # 원본 아카이브가 웹에서 받은 파일이라면(Zone.Identifier 존재) 해제된 모든
        # 파일에도 동일한 MoTW 표시를 남겨, 실행 시 SmartScreen 등 보호 기제가 그대로
        # 작동하도록 한다(비-Windows/ADS 미지원 환경에서는 조용히 아무 일도 하지 않음).
        motw.propagate_zone_identifier(archive_path, destination)

        return manifest

    def extract_entries(
        self,
        archive_path: pathlib.Path,
        entry_names: list[str],
        destination: pathlib.Path,
        *,
        password: str | None = None,
    ) -> None:
        """아카이브 전체가 아니라 지정한 엔트리 몇 개만 destination에 해제한다.

        내장 이미지 뷰어처럼 일부 항목만 빠르게 미리 볼 때 전체 압축 해제보다 가볍게
        쓰기 위한 것이다. 엔트리별 검증은 어댑터의 extract_one이 이미 수행한다.
        """
        archive_path = pathlib.Path(archive_path)
        destination = pathlib.Path(destination)
        destination.mkdir(parents=True, exist_ok=True)

        reader = format_registry.get_reader(archive_path, password=password)
        try:
            for entry_name in entry_names:
                reader.extract_one(entry_name, destination)
        finally:
            reader.close()

    def smart_extract(
        self,
        archive_path: pathlib.Path,
        base_destination: pathlib.Path,
        *,
        password: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        """반디집 "알아서 압축풀기"처럼 실제 해제 위치를 아카이브 내용에 맞춰 자동으로 정한다.

        먼저 목록만 조회해 manifest를 얻고(디스크에 아무것도 쓰지 않음), 그 manifest를
        기준으로 smart_naming이 최종 목적지를 계산한 뒤 기존 extract()에 위임한다
        (로직 중복 금지).
        """
        archive_path = pathlib.Path(archive_path)
        manifest = InspectService().list_contents(archive_path, password=password)
        destination = smart_naming.resolve_smart_extract_destination(
            manifest, archive_path, base_destination
        )
        return self.extract(
            archive_path, destination, password=password, on_progress=on_progress
        )
