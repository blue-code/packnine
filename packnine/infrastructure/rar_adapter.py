"""rarfile 기반 RAR 어댑터 — 해제 전용.

RAR 포맷의 압축(인코딩)은 라이선스 문제로 오픈소스 구현체가 존재하지 않아
쓰기는 지원하지 않는다. rarfile 라이브러리 자체도 unrar 또는 bsdtar 같은
외부 실행 파일에 의존하므로, 해당 도구가 없으면 생성자 단계에서 바로
ExternalToolMissingError를 발생시켜 사용자에게 설치를 안내한다.
"""
from __future__ import annotations

import pathlib
import shutil

import rarfile

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import (
    CorruptedArchiveError,
    ExternalToolMissingError,
    InvalidPasswordError,
)
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy


class RarCompressionNotSupportedError(Exception):
    """RAR 포맷으로의 압축(쓰기)은 라이선스 제약으로 지원하지 않는다."""


def _ensure_unrar_tool_available() -> None:
    if shutil.which(rarfile.UNRAR_TOOL) is None and shutil.which("bsdtar") is None:
        raise ExternalToolMissingError(
            "RAR 압축 해제에 필요한 외부 도구를 찾을 수 없습니다. "
            "unrar 또는 bsdtar를 설치하세요."
        )


class RarArchiveReader:
    """rarfile을 사용하는 RAR 해제 전용 어댑터."""

    def __init__(self, path: pathlib.Path, password: str | None = None) -> None:
        _ensure_unrar_tool_available()
        self._path = pathlib.Path(path)
        self._password = password
        try:
            self._archive = rarfile.RarFile(self._path)
        except rarfile.PasswordRequired as exc:
            raise InvalidPasswordError(f"비밀번호가 필요한 아카이브입니다: {self._path}") from exc
        except rarfile.Error as exc:  # NotRarFile, BadRarFile 등 파싱 실패 전반
            raise CorruptedArchiveError(f"RAR 파일이 손상되었거나 rar 형식이 아닙니다: {self._path}") from exc
        if password:
            self._archive.setpassword(password)

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for info in self._archive.infolist():
            modified_at: float | None = None
            if info.date_time:
                import time

                try:
                    modified_at = time.mktime((*info.date_time, 0, 0, -1))
                except (ValueError, OverflowError):
                    modified_at = None
            entries.append(
                ArchiveEntry(
                    name=info.filename.replace("\\", "/"),
                    size=info.file_size,
                    compressed_size=info.compress_size,
                    is_dir=info.is_dir(),
                    is_symlink=info.is_symlink(),
                    modified_at=modified_at,
                )
            )
        return entries

    def _validate_all(
        self, destination: pathlib.Path
    ) -> list[tuple[ArchiveEntry, pathlib.Path]]:
        entries = self.list_entries()
        manifest = ArchiveManifest(entries=entries, format_name="rar")
        policy = ArchiveSecurityPolicy()
        policy.validate_manifest(manifest)
        return [(entry, policy.validate_entry(entry, destination)) for entry in entries]

    def extract_all(
        self,
        destination: pathlib.Path,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        destination = pathlib.Path(destination)
        validated = self._validate_all(destination)

        destination.mkdir(parents=True, exist_ok=True)
        total = len(validated)
        for done, (entry, _target_path) in enumerate(validated, start=1):
            self._extract_entry(entry.name, destination)
            if on_progress is not None:
                on_progress(entry.name, done, total)

    def _extract_entry(self, entry_name: str, destination: pathlib.Path) -> None:
        """단일 엔트리를 해제하되 rarfile의 암호/손상 예외를 도메인 예외로 변환한다."""
        try:
            self._archive.extract(entry_name, path=destination, pwd=self._password)
        except (rarfile.PasswordRequired, rarfile.RarWrongPassword) as exc:
            raise InvalidPasswordError(
                f"비밀번호가 틀렸거나 필요합니다: {self._path}"
            ) from exc
        except rarfile.BadRarFile as exc:
            raise CorruptedArchiveError(f"RAR 파일이 손상되었습니다: {self._path}") from exc

    def extract_one(self, entry_name: str, destination: pathlib.Path) -> None:
        destination = pathlib.Path(destination)
        entries = self.list_entries()
        entry = next((e for e in entries if e.name == entry_name), None)
        if entry is None:
            raise KeyError(f"아카이브에 존재하지 않는 엔트리입니다: {entry_name}")

        policy = ArchiveSecurityPolicy()
        policy.validate_entry(entry, destination)

        destination.mkdir(parents=True, exist_ok=True)
        self._extract_entry(entry_name, destination)

    def close(self) -> None:
        self._archive.close()


def _raise_rar_writer_not_supported() -> None:
    raise RarCompressionNotSupportedError(
        "RAR 압축(쓰기)은 라이선스 문제로 지원하지 않습니다. ZIP/7Z/TAR를 사용하세요."
    )


class RarArchiveWriter:
    """RAR 쓰기를 실수로 시도했을 때 안내 예외를 내기 위한 최소 클래스.

    실제 RAR 인코더는 구현하지 않는다(라이선스 제약).
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        _raise_rar_writer_not_supported()

    def add_files(self, *args: object, **kwargs: object) -> None:
        _raise_rar_writer_not_supported()

    def close(self) -> None:
        _raise_rar_writer_not_supported()
