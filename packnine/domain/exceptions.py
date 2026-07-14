"""도메인 계층 예외 모음."""
from __future__ import annotations


class UnsafeArchiveEntryError(Exception):
    """악성/위험한 아카이브 엔트리를 발견했을 때 발생시킨다."""

    def __init__(self, entry_name: str, reason: str) -> None:
        self.entry_name = entry_name
        self.reason = reason
        super().__init__(f"안전하지 않은 아카이브 엔트리: '{entry_name}' ({reason})")


class InvalidPasswordError(Exception):
    """비밀번호가 틀렸거나, 암호화된 아카이브인데 비밀번호가 없을 때 발생시킨다.

    라이브러리별로 새어 나오는 예외가 제각각(RuntimeError, TypeError, CrcError 등)이라
    presentation 계층이 일관되게 "비밀번호를 확인하세요"를 안내할 수 있도록
    어댑터가 반드시 이 예외로 변환해서 던진다.
    """


class UnsupportedFormatError(Exception):
    """지원하지 않는 아카이브 포맷일 때 발생시킨다."""


class CorruptedArchiveError(Exception):
    """아카이브 파일이 깨져 있어 읽을 수 없을 때 발생시킨다.

    라이브러리 고유 예외(BadZipFile, Bad7zFile, tarfile.ReadError 등)를 그대로
    전파하면 presentation 계층이 포맷별로 분기해야 하므로 어댑터가 이 예외로 통일한다.
    """


class ExternalToolMissingError(Exception):
    """외부 실행 도구(7z.exe, unrar 등)를 찾을 수 없을 때 발생시킨다."""
