"""아카이브 보안 정책 — Zip Slip, 압축폭탄 등으로부터 압축해제를 보호한다.

domain 계층이므로 순수 표준 라이브러리(pathlib/re)만 사용하고
zipfile/py7zr 등 실제 압축 라이브러리는 import하지 않는다.
"""
from __future__ import annotations

import pathlib
import re

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import UnsafeArchiveEntryError

# "C:" 같은 Windows 드라이브 문자 패턴 (대소문자 무관)
_DRIVE_LETTER_PATTERN = re.compile(r"^[A-Za-z]:")


class ArchiveSecurityPolicy:
    """아카이브 엔트리/전체 목록의 안전성을 검증하는 정책 객체."""

    def __init__(
        self,
        max_compression_ratio: float = 100.0,
        max_total_uncompressed_size: int = 10 * 1024 * 1024 * 1024,
        allow_symlinks: bool = False,
        max_entry_count: int = 100_000,
        max_entry_name_length: int = 1024,
    ) -> None:
        self.max_compression_ratio = max_compression_ratio
        self.max_total_uncompressed_size = max_total_uncompressed_size
        self.allow_symlinks = allow_symlinks
        # 압축비/전체용량이 정상 범위여도 엔트리 수가 지나치게 많으면(예: 빈 파일 수백만 개)
        # 처리 자체가 리소스 고갈(DoS)로 이어질 수 있어 별도 상한을 둔다.
        self.max_entry_count = max_entry_count
        # 비정상적으로 긴 경로는 파일시스템/외부 도구 호출 시 예기치 못한 동작을 유발할 수
        # 있는 병적인(pathological) 입력이므로 사전에 차단한다.
        self.max_entry_name_length = max_entry_name_length

    def validate_entry(
        self, entry: ArchiveEntry, destination_root: pathlib.Path
    ) -> pathlib.Path:
        """엔트리를 검증하고, 통과하면 실제로 쓸 안전한 절대 경로를 반환한다."""
        name = entry.name

        if len(name) > self.max_entry_name_length:
            raise UnsafeArchiveEntryError(
                name,
                f"엔트리 이름 길이({len(name)})가 허용 상한"
                f"({self.max_entry_name_length})을 초과합니다",
            )

        # 절대경로/드라이브 문자는 destination_root와 결합해도 root를 무시하고
        # 임의 위치를 가리킬 수 있으므로 경로 결합 전에 먼저 명시적으로 차단한다.
        if self._is_absolute_or_drive(name):
            raise UnsafeArchiveEntryError(
                name, "절대 경로 또는 드라이브 문자를 포함한 엔트리는 허용되지 않습니다"
            )

        # NTFS ADS(Alternate Data Stream) 삽입 방지: "normal.txt:evil.exe" 형태의 이름은
        # 실제 파일이 아니라 normal.txt의 대체 스트림에 쓰여 탐지를 피한 채 임의 콘텐츠를
        # 심을 수 있다(RAR의 ADS 처리 관련 취약점과 동일한 클래스). 드라이브 문자(예: "C:")는
        # 위에서 이미 별도로 걸러지므로, 여기서는 그 외의 모든 콜론 포함 이름을 차단한다.
        if ":" in name:
            raise UnsafeArchiveEntryError(
                name, "콜론(:)을 포함한 엔트리는 NTFS 대체 데이터 스트림(ADS)으로 악용될 수 있어 허용되지 않습니다"
            )

        if entry.is_symlink and not self.allow_symlinks:
            raise UnsafeArchiveEntryError(name, "심볼릭 링크 엔트리는 허용되지 않습니다")

        # ZIP 스펙은 '/'를 구분자로 쓰지만, 악성 엔트리가 Windows 스타일 '\'를 섞어
        # 넣으면 POSIX에서 pathlib가 이를 하나의 파일명으로 오인해 뒤의 resolve()
        # 기반 검사를 무력화할 수 있다(플랫폼에 따라 방어 여부가 갈리는 취약점).
        # 그래서 먼저 '\'를 '/'로 정규화한 뒤 세그먼트 단위로 ".."을 직접 검사한다.
        normalized = name.replace("\\", "/")
        segments = [seg for seg in normalized.split("/") if seg not in ("", ".")]
        if any(seg == ".." for seg in segments):
            raise UnsafeArchiveEntryError(
                name, "대상 디렉터리를 벗어나는 경로(Zip Slip)가 감지되었습니다"
            )

        root = destination_root.resolve()
        candidate = (root / normalized).resolve()

        # Zip Slip 방지(2차 방어): 정규화 후에도 candidate가 root 하위(또는 root 자신)여야 한다.
        if candidate != root and root not in candidate.parents:
            raise UnsafeArchiveEntryError(
                name, "대상 디렉터리를 벗어나는 경로(Zip Slip)가 감지되었습니다"
            )

        # 압축폭탄 방지: 디렉터리 엔트리는 압축률 개념이 의미 없으므로 검사 제외
        if not entry.is_dir and entry.compression_ratio > self.max_compression_ratio:
            raise UnsafeArchiveEntryError(
                name,
                f"압축률({entry.compression_ratio:.1f})이 허용 상한"
                f"({self.max_compression_ratio})을 초과하여 압축폭탄으로 의심됩니다",
            )

        return candidate

    def validate_manifest(self, manifest: ArchiveManifest) -> None:
        """전체 압축해제 용량/엔트리 개수가 상한을 넘는지 검사한다."""
        total = manifest.total_uncompressed_size
        if total > self.max_total_uncompressed_size:
            raise UnsafeArchiveEntryError(
                entry_name="__manifest__",
                reason=(
                    f"전체 압축해제 용량({total} bytes)이 허용 상한"
                    f"({self.max_total_uncompressed_size} bytes)을 초과합니다"
                ),
            )

        entry_count = len(manifest.entries)
        if entry_count > self.max_entry_count:
            raise UnsafeArchiveEntryError(
                entry_name="__manifest__",
                reason=(
                    f"엔트리 개수({entry_count})가 허용 상한"
                    f"({self.max_entry_count})을 초과합니다(리소스 고갈 방지)"
                ),
            )

    @staticmethod
    def _is_absolute_or_drive(name: str) -> bool:
        if name.startswith("/") or name.startswith("\\"):
            return True
        return bool(_DRIVE_LETTER_PATTERN.match(name))
