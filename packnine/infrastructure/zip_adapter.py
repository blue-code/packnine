"""pyzipper(zipfile 포크) 기반 ZIP 어댑터.

ArchiveReader/ArchiveWriter Protocol(packnine.domain.interfaces)을 구조적으로
만족시키는 구현체이며, 해제 시 ArchiveSecurityPolicy로 전체 엔트리를 사전
검증(all-or-nothing)한 뒤에만 실제 디스크에 쓴다.

표준 zipfile 대신 pyzipper를 쓰는 이유: 표준 라이브러리는 암호화 zip을 "읽기"만
지원(그마저 legacy ZipCrypto뿐)하고 "쓰기"는 아예 불가능하다. 초기 구현은 password를
받아놓고 조용히 무시했는데, 사용자는 암호가 걸렸다고 믿게 되는 최악의 동작이라
pyzipper로 교체해 AES-256 쓰기/읽기를 모두 지원한다(반디집/7-Zip과 호환).
"""
from __future__ import annotations

import pathlib
import shutil
import stat
import time
import zipfile

import pyzipper

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import CorruptedArchiveError, InvalidPasswordError
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy
from packnine.domain.value_objects import CompressionLevel


def _is_symlink_zipinfo(info: zipfile.ZipInfo) -> bool:
    """external_attr 상위 16비트(유닉스 모드)에서 심볼릭 링크 여부를 판단한다.

    external_attr는 유닉스 계열 도구가 만든 zip에만 의미 있는 값이 들어 있고,
    Windows 도구가 만든 zip은 0인 경우가 많으므로 0이면 무조건 False로 취급한다.
    """
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode == 0:
        return False
    return stat.S_ISLNK(mode)


def _to_timestamp(date_time: tuple[int, int, int, int, int, int]) -> float | None:
    try:
        return time.mktime((*date_time, 0, 0, -1))
    except (ValueError, OverflowError):
        return None


def _open_member(zf: zipfile.ZipFile, name: str, password_bytes: bytes | None):
    """멤버 스트림을 열되, 라이브러리 예외를 도메인 예외로 변환한다.

    pyzipper/zipfile은 암호 문제를 RuntimeError("Bad password...", "...password
    required...")로 던지므로 메시지 기반으로 판별할 수밖에 없다(전용 예외 클래스가 없음).
    """
    try:
        return zf.open(name, pwd=password_bytes)
    except RuntimeError as exc:
        message = str(exc).lower()
        if "password" in message or "encrypted" in message:
            raise InvalidPasswordError(
                f"비밀번호가 틀렸거나 필요합니다: {name}"
            ) from exc
        raise


class ZipArchiveReader:
    """pyzipper를 사용하는 ZIP 해제 어댑터(일반/ZipCrypto/AES zip 모두 읽는다)."""

    def __init__(self, path: pathlib.Path, password: str | None = None) -> None:
        self._path = pathlib.Path(path)
        self._password = password
        self._password_bytes = password.encode("utf-8") if password else None
        try:
            self._zf = pyzipper.AESZipFile(self._path, mode="r")
        except (pyzipper.BadZipFile, zipfile.BadZipFile) as exc:
            raise CorruptedArchiveError(f"ZIP 파일이 손상되었습니다: {self._path}") from exc
        if self._password_bytes is not None:
            self._zf.setpassword(self._password_bytes)

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for info in self._zf.infolist():
            entries.append(
                ArchiveEntry(
                    name=info.filename,
                    size=info.file_size,
                    compressed_size=info.compress_size,
                    is_dir=info.filename.endswith("/"),
                    is_symlink=_is_symlink_zipinfo(info),
                    modified_at=_to_timestamp(info.date_time),
                )
            )
        return entries

    def _validate_all(
        self, destination: pathlib.Path
    ) -> list[tuple[ArchiveEntry, pathlib.Path]]:
        entries = self.list_entries()
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        policy = ArchiveSecurityPolicy()
        # all-or-nothing: 실제로 디스크에 쓰기 전에 전체 목록/각 엔트리를 먼저 검증한다.
        # 여기서 예외가 나면 아래 실제 쓰기 루프는 절대 실행되지 않는다.
        policy.validate_manifest(manifest)
        return [(entry, policy.validate_entry(entry, destination)) for entry in entries]

    def extract_all(
        self,
        destination: pathlib.Path,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        destination = pathlib.Path(destination)
        validated = self._validate_all(destination)

        # 암호 오류는 디스크에 무언가 쓰기 전에 잡아야 한다(all-or-nothing).
        # AES zip은 open 시점에 password verifier를 검사하므로, 첫 파일 엔트리를
        # 열어보는 것만으로 실제 해제 전에 암호를 사전 검증할 수 있다.
        first_file = next((entry for entry, _ in validated if not entry.is_dir), None)
        if first_file is not None:
            _open_member(self._zf, first_file.name, self._password_bytes).close()

        destination.mkdir(parents=True, exist_ok=True)
        total = len(validated)
        for done, (entry, target_path) in enumerate(validated, start=1):
            if entry.is_dir:
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with _open_member(self._zf, entry.name, self._password_bytes) as src:
                    with target_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
            if on_progress is not None:
                on_progress(entry.name, done, total)

    def extract_one(self, entry_name: str, destination: pathlib.Path) -> None:
        destination = pathlib.Path(destination)
        entries = self.list_entries()
        entry = next((e for e in entries if e.name == entry_name), None)
        if entry is None:
            raise KeyError(f"아카이브에 존재하지 않는 엔트리입니다: {entry_name}")

        policy = ArchiveSecurityPolicy()
        target_path = policy.validate_entry(entry, destination)

        destination.mkdir(parents=True, exist_ok=True)
        if entry.is_dir:
            target_path.mkdir(parents=True, exist_ok=True)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with _open_member(self._zf, entry.name, self._password_bytes) as src:
                with target_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

    def close(self) -> None:
        self._zf.close()


class ZipArchiveWriter:
    """pyzipper를 사용하는 ZIP 압축 어댑터.

    password가 주어지면 AES-256으로 실제 암호화한다(WZ_AES - 반디집/7-Zip/WinRAR과
    호환되는 WinZip AES 방식). 무암호일 때는 표준 zipfile과 동일한 일반 zip을 만든다.
    """

    def __init__(
        self,
        path: pathlib.Path,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
    ) -> None:
        self._path = pathlib.Path(path)
        self._password = password

        if compression_level == CompressionLevel.STORE:
            compression = zipfile.ZIP_STORED
            compresslevel = None
        else:
            compression = zipfile.ZIP_DEFLATED
            compresslevel = int(compression_level)  # zlib deflate는 0~9 스케일과 동일

        if password:
            self._zf: zipfile.ZipFile = pyzipper.AESZipFile(
                self._path,
                mode="w",
                compression=compression,
                compresslevel=compresslevel,
                encryption=pyzipper.WZ_AES,
            )
            self._zf.setpassword(password.encode("utf-8"))
        else:
            self._zf = zipfile.ZipFile(
                self._path, mode="w", compression=compression, compresslevel=compresslevel
            )

    def add_files(
        self,
        paths: list[pathlib.Path],
        on_progress: ProgressCallback | None = None,
    ) -> None:
        # 진행률 total을 정확히 계산하려면, 디렉터리를 먼저 파일 목록으로 평탄화해야 한다.
        file_list: list[tuple[pathlib.Path, str]] = []
        for raw_path in paths:
            path = pathlib.Path(raw_path)
            if path.is_dir():
                for file_path in sorted(path.rglob("*")):
                    if file_path.is_file():
                        arcname = f"{path.name}/{file_path.relative_to(path).as_posix()}"
                        file_list.append((file_path, arcname))
            else:
                file_list.append((path, path.name))

        total = len(file_list)
        for done, (file_path, arcname) in enumerate(file_list, start=1):
            self._zf.write(file_path, arcname=arcname)
            if on_progress is not None:
                on_progress(arcname, done, total)

    def close(self) -> None:
        self._zf.close()
