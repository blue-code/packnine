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
import tempfile
import time
import zipfile

import pyzipper

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import CorruptedArchiveError, InvalidPasswordError
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy
from packnine.domain.file_filter import ExcludeFilter
from packnine.domain.value_objects import CompressionLevel, VolumeSize
from packnine.infrastructure import libarchive_tool, source_walk, volume_io


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


_UTF8_FLAG = 0x800  # general purpose bit 11: 파일명이 UTF-8임을 나타내는 zip 표준 플래그

# 멤버 하나를 디스크로 옮길 때 쓰는 버퍼 크기.
# shutil 기본값(64KB)은 기가바이트급 동영상에서 호출 횟수만 불필요하게 늘린다.
_COPY_CHUNK = 1024 * 1024

_ENCRYPTED_FLAG = 0x1  # general purpose bit 0: 엔트리가 암호화돼 있음
_WZ_AES_COMPRESS_TYPE = 99  # WinZip AES는 압축 방식 99로 표시된다(구형 ZipCrypto와 구분)


def _copy_with_progress(
    src,
    dst,
    entry_name: str,
    already_written: int,
    total_bytes: int,
    on_progress: ProgressCallback | None,
) -> int:
    """멤버 하나를 옮기면서 중간에도 진행률을 올린다. 옮긴 바이트 수를 돌려준다.

    엔트리가 끝날 때만 보고하면 6GB짜리 동영상 하나를 푸는 동안 막대가 제자리에
    멈춰 있다. 사용자 눈에는 멈춘 것과 구분되지 않는다.
    """
    written = 0
    while True:
        chunk = src.read(_COPY_CHUNK)
        if not chunk:
            break
        dst.write(chunk)
        written += len(chunk)
        if on_progress is not None and total_bytes > 0:
            on_progress(entry_name, min(already_written + written, total_bytes), total_bytes)
    return written


def _decode_legacy_filename(info: zipfile.ZipInfo) -> str:
    """UTF-8 플래그가 없는 엔트리명의 원래 인코딩을 자동 감지해 복원한다.

    zipfile은 플래그 없는 이름을 무조건 cp437로 디코딩하는데, 알집/구형 도구가 만든
    zip은 실제로는 cp949 바이트라 한글이 깨진다. cp437은 256바이트 전부에 1:1 대응하는
    문자가 있어 encode('cp437')로 원본 바이트를 무손실 복원할 수 있고, 그 바이트를
    UTF-8 → cp949 순으로 재판별한다(반디집의 "코드 페이지 자동 감지"에 대응).
    """
    if info.flag_bits & _UTF8_FLAG:
        return info.filename
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError:
        # cp437 왕복이 안 되는 이름은 zipfile이 이미 다른 경로로 디코딩한 것 - 그대로 둔다.
        return info.filename
    for codec in ("utf-8", "cp949"):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return info.filename


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
        # 분할 첫 볼륨(.zip.001)이면 볼륨 묶음을 하나의 파일 객체로 열어 넘긴다.
        # 라이브러리는 파일 객체를 닫지 않으므로 close()에서 우리가 직접 닫는다.
        self._volume_source = (
            volume_io.open_volume_source(self._path) if volume_io.is_first_volume(self._path) else None
        )
        source = self._volume_source if self._volume_source is not None else self._path
        try:
            self._zf = pyzipper.AESZipFile(source, mode="r")
        except (pyzipper.BadZipFile, zipfile.BadZipFile) as exc:
            if self._volume_source is not None:
                self._volume_source.close()
            raise CorruptedArchiveError(f"ZIP 파일이 손상되었습니다: {self._path}") from exc
        if self._password_bytes is not None:
            self._zf.setpassword(self._password_bytes)
        # 자동 감지로 복원한 표시용 이름 -> zipfile 내부(cp437) 이름 매핑.
        # 해제 시 zf.open()에는 내부 이름을 넘겨야 실제 엔트리를 찾을 수 있다.
        self._stored_names: dict[str, str] = {}

    def _stored_name(self, display_name: str) -> str:
        return self._stored_names.get(display_name, display_name)

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for info in self._zf.infolist():
            display_name = _decode_legacy_filename(info)
            if display_name != info.filename:
                self._stored_names[display_name] = info.filename
            entries.append(
                ArchiveEntry(
                    name=display_name,
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

    def uses_legacy_zipcrypto(self) -> bool:
        """구형 ZipCrypto로 암호화된 엔트리가 있는지 본다.

        플래그 0번 비트는 "암호화됨"만 알려 줄 뿐 방식까지는 알려 주지 않는다.
        AES(WinZip AES)는 0x9901 확장 필드로 구분하는데, pyzipper가 그 필드를 읽어
        wz_aes_version에 담아 두고 compress_type은 원래 압축 방식(보통 8)으로
        되돌려 놓는다. 그래서 compress_type==99로는 걸러지지 않는다.

        둘을 구분하는 이유는 속도가 전혀 다르기 때문이다. AES는 pycryptodome(C)로
        209MB/s가 나오지만, ZipCrypto는 순수 파이썬이라 1.4MB/s다(실측).
        """
        for info in self._zf.infolist():
            if not info.flag_bits & _ENCRYPTED_FLAG:
                continue
            if getattr(info, "wz_aes_version", None) is not None:
                continue
            if info.compress_type == _WZ_AES_COMPRESS_TYPE:
                continue
            return True
        return False

    def _should_delegate(self) -> pathlib.Path | None:
        """bsdtar에 넘길 상황이면 그 실행 파일 경로를, 아니면 None을 돌려준다."""
        if self._password is None or self._volume_source is not None:
            # 비밀번호가 없으면 위임할 이유가 없고, 분할 볼륨은 우리가 하나로 이어
            # 붙여 연 파일 객체라 외부 도구에 경로로 넘길 수 없다.
            return None
        if not self.uses_legacy_zipcrypto():
            return None
        return libarchive_tool.find_tool()

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
            _open_member(self._zf, self._stored_name(first_file.name), self._password_bytes).close()

        destination.mkdir(parents=True, exist_ok=True)

        tool = self._should_delegate()
        if tool is not None:
            self._extract_all_delegated(tool, destination, validated, on_progress)
            return

        total_bytes = sum(entry.size for entry, _ in validated if not entry.is_dir)
        written = 0
        for entry, target_path in validated:
            if entry.is_dir:
                target_path.mkdir(parents=True, exist_ok=True)
                if on_progress is not None:
                    on_progress(entry.name, min(written, total_bytes), total_bytes)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with _open_member(self._zf, self._stored_name(entry.name), self._password_bytes) as src:
                with target_path.open("wb") as dst:
                    written += _copy_with_progress(
                        src, dst, entry.name, written, total_bytes, on_progress
                    )
            if on_progress is not None and entry.size == 0:
                # 빈 파일은 복사 중 보고가 한 번도 없다. 목록에서 빠지지 않게 챙긴다.
                on_progress(entry.name, min(written, total_bytes), total_bytes)

    def _extract_all_delegated(
        self,
        tool: pathlib.Path,
        destination: pathlib.Path,
        validated: list[tuple[ArchiveEntry, pathlib.Path]],
        on_progress: ProgressCallback | None,
    ) -> None:
        """bsdtar로 풀되, 검증을 통과한 엔트리만 목적지에 남긴다.

        외부 도구는 우리 보안 정책을 모른다. 그래서 목적지에 직접 쓰게 두지 않고
        우리가 만든 staging 폴더에만 풀게 한 뒤, _validate_all이 계산해 둔 안전한
        경로로만 옮긴다. staging에 있지만 검증 목록에 없는 것은 그대로 버려진다.

        staging은 목적지와 같은 볼륨에 둔다. 그래야 옮기는 단계가 rename이라 7GB를
        한 번 더 복사하지 않는다.
        """
        staging_parent = destination.parent if destination.parent.exists() else destination
        staging = pathlib.Path(tempfile.mkdtemp(prefix="packnine_fast_", dir=staging_parent))
        try:
            total_bytes = sum(entry.size for entry, _ in validated if not entry.is_dir)
            libarchive_tool.extract_zip(
                tool,
                self._path,
                staging,
                self._password or "",
                total_bytes=total_bytes,
                on_progress=on_progress,
            )

            for entry, target_path in validated:
                if entry.is_dir:
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                source = staging / entry.name
                if not source.is_file():
                    # 도구가 내놓지 않은 엔트리는 조용히 건너뛴다(빈 파일을 만들지 않는다).
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if target_path.exists():
                    target_path.unlink()
                shutil.move(str(source), str(target_path))
        finally:
            shutil.rmtree(staging, ignore_errors=True)

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
            with _open_member(self._zf, self._stored_name(entry.name), self._password_bytes) as src:
                with target_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, _COPY_CHUNK)

    def close(self) -> None:
        self._zf.close()
        if self._volume_source is not None:
            self._volume_source.close()


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
        volume_size: VolumeSize | None = None,
        exclude_filter: ExcludeFilter | None = None,
    ) -> None:
        self._exclude_filter = exclude_filter or ExcludeFilter()
        self._path = pathlib.Path(path)
        self._password = password
        # 실제로 만들어진 첫 파일 경로와 볼륨 수. 분할하지 않으면 지정 경로 그대로이고,
        # 분할했더라도 결과가 한 조각이면 close()에서 .001을 떼어 지정 경로가 된다.
        self.output_path = self._path
        self.volume_count = 1
        self._volume_target = (
            volume_io.open_volume_target(self._path, volume_size) if volume_size is not None else None
        )
        target = self._volume_target if self._volume_target is not None else self._path

        if compression_level == CompressionLevel.STORE:
            compression = zipfile.ZIP_STORED
            compresslevel = None
        else:
            compression = zipfile.ZIP_DEFLATED
            compresslevel = int(compression_level)  # zlib deflate는 0~9 스케일과 동일

        if password:
            self._zf: zipfile.ZipFile = pyzipper.AESZipFile(
                target,
                mode="w",
                compression=compression,
                compresslevel=compresslevel,
                encryption=pyzipper.WZ_AES,
            )
            self._zf.setpassword(password.encode("utf-8"))
        else:
            self._zf = zipfile.ZipFile(
                target, mode="w", compression=compression, compresslevel=compresslevel
            )

    def add_files(
        self,
        paths: list[pathlib.Path],
        on_progress: ProgressCallback | None = None,
    ) -> None:
        # 진행률 total을 정확히 계산하려면, 디렉터리를 먼저 파일 목록으로 평탄화해야 한다.
        # 평탄화와 제외 패턴 적용은 세 어댑터가 공유한다(source_walk).
        file_list = source_walk.collect_files(paths, self._exclude_filter)

        total = len(file_list)
        for done, (file_path, arcname) in enumerate(file_list, start=1):
            self._zf.write(file_path, arcname=arcname)
            if on_progress is not None:
                on_progress(arcname, done, total)

    def close(self) -> None:
        self._zf.close()
        if self._volume_target is not None:
            self._volume_target.close()
            self.output_path, self.volume_count = volume_io.finalize_volumes(self._path)
