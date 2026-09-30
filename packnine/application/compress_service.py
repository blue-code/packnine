"""압축 유스케이스 오케스트레이션.

application 계층은 domain의 포트(interfaces)만 알고, 실제 구현체는
format_registry를 통해서만 얻는다(개별 어댑터 클래스를 직접 import하지 않는다).
"""
from __future__ import annotations

import concurrent.futures
import dataclasses
import os
import pathlib
from typing import Callable

from packnine.application import smart_naming
from packnine.domain.entities import ArchiveManifest
from packnine.domain.file_filter import ExcludeFilter
from packnine.domain.interfaces import ProgressCallback
from packnine.domain.value_objects import CompressionLevel, VolumeSize
from packnine.infrastructure import format_registry

# 항목별 압축을 몇 개까지 동시에 돌릴지의 상한. 코어를 전부 쓰면 체감 반응성이 나빠지고
# 디스크가 병목인 구간에서는 오히려 느려져서, 코어 수와 이 값 중 작은 쪽을 쓴다.
_MAX_PARALLEL_ITEMS = 8


@dataclasses.dataclass(frozen=True)
class EachCompressResult:
    """compress_each()의 항목 하나에 대한 결과.

    하나가 실패해도 나머지는 계속 진행해야 하므로 예외를 던지지 않고 error에 담아 돌려준다
    (우클릭 "각각 압축하기"에서 파일 하나가 잠겨 있다고 전체가 중단되면 안 된다).
    """

    source: pathlib.Path
    destination: pathlib.Path
    manifest: ArchiveManifest | None = None
    error: Exception | None = None


def _resolve_worker_count(item_count: int, max_workers: int | None) -> int:
    if max_workers is not None:
        return max(1, min(max_workers, item_count))
    return max(1, min(item_count, os.cpu_count() or 1, _MAX_PARALLEL_ITEMS))


class CompressService:
    """여러 소스 경로를 하나의 아카이브로 압축하는 유스케이스."""

    def compress(
        self,
        source_paths: list[pathlib.Path],
        destination: pathlib.Path,
        *,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
        volume_size: VolumeSize | None = None,
        exclude_filter: ExcludeFilter | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        """source_paths를 destination으로 압축하고 결과 목록을 돌려준다.

        volume_size를 주면 `destination.001`, `.002` … 볼륨으로 나눠 쓴다. 결과가 볼륨
        하나에 들어가면 `.001` 없이 destination 그대로 저장되므로, 실제 파일 경로는 반환된
        manifest.archive_path로 확인해야 한다.
        """
        destination = pathlib.Path(destination)

        # writer를 만들기(=대상 파일을 여는 시점) 전에 소스 존재 여부를 먼저 검증한다.
        # 그래야 존재하지 않는 소스로 인해 빈 아카이브 파일이 생성되는 일이 없다.
        for source_path in source_paths:
            if not pathlib.Path(source_path).exists():
                raise FileNotFoundError(f"압축할 소스 경로가 존재하지 않습니다: {source_path}")

        # 해제(extract)가 대상 폴더를 자동 생성하는 것과 동일하게, 출력 아카이브의
        # 부모 폴더도 없으면 만들어 준다. 우클릭 메뉴의 --dest-dir처럼 아직 없는
        # 폴더가 목적지로 들어와도 FileNotFoundError로 죽지 않아야 한다.
        # (소스 검증보다 뒤에 두어, 잘못된 요청에서는 빈 폴더가 생기지 않게 한다)
        destination.parent.mkdir(parents=True, exist_ok=True)

        # RAR 확장자면 get_writer가 UnsupportedFormatError를 던지며,
        # 여기서는 그대로 전파시킨다(RAR 쓰기는 라이선스상 미지원).
        writer = format_registry.get_writer(
            destination,
            password=password,
            compression_level=compression_level,
            volume_size=volume_size,
            exclude_filter=exclude_filter,
        )
        writer.add_files(list(source_paths), on_progress=on_progress)
        writer.close()

        # 호출자가 결과를 바로 요약할 수 있도록, 방금 만든 아카이브를 다시 열어 목록을 읽는다.
        # 분할했으면 첫 볼륨(.001)을 열어야 하므로 writer가 확정한 실제 경로를 쓴다.
        reader = format_registry.get_reader(writer.output_path, password=password)
        try:
            entries = reader.list_entries()
        finally:
            reader.close()

        return ArchiveManifest(
            entries=entries,
            format_name=destination.suffix,
            archive_path=writer.output_path,
            volume_count=writer.volume_count,
        )

    def compress_each(
        self,
        source_paths: list[pathlib.Path],
        *,
        dest_dir: pathlib.Path | None = None,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
        max_workers: int | None = None,
        on_item_start: Callable[[pathlib.Path], None] | None = None,
        on_item_done: Callable[[pathlib.Path, int, int], None] | None = None,
    ) -> list[EachCompressResult]:
        """항목들을 하나로 묶지 않고 항목별로 각각 압축한다("각각 압축하기").

        항목끼리는 서로 독립적이라 동시에 돌릴 수 있다. zlib/lzma는 압축하는 동안 GIL을
        놓으므로 스레드만으로도 실제로 여러 코어를 쓴다(프로세스 풀은 경로 직렬화/시작
        비용만 늘고 이득이 없다). 단일 아카이브 내부의 병렬화는 별개 문제다 - zipfile에
        이미 압축된 블록을 밀어 넣는 공개 API가 없고, 로컬 헤더를 직접 쓰는 것은 바이너리
        수동 조립 금지 원칙(SECURITY.md 6번)에 걸린다.

        결과는 입력 순서 그대로 돌려주고, 실패한 항목은 예외 대신 error 필드에 담는다.
        """
        sources = [pathlib.Path(p) for p in source_paths]
        if not sources:
            return []

        # 목적지 이름은 병렬 진입 전에 순차로 확정한다. 파일이 아직 없는 상태에서 워커들이
        # 각자 이름을 고르면 서로 같은 이름을 집어갈 수 있다(다른 폴더의 동명 파일을
        # 한 폴더에 모아 압축하는 경우).
        destinations: list[pathlib.Path] = []
        for source in sources:
            auto = smart_naming.resolve_smart_compress_destination([source])
            candidate = (dest_dir / auto.name) if dest_dir is not None else auto
            destinations.append(
                smart_naming.resolve_unique_file_path(candidate, taken=destinations)
            )

        total = len(sources)
        done_count = 0
        results: list[EachCompressResult | None] = [None] * total

        def run_one(index: int) -> None:
            source = sources[index]
            destination = destinations[index]
            if on_item_start is not None:
                on_item_start(source)
            try:
                manifest = self.compress(
                    [source],
                    destination,
                    password=password,
                    compression_level=compression_level,
                )
            except Exception as exc:  # noqa: BLE001 - 항목 하나의 실패로 전체를 멈추지 않는다
                results[index] = EachCompressResult(source, destination, error=exc)
            else:
                results[index] = EachCompressResult(source, destination, manifest=manifest)

        workers = _resolve_worker_count(total, max_workers)
        if workers == 1:
            for index in range(total):
                run_one(index)
                done_count += 1
                if on_item_done is not None:
                    on_item_done(sources[index], done_count, total)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(run_one, index): index for index in range(total)}
                for future in concurrent.futures.as_completed(futures):
                    future.result()  # run_one은 예외를 삼키므로 여기 오는 건 진짜 버그다
                    done_count += 1
                    if on_item_done is not None:
                        # 완료 보고는 완료된 순서대로 나간다(진행률 표시용).
                        on_item_done(sources[futures[future]], done_count, total)

        return [result for result in results if result is not None]

    def smart_compress(
        self,
        source_paths: list[pathlib.Path],
        *,
        password: str | None = None,
        compression_level: CompressionLevel = CompressionLevel.NORMAL,
        on_progress: ProgressCallback | None = None,
    ) -> ArchiveManifest:
        """반디집 "알아서 압축"처럼 목적지 경로를 자동으로 정해 바로 압축한다.

        목적지 이름 결정 규칙은 smart_naming에 위임하고, 실제 압축은 기존 compress()를
        그대로 재사용한다(로직 중복 금지).
        """
        destination = smart_naming.resolve_smart_compress_destination(source_paths)
        return self.compress(
            source_paths,
            destination,
            password=password,
            compression_level=compression_level,
            on_progress=on_progress,
        )
