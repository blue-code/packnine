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
        max_total_compression_ratio: float = 20.0,
        min_total_uncompressed_size: int = 10 * 1024 * 1024 * 1024,
        max_total_uncompressed_size: int | None = None,
        allow_symlinks: bool = False,
        max_entry_count: int = 100_000,
        max_entry_name_length: int = 1024,
    ) -> None:
        self.max_compression_ratio = max_compression_ratio
        # 합계 팽창률 상한. 엔트리별 상한보다 반드시 낮아야 의미가 있다 - 전체 팽창률은
        # 엔트리별 팽창률의 가중평균이라 수학적으로 엔트리 최대값을 넘을 수 없고, 두 값을
        # 같게 두면 이 검사는 절대 발동하지 않는 죽은 코드가 된다. 낮게 두는 덕에
        # "엔트리마다 압축률 50인 파일 1만 개"처럼 엔트리 검사를 통과하는 조합을 잡는다.
        self.max_total_compression_ratio = max_total_compression_ratio
        # 팽창률만으로 막으면 정상 아카이브가 과잉 차단된다. 50MB 로그 묶음이 2GB로
        # 풀리면 팽창률 40인데, 이건 악의가 아니라 텍스트가 잘 줄어든 결과다. 그래서
        # 이 크기 아래로 풀리는 아카이브는 팽창률을 묻지 않고 통과시킨다.
        #
        # 하한을 10GiB로 둔 것은 0.13.0까지 "절대 상한"이던 값을 뒤집은 것이다. 같은
        # 숫자를 천장이 아니라 바닥으로 쓴다. 이만큼까지는 보통 디스크에 들어가므로
        # 실제로 들어가는지는 아래 application 계층의 여유 공간 검사가 판단한다.
        self.min_total_uncompressed_size = min_total_uncompressed_size
        # 절대 용량 상한은 기본으로 걸지 않는다(None). 예전에는 10GiB가 기본값이었는데,
        # 동영상을 압축 없이 담아 둔 10.6GiB zip처럼 압축폭탄과 무관한 아카이브까지
        # "안전하지 않음"으로 막았다. 압축폭탄의 본질은 절대 크기가 아니라 팽창률이다.
        # 디스크에 안 들어가는 문제는 보안이 아니라 용량 문제이므로, 목적지를 아는
        # application 계층에서 실제 여유 공간과 비교해 따로 처리한다.
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
        """아카이브 전체의 팽창률/용량/엔트리 개수가 상한을 넘는지 검사한다."""
        total = manifest.total_uncompressed_size

        # 호출자가 절대 상한을 명시했을 때만 적용한다(기본값은 상한 없음).
        if (
            self.max_total_uncompressed_size is not None
            and total > self.max_total_uncompressed_size
        ):
            raise UnsafeArchiveEntryError(
                entry_name="__manifest__",
                reason=(
                    f"전체 압축해제 용량({total} bytes)이 허용 상한"
                    f"({self.max_total_uncompressed_size} bytes)을 초과합니다"
                ),
            )

        # 허용량은 "아카이브 실제 크기 x 팽창률 상한"이되, 작은 아카이브가 과잉 차단되지
        # 않도록 하한을 둔다. 압축하지 않고 담은 아카이브는 팽창률이 1.0이라 항상 통과한다
        # (출력이 이미 입력만큼 크므로 압축폭탄일 수가 없다).
        allowance = max(
            self.min_total_uncompressed_size,
            int(manifest.total_compressed_size * self.max_total_compression_ratio),
        )
        if total > allowance:
            actual_ratio = total / max(manifest.total_compressed_size, 1)
            raise UnsafeArchiveEntryError(
                entry_name="__manifest__",
                reason=(
                    f"전체 팽창률({actual_ratio:.1f})이 허용 상한"
                    f"({self.max_total_compression_ratio})을 초과하여 압축폭탄으로"
                    f" 의심됩니다(압축 {manifest.total_compressed_size} bytes →"
                    f" 해제 {total} bytes)"
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
