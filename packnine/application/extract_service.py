"""압축 해제 유스케이스 오케스트레이션."""
from __future__ import annotations

import pathlib
import shutil
import tempfile

from packnine.application import smart_naming
from packnine.application.inspect_service import InspectService
from packnine.domain.entities import ArchiveManifest
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy
from packnine.domain.value_objects import DuplicatePolicy
from packnine.infrastructure import format_registry, motw


class ExtractService:
    """아카이브를 지정한 디렉터리에 안전하게 해제하는 유스케이스."""

    def __init__(self, security_policy: ArchiveSecurityPolicy | None = None) -> None:
        # 정책을 주입 가능하게 해 호출자가 용량/압축률 상한 등을 테스트/커스터마이즈할 수 있게 한다.
        self._security_policy = security_policy or ArchiveSecurityPolicy()

    def find_conflicts(
        self, manifest: ArchiveManifest, destination: pathlib.Path
    ) -> list[str]:
        """해제하면 덮어쓰게 될 기존 파일들의 엔트리 이름을 돌려준다.

        해제를 시작하기 전에 "이미 있는 파일 N개를 어떻게 할지" 물어보기 위한 조회용이다.
        디스크에 아무것도 쓰지 않는다.
        """
        destination = pathlib.Path(destination)
        if not destination.exists():
            return []

        conflicts: list[str] = []
        for entry in manifest.entries:
            if entry.is_dir:
                continue
            try:
                target = self._security_policy.validate_entry(entry, destination)
            except Exception:  # noqa: BLE001 - 위험한 엔트리는 해제 단계에서 별도로 막는다
                continue
            if target.exists():
                conflicts.append(entry.name)
        return conflicts

    def extract(
        self,
        archive_path: pathlib.Path,
        destination: pathlib.Path,
        *,
        password: str | None = None,
        on_progress: ProgressCallback | None = None,
        duplicate_policy: DuplicatePolicy = DuplicatePolicy.OVERWRITE,
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

            # 덮어쓰기(기존 동작)이거나 충돌이 아예 없으면 곧바로 목적지에 푼다.
            # 이 경로에는 추가 비용이 전혀 붙지 않는다.
            needs_staging = (
                duplicate_policy is not DuplicatePolicy.OVERWRITE
                and bool(self.find_conflicts(manifest, destination))
            )

            destination.mkdir(parents=True, exist_ok=True)
            # 엔트리별 Zip Slip/심볼릭링크/압축률 검증은 인프라 어댑터가 이미
            # security_policy로 수행하므로 여기서 중복하지 않는다.
            if needs_staging:
                written_names = self._extract_via_staging(
                    reader, destination, duplicate_policy, on_progress
                )
            else:
                reader.extract_all(destination, on_progress=on_progress)
                written_names = [entry.name for entry in manifest.entries if not entry.is_dir]
        finally:
            reader.close()

        # 원본 아카이브가 웹에서 받은 파일이라면(Zone.Identifier 존재) 이번에 해제된
        # 파일들에만 동일한 MoTW 표시를 남겨, 실행 시 SmartScreen 등 보호 기제가 그대로
        # 작동하도록 한다(비-Windows/ADS 미지원 환경에서는 조용히 아무 일도 하지 않음).
        # 목적지에 원래 있던 파일은 절대 건드리지 않도록 실제로 쓴 파일 목록만 넘긴다
        # (건너뛴 파일은 우리가 쓴 게 아니므로 표시를 덧씌우면 안 된다).
        motw.propagate_zone_identifier(archive_path, destination, written_names)

        return manifest

    def _extract_via_staging(
        self,
        reader,
        destination: pathlib.Path,
        duplicate_policy: DuplicatePolicy,
        on_progress: ProgressCallback | None,
    ) -> list[str]:
        """임시 폴더에 먼저 푼 뒤, 중복 정책에 따라 목적지로 옮긴다.

        어댑터(zipfile/py7zr/tarfile/unrar)는 목적지에 바로 쓰기 때문에, 포맷마다 "건너뛰기"를
        따로 구현하면 어댑터 수만큼 중복되고 누락도 생긴다. 한 단계 staging을 두면 정책을
        전 포맷 공통으로 한 곳에서 처리할 수 있다.

        staging은 목적지와 같은 볼륨(부모 폴더 아래)에 만든다. %TEMP%가 다른 드라이브면
        옮기는 단계가 복사+삭제로 바뀌어 느려지기 때문이다.

        돌려주는 값은 실제로 목적지에 쓴 파일들의 상대 경로(MoTW 표시 대상)다.
        """
        staging_parent = destination.parent if destination.parent.exists() else destination
        staging = pathlib.Path(tempfile.mkdtemp(prefix="packnine_stage_", dir=staging_parent))
        try:
            reader.extract_all(staging, on_progress=on_progress)

            written: list[str] = []
            for source in sorted(staging.rglob("*")):
                if source.is_dir():
                    continue
                relative = source.relative_to(staging)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)

                if target.exists():
                    if duplicate_policy is DuplicatePolicy.SKIP:
                        continue
                    target = smart_naming.resolve_unique_file_path(target)

                # os.replace 계열(shutil.move)은 같은 볼륨이면 rename이라 추가 복사가 없다.
                shutil.move(str(source), str(target))
                written.append(target.relative_to(destination).as_posix())
            return written
        finally:
            shutil.rmtree(staging, ignore_errors=True)

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

        # 일부만 꺼낸 경우에도(드래그 아웃/외부 앱으로 열기) 원본의 MoTW를 물려줘야
        # 꺼낸 파일을 실행할 때 보호 기제가 그대로 작동한다.
        motw.propagate_zone_identifier(archive_path, destination, entry_names)

    def smart_extract(
        self,
        archive_path: pathlib.Path,
        base_destination: pathlib.Path,
        *,
        password: str | None = None,
        on_progress: ProgressCallback | None = None,
        duplicate_policy: DuplicatePolicy = DuplicatePolicy.OVERWRITE,
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
            archive_path,
            destination,
            password=password,
            on_progress=on_progress,
            duplicate_policy=duplicate_policy,
        )
