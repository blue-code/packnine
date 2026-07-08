"""도메인 값객체(Value Object) 모음.

값객체는 식별자 없이 값 자체로 동일성을 판단하며 불변(immutable)이어야 한다.
외부 압축 라이브러리에 의존하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


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
