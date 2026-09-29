"""도메인 값객체(Value Object) 모음.

값객체는 식별자 없이 값 자체로 동일성을 판단하며 불변(immutable)이어야 한다.
외부 압축 라이브러리에 의존하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class DuplicatePolicy(Enum):
    """해제 시 목적지에 같은 이름의 파일이 이미 있을 때의 처리 방식.

    기본값은 OVERWRITE다 - 이 기능이 생기기 전의 동작이라, 정책을 지정하지 않은
    기존 호출부의 결과가 달라지지 않아야 한다.
    """

    OVERWRITE = "overwrite"  # 기존 파일을 덮어쓴다
    SKIP = "skip"  # 기존 파일을 그대로 두고 해당 엔트리는 풀지 않는다
    RENAME = "rename"  # 기존 파일을 두고 새 파일에 _2, _3 ... 을 붙여 함께 남긴다


class CompressionLevel(IntEnum):
    """압축 강도. IntEnum이라 정수처럼 비교/정렬 가능하며 값 자체가 불변이다."""

    STORE = 0
    FASTEST = 1
    NORMAL = 5
    MAXIMUM = 9


@dataclass(frozen=True)
class PasswordPolicy:
    """아카이브 암호화 정책."""

    password: str | None = None
    use_aes256: bool = True

    @property
    def is_encrypted(self) -> bool:
        # password가 None이거나 빈 문자열이면 암호화하지 않은 것으로 간주
        return self.password is not None and self.password != ""


@dataclass(frozen=True)
class ArchivePath:
    """아카이브 내부 엔트리 경로의 원본 문자열을 보관하는 값객체.

    검증(안전한 경로인지 등)은 security_policy 모듈에서 수행하며,
    이 값객체는 아직 검증하지 않은 원본 문자열만 보관한다.
    """

    raw: str


_BYTES_PER_MEGABYTE = 1024 * 1024


@dataclass(frozen=True)
class VolumeSize:
    """분할 압축 시 볼륨 하나의 최대 크기(bytes).

    메일 첨부 한도는 서비스들이 MiB 기준으로 잡고 있어 1024 기반으로 환산한다.
    10진 MB(1,000,000)로 잡으면 한도보다 작게 나와 손해만 보고, 반대로 잡을 일은 없다.
    """

    bytes: int

    def __post_init__(self) -> None:
        if self.bytes <= 0:
            raise ValueError(f"볼륨 크기는 양수여야 합니다: {self.bytes}")

    @classmethod
    def from_megabytes(cls, megabytes: int) -> "VolumeSize":
        if megabytes < 1:
            raise ValueError(f"볼륨 크기는 1MB 이상이어야 합니다: {megabytes}")
        return cls(bytes=megabytes * _BYTES_PER_MEGABYTE)

    @property
    def megabytes(self) -> int:
        return self.bytes // _BYTES_PER_MEGABYTE


@dataclass(frozen=True)
class SplitPreset:
    """분할 크기 프리셋. 옵션 창의 콤보 항목 하나에 대응한다."""

    label: str
    megabytes: int
    note: str  # 툴팁/안내용 - 한도 기준(합계/파일당)과 조사 시점을 남긴다

    @property
    def volume_size(self) -> VolumeSize:
        return VolumeSize.from_megabytes(self.megabytes)


# 메일 첨부 한도 프리셋 (2026-09 조사 기준). 한도는 서비스가 바꿀 수 있으므로 프리셋은
# 옵션 창의 MB 입력란을 채우는 단축키 역할만 하고, 사용자가 값을 고쳐 쓸 수 있게 둔다.
# 다음 대용량 4GB는 4096MB로 잡으면 FAT32 파일 한도(4GB-1byte)를 넘겨 USB 복사가 실패하므로
# 4095MB로 잡는다. 메일 한도 "4GB 이하"도 그대로 만족한다.
SPLIT_PRESETS: tuple[SplitPreset, ...] = (
    SplitPreset(
        "네이버 메일 일반첨부 (10MB)",
        10,
        "파일 1개당 10MB. 넘으면 대용량첨부로 바뀌어 30일 다운로드 기한이 생깁니다.",
    ),
    SplitPreset(
        "네이버 메일 대용량첨부 (2GB)",
        2048,
        "파일 1개당 2GB, 메일 1통에 10개까지. 30일·100회 다운로드 제한이 있습니다.",
    ),
    SplitPreset(
        "다음 메일 일반첨부 (25MB)",
        25,
        "단일 또는 합계 25MB. 합계 기준이라 볼륨 하나당 메일 한 통으로 보내세요.",
    ),
    SplitPreset(
        "다음 메일 대용량첨부 (4GB)",
        4095,
        "파일 1개당 4GB. FAT32 USB 복사가 되도록 4095MB로 잡았습니다.",
    ),
    SplitPreset(
        "Gmail 첨부 (25MB)",
        25,
        "합계 25MB. 넘으면 Google Drive 링크로 바뀝니다. 볼륨 하나당 메일 한 통으로 보내세요.",
    ),
)
