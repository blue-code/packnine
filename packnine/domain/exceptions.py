"""도메인 계층 예외 모음."""
from __future__ import annotations


class UnsafeArchiveEntryError(Exception):
    """악성/위험한 아카이브 엔트리를 발견했을 때 발생시킨다."""

    def __init__(self, entry_name: str, reason: str) -> None:
        self.entry_name = entry_name
        self.reason = reason
        super().__init__(f"안전하지 않은 아카이브 엔트리: '{entry_name}' ({reason})")


class UnsupportedFormatError(Exception):
    """지원하지 않는 아카이브 포맷일 때 발생시킨다."""


class ExternalToolMissingError(Exception):
    """외부 실행 도구(7z.exe, unrar 등)를 찾을 수 없을 때 발생시킨다."""
