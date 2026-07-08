"""표준 tarfile 기반 TAR 어댑터.

.tar / .tar.gz(.tgz) / .tar.bz2 / .tar.xz 를 모두 지원한다.
tar 포맷은 자체적으로 암호화를 지원하지 않으므로, 이 어댑터의 생성자는
format_registry에서 다른 어댑터와 동일한 시그니처로 호출할 수 있도록
password 인자를 받기만 하고 실제로는 사용하지 않는다.
"""
from __future__ import annotations

import pathlib
import tarfile

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import UnsupportedFormatError
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy
from packnine.domain.value_objects import CompressionLevel


def _resolve_write_open_kwargs(path: pathlib.Path, compression_level: CompressionLevel) -> dict:
    """확장자를 보고 tarfile.open에 넘길 쓰기 모드를 결정한다.

    복합 확장자(.tar.gz 등)를 먼저 검사해야 .tar 단일 확장자에 잘못 매칭되지 않는다.
    """
    name = path.name.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        # gzip만 tarfile.open을 통해 compresslevel을 직접 받을 수 있어 여기서만 반영한다
        # (bz2/xz는 tarfile.open 경유 시 compresslevel 인자를 지원하지 않아 기본값 사용).
        return {"mode": "w:gz", "compresslevel": int(compression_level)}
    if name.endswith(".tar.bz2"):
        return {"mode": "w:bz2"}
    if name.endswith(".tar.xz"):
        return {"mode": "w:xz"}
    if name.endswith(".tar"):
        return {"mode": "w"}
    raise UnsupportedFormatError(f"지원하지 않는 tar 확장자입니다: {path.name}")


class TarArchiveReader:
    """표준 tarfile을 사용하는 TAR 계열 해제 어댑터."""

    def __init__(self, path: pathlib.Path, password: str | None = None) -> None:
        # tar는 암호화를 지원하지 않으므로 password는 무시한다(레지스트리 시그니처 통일용).
        self._path = pathlib.Path(path)
        self._tf = tarfile.open(self._path, mode="r:*")

    def list_entries(self) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for member in self._tf.getmembers():
            entries.append(
                ArchiveEntry(
                    name=member.name,
                    size=member.size,
                    # tar/gz/bz2/xz는 스트림 전체가 하나로 압축되는 솔리드 포맷이라
                    # 멤버별 압축 후 크기를 알 수 없다. size로 대체해 비율을 1.0으로
                    # 두어 압축폭탄 오탐을 피한다(WHY: 포맷 자체의 한계).
                    compressed_size=member.size,
                    is_dir=member.isdir(),
                    is_symlink=member.issym() or member.islnk(),
                    modified_at=float(member.mtime) if member.mtime is not None else None,
                )
            )
        return entries

    def _validate_all(
        self, destination: pathlib.Path
    ) -> list[tuple[ArchiveEntry, pathlib.Path]]:
        entries = self.list_entries()
        manifest = ArchiveManifest(entries=entries, format_name="tar")
        policy = ArchiveSecurityPolicy()
        policy.validate_manifest(manifest)
        return [(entry, policy.validate_entry(entry, destination)) for entry in entries]

    def extract_all(
        self,
        destination: pathlib.Path,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        destination = pathlib.Path(destination)
        # all-or-nothing: 우리 SecurityPolicy를 먼저 전체 통과시킨다.
        validated = self._validate_all(destination)

        destination.mkdir(parents=True, exist_ok=True)
        total = len(validated)
        for done, (entry, _target_path) in enumerate(validated, start=1):
            # 우리 정책 통과 후에도 표준 라이브러리 data filter(3.12+)로 한 번 더 방어한다.
            self._tf.extract(entry.name, path=destination, filter="data")
            if on_progress is not None:
                on_progress(entry.name, done, total)

    def extract_one(self, entry_name: str, destination: pathlib.Path) -> None:
        destination = pathlib.Path(destination)
        entries = self.list_entries()
        entry = next((e for e in entries if e.name == entry_name), None)
        if entry is None:
            raise KeyError(f"아카이브에 존재하지 않는 엔트리입니다: {entry_name}")

        policy = ArchiveSecurityPolicy()
        policy.validate_entry(entry, destination)

        destination.mkdir(parents=True, exist_ok=True)
        self._tf.extract(entry_name, path=destination, filter="data")

    def close(self) -> None:
        self._tf.close()


class TarArchiveWriter:
    """표준 tarfile을 사용하는 TAR 계열 압축 어댑터."""

    def __init__(
        self,
        path: pathlib.Path,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
    ) -> None:
        # tar는 암호화를 지원하지 않으므로 password는 무시한다(레지스트리 시그니처 통일용).
        self._path = pathlib.Path(path)
        open_kwargs = _resolve_write_open_kwargs(self._path, compression_level)
        self._tf = tarfile.open(self._path, **open_kwargs)

    def add_files(
        self,
        paths: list[pathlib.Path],
        on_progress: ProgressCallback | None = None,
    ) -> None:
        total = len(paths)
        for done, raw_path in enumerate(paths, start=1):
            path = pathlib.Path(raw_path)
            # tarfile.add는 기본적으로 재귀(recursive=True)이므로 디렉터리도 통째로 담긴다.
            self._tf.add(path, arcname=path.name)
            if on_progress is not None:
                on_progress(path.name, done, total)

    def close(self) -> None:
        self._tf.close()
