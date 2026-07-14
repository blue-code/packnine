"""py7zr 기반 7Z 어댑터.

py7zr은 AES-256 암호화(header_encryption=True)를 기본 지원하므로,
"진짜" 비밀번호 보호가 필요한 경우 이 어댑터를 사용한다(ZIP 어댑터는 표준
zipfile의 한계로 쓰기 시 실제 암호화를 지원하지 않음).
"""
from __future__ import annotations

import contextlib
import lzma
import pathlib

import py7zr
import py7zr.exceptions

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import CorruptedArchiveError, InvalidPasswordError
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy
from packnine.domain.value_objects import CompressionLevel


@contextlib.contextmanager
def _map_py7zr_errors(path: pathlib.Path, password: str | None):
    """py7zr의 들쭉날쭉한 예외를 도메인 예외로 변환한다.

    헤더 암호화된 7z를 틀린 암호로 열면 py7zr은 깨진 헤더를 그대로 파싱하다가
    TypeError("Unknown field...") 같은 내부 예외를 던진다(전용 예외 없음).
    암호가 주어진 상태의 파싱/CRC 실패는 "암호가 틀렸을 가능성"으로 안내하고,
    무암호 상태의 동일 실패는 파일 손상으로 안내한다.
    """
    try:
        yield
    except py7zr.exceptions.PasswordRequired as exc:
        raise InvalidPasswordError(f"비밀번호가 필요한 아카이브입니다: {path}") from exc
    except (TypeError, py7zr.exceptions.Bad7zFile, py7zr.exceptions.CrcError, lzma.LZMAError) as exc:
        if password is not None:
            raise InvalidPasswordError(
                f"비밀번호가 틀렸거나 파일이 손상되었습니다: {path}"
            ) from exc
        raise CorruptedArchiveError(f"7Z 파일이 손상되었습니다: {path}") from exc


class SevenZipArchiveReader:
    """py7zr을 사용하는 7Z 해제 어댑터."""

    def __init__(self, path: pathlib.Path, password: str | None = None) -> None:
        self._path = pathlib.Path(path)
        self._password = password
        with _map_py7zr_errors(self._path, password):
            self._archive = py7zr.SevenZipFile(self._path, mode="r", password=password)

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        with _map_py7zr_errors(self._path, self._password):
            infos = self._archive.list()
        for info in infos:
            name = info.filename.replace("\\", "/")
            uncompressed = info.uncompressed or 0
            # 솔리드 블록의 마지막 파일이 아닌 경우 compressed가 None으로 나올 수 있어
            # 그 경우 uncompressed로 대체한다(비율 1.0 취급, 압축폭탄 오탐 방지 목적).
            compressed = info.compressed if info.compressed is not None else uncompressed
            modified_at = info.creationtime.timestamp() if info.creationtime else None
            entries.append(
                ArchiveEntry(
                    name=name,
                    size=uncompressed,
                    compressed_size=compressed,
                    is_dir=info.is_directory,
                    # py7zr 0.22 기준 FileInfo가 심볼릭 링크 플래그를 노출하지 않으므로
                    # 항상 False로 취급한다(WHY: 라이브러리 한계, 추후 업그레이드 시 재검토).
                    is_symlink=False,
                    modified_at=modified_at,
                )
            )
        return entries

    def _validate_all(
        self, destination: pathlib.Path
    ) -> list[tuple[ArchiveEntry, pathlib.Path]]:
        entries = self.list_entries()
        manifest = ArchiveManifest(entries=entries, format_name="7z")
        policy = ArchiveSecurityPolicy()
        # all-or-nothing 사전 검증: py7zr 자체도 내부적으로 일부 검증을 하지만,
        # 우리 정책 레이어를 통과시키는 것이 요구사항이므로 extractall() 호출 전에 먼저 검사한다.
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
        with _map_py7zr_errors(self._path, self._password):
            self._archive.extractall(path=destination)

        total = len(validated)
        for done, (entry, _target_path) in enumerate(validated, start=1):
            if on_progress is not None:
                on_progress(entry.name, done, total)

    def extract_one(self, entry_name: str, destination: pathlib.Path) -> None:
        destination = pathlib.Path(destination)
        entries = self.list_entries()
        entry = next((e for e in entries if e.name == entry_name), None)
        if entry is None:
            raise KeyError(f"아카이브에 존재하지 않는 엔트리입니다: {entry_name}")

        policy = ArchiveSecurityPolicy()
        # 검증에 실패하면 예외가 전파되고, 아래 실제 extract() 호출은 실행되지 않는다.
        policy.validate_entry(entry, destination)

        destination.mkdir(parents=True, exist_ok=True)
        with _map_py7zr_errors(self._path, self._password):
            self._archive.extract(path=destination, targets=[entry_name])

    def close(self) -> None:
        self._archive.close()


class SevenZipArchiveWriter:
    """py7zr을 사용하는 7Z 압축 어댑터. password 지정 시 진짜 AES-256 암호화를 적용한다."""

    def __init__(
        self,
        path: pathlib.Path,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
    ) -> None:
        self._path = pathlib.Path(path)
        self._password = password
        # 압축 레벨 세밀 조정은 py7zr filters로 가능하나, 요구사항에 필터 커스터마이징이
        # 명시되지 않아 최소 구현에서는 기본 LZMA2 필터를 그대로 사용한다.
        self._compression_level = compression_level
        self._archive = py7zr.SevenZipFile(
            self._path,
            mode="w",
            password=password,
            header_encryption=bool(password),
        )

    def add_files(
        self,
        paths: list[pathlib.Path],
        on_progress: ProgressCallback | None = None,
    ) -> None:
        total = len(paths)
        for done, raw_path in enumerate(paths, start=1):
            path = pathlib.Path(raw_path)
            # writeall은 파일/디렉터리 모두 재귀적으로 처리한다.
            self._archive.writeall(path, arcname=path.name)
            if on_progress is not None:
                on_progress(path.name, done, total)

    def close(self) -> None:
        self._archive.close()
