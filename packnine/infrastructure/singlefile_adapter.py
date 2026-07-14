"""tar가 아닌 순수 단일 파일 압축(.gz/.bz2/.xz) 해제 어댑터.

이 포맷들은 "아카이브"가 아니라 파일 하나를 통째로 압축한 것이라 엔트리가 항상
하나뿐이고, 원본 크기를 헤더에서 신뢰할 수 있게 알 방법이 없다(gzip의 ISIZE는
32비트 모듈러 값). 그래서 압축폭탄 방어를 메타데이터 사전 검증 대신 해제 스트리밍
중의 실쓰기 바이트 상한으로 수행한다.

쓰기(단일 파일 압축 생성)는 지원하지 않는다 - ZIP/7Z/TAR 계열로 충분하고,
반디집 대응 기본 기능은 "해제"이기 때문이다.
"""
from __future__ import annotations

import bz2
import gzip
import lzma
import pathlib

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import CorruptedArchiveError, UnsafeArchiveEntryError
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.security_policy import ArchiveSecurityPolicy

_OPENERS = {
    ".gz": gzip.open,
    ".bz2": bz2.open,
    ".xz": lzma.open,
}

# 해제 중 라이브러리가 던질 수 있는 "손상 파일" 예외 모음.
# gzip.BadGzipFile은 OSError의 하위 클래스, lzma/bz2는 각각 고유 예외를 쓴다.
_CORRUPTION_ERRORS = (OSError, EOFError, lzma.LZMAError, ValueError)

# 압축 크기가 아주 작은 정상 파일(짧은 텍스트 등)이 비율 상한에 억울하게 걸리지 않도록
# 이 크기까지는 비율과 무관하게 허용한다. 폭탄은 이 값을 훨씬 넘어서므로 방어에 지장 없다.
_RATIO_FLOOR_BYTES = 10 * 1024 * 1024

_CHUNK_SIZE = 1024 * 1024


class SingleFileArchiveReader:
    """gzip/bz2/lzma 표준 라이브러리를 사용하는 단일 파일 해제 어댑터."""

    def __init__(self, path: pathlib.Path, password: str | None = None) -> None:
        # 이 포맷들은 암호화를 지원하지 않으므로 password는 무시한다(시그니처 통일용).
        self._path = pathlib.Path(path)
        suffix = self._path.suffix.lower()
        if suffix not in _OPENERS:
            raise CorruptedArchiveError(f"단일 파일 압축 확장자가 아닙니다: {self._path.name}")
        self._suffix = suffix
        if not self._path.exists():
            raise FileNotFoundError(f"파일이 존재하지 않습니다: {self._path}")

    def _entry_name(self) -> str:
        # notes.txt.gz -> notes.txt, archive.gz -> archive
        return self._path.name[: -len(self._suffix)]

    def list_entries(self) -> list[ArchiveEntry]:
        compressed = self._path.stat().st_size
        return [
            ArchiveEntry(
                name=self._entry_name(),
                # 원본 크기는 해제 전에는 알 수 없다(아키텍처 원칙상 트레일러를 직접
                # 파싱하지 않는다 - test_architecture_constraints 참고). 0으로 표시한다.
                size=0,
                compressed_size=compressed,
                is_dir=False,
                is_symlink=False,
                modified_at=self._path.stat().st_mtime,
            )
        ]

    def extract_all(
        self,
        destination: pathlib.Path,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        destination = pathlib.Path(destination)
        entries = self.list_entries()
        entry = entries[0]

        policy = ArchiveSecurityPolicy()
        policy.validate_manifest(ArchiveManifest(entries=entries, format_name=self._suffix))
        target_path = policy.validate_entry(entry, destination)

        compressed = entry.compressed_size
        # 스트리밍 상한: 압축 크기 x 정책 비율, 단 소형 파일 하한(_RATIO_FLOOR_BYTES) 보장.
        max_bytes = max(int(compressed * policy.max_compression_ratio), _RATIO_FLOOR_BYTES)

        destination.mkdir(parents=True, exist_ok=True)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        try:
            with _OPENERS[self._suffix](self._path, "rb") as src:
                with target_path.open("wb") as dst:
                    while True:
                        chunk = src.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes:
                            raise UnsafeArchiveEntryError(
                                entry.name,
                                f"해제 크기가 허용 상한({max_bytes} bytes)을 초과했습니다"
                                " (압축폭탄 의심)",
                            )
                        dst.write(chunk)
                        if on_progress is not None:
                            # 전체 크기를 모르는 포맷이라 done==total로 두고 이름만 갱신한다.
                            on_progress(entry.name, written, written)
        except UnsafeArchiveEntryError:
            target_path.unlink(missing_ok=True)  # 중단된 부분 파일을 남기지 않는다
            raise
        except _CORRUPTION_ERRORS as exc:
            target_path.unlink(missing_ok=True)
            raise CorruptedArchiveError(f"압축 파일이 손상되었습니다: {self._path}") from exc

        if on_progress is not None:
            on_progress(entry.name, written or 1, written or 1)

    def extract_one(self, entry_name: str, destination: pathlib.Path) -> None:
        if entry_name != self._entry_name():
            raise KeyError(f"아카이브에 존재하지 않는 엔트리입니다: {entry_name}")
        self.extract_all(destination)

    def close(self) -> None:
        # 열린 핸들을 유지하지 않으므로 정리할 자원이 없다.
        pass
