"""CompressService.compress_each 테스트 - 항목별 병렬 압축("각각 압축하기").

압축 자체는 zlib/lzma가 GIL을 놓고 도는 구간이라 스레드로도 실제 코어를 나눠 쓴다.
여기서는 속도(측정은 머신마다 흔들림)가 아니라 계약을 검증한다: 결과 순서, 목적지
규칙, 부분 실패 허용, 동시 실행 여부.
"""
from __future__ import annotations

import pathlib
import threading

from packnine.application.compress_service import CompressService
from packnine.domain.value_objects import CompressionLevel


def _make_source(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    path = tmp_path / name
    # 압축률 검사(압축폭탄 방어)에 걸리지 않도록 적당히 반복되는 텍스트를 쓴다.
    path.write_text(f"{name} 내용 " * 50, encoding="utf-8")
    return path


def test_each_source_becomes_its_own_archive(tmp_path):
    sources = [_make_source(tmp_path, f"f{i}.txt") for i in range(3)]

    results = CompressService().compress_each(sources)

    # 결과는 입력 순서를 그대로 유지해야 한다(병렬로 돌아도 보고 순서는 안정적이어야
    # 사용자가 "몇 번째가 실패했는지" 알 수 있다).
    assert [r.source for r in results] == sources
    for result, source in zip(results, sources):
        assert result.error is None
        assert result.destination == tmp_path / f"{source.stem}.zip"
        assert result.destination.exists()
        assert result.manifest is not None and len(result.manifest.entries) == 1


def test_dest_dir_places_archives_in_that_folder(tmp_path):
    sources = [_make_source(tmp_path, "a.txt"), _make_source(tmp_path, "b.txt")]
    dest_dir = tmp_path / "out"

    results = CompressService().compress_each(sources, dest_dir=dest_dir)

    assert [r.destination for r in results] == [dest_dir / "a.zip", dest_dir / "b.zip"]
    assert all(r.destination.exists() for r in results)


def test_existing_name_gets_numeric_suffix(tmp_path):
    source = _make_source(tmp_path, "a.txt")
    (tmp_path / "a.zip").write_text("기존 파일", encoding="utf-8")

    results = CompressService().compress_each([source])

    # 기존 파일을 덮어쓰지 않아야 한다.
    assert results[0].destination == tmp_path / "a_2.zip"
    assert (tmp_path / "a.zip").read_text(encoding="utf-8") == "기존 파일"


def test_one_failure_does_not_stop_the_others(tmp_path):
    good = _make_source(tmp_path, "good.txt")
    missing = tmp_path / "없는파일.txt"

    results = CompressService().compress_each([missing, good])

    assert isinstance(results[0].error, FileNotFoundError)
    assert results[0].manifest is None
    assert results[1].error is None
    assert results[1].destination.exists()


def test_password_and_level_are_applied(tmp_path):
    import pytest

    from packnine.application.extract_service import ExtractService
    from packnine.domain.exceptions import InvalidPasswordError

    source = _make_source(tmp_path, "secret.txt")

    results = CompressService().compress_each(
        [source], password="pw1234", compression_level=CompressionLevel.MAXIMUM
    )

    archive = results[0].destination
    # zip은 목록(중앙 디렉터리)이 암호화되지 않으므로 list는 성공한다. 실제 내용 해제가
    # 비밀번호 없이 실패해야 암호가 걸린 것이다.
    with pytest.raises(InvalidPasswordError):
        ExtractService().extract(archive, tmp_path / "out")

    ExtractService().extract(archive, tmp_path / "ok", password="pw1234")
    assert (tmp_path / "ok" / "secret.txt").exists()


def test_items_run_concurrently_when_workers_allow(tmp_path):
    # 실제로 동시에 도는지 확인한다 - 순차 실행이면 배리어에서 영원히 대기한다.
    sources = [_make_source(tmp_path, f"c{i}.txt") for i in range(3)]
    barrier = threading.Barrier(3, timeout=10)
    observed: list[str] = []

    def on_item_start(source: pathlib.Path) -> None:
        barrier.wait()  # 3개가 모두 시작해야 통과한다
        observed.append(source.name)

    results = CompressService().compress_each(
        sources, max_workers=3, on_item_start=on_item_start
    )

    assert len(observed) == 3
    assert all(r.error is None for r in results)


def test_single_worker_still_works(tmp_path):
    sources = [_make_source(tmp_path, f"s{i}.txt") for i in range(2)]

    results = CompressService().compress_each(sources, max_workers=1)

    assert all(r.error is None and r.destination.exists() for r in results)


def test_progress_reports_completed_item_count(tmp_path):
    sources = [_make_source(tmp_path, f"p{i}.txt") for i in range(3)]
    seen: list[tuple[int, int]] = []
    lock = threading.Lock()

    def on_item_done(source, done, total):
        with lock:
            seen.append((done, total))

    CompressService().compress_each(sources, on_item_done=on_item_done)

    # 완료 보고는 1/3, 2/3, 3/3 세 번(순서는 완료 순이라 정렬해서 비교).
    assert sorted(seen) == [(1, 3), (2, 3), (3, 3)]
