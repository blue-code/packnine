"""최근 연 아카이브 목록 저장소 테스트.

목록은 사용자 편의용이라 깨져도 앱이 죽으면 안 된다 - 파일이 없거나 내용이 망가졌을 때
빈 목록으로 조용히 넘어가는지를 특히 확인한다.
"""
from __future__ import annotations

import pathlib

from packnine.infrastructure import recent_files


def _store(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "recent.json"


def test_remember_puts_newest_first(tmp_path):
    store = _store(tmp_path)
    first = tmp_path / "a.zip"
    second = tmp_path / "b.zip"
    for path in (first, second):
        path.write_text("x", encoding="utf-8")

    recent_files.remember(first, store_path=store)
    recent_files.remember(second, store_path=store)

    assert recent_files.load(store_path=store) == [second, first]


def test_remembering_again_moves_it_to_front_without_duplicating(tmp_path):
    store = _store(tmp_path)
    first = tmp_path / "a.zip"
    second = tmp_path / "b.zip"
    for path in (first, second):
        path.write_text("x", encoding="utf-8")

    recent_files.remember(first, store_path=store)
    recent_files.remember(second, store_path=store)
    recent_files.remember(first, store_path=store)

    assert recent_files.load(store_path=store) == [first, second]


def test_list_is_capped(tmp_path):
    store = _store(tmp_path)
    paths = []
    for index in range(recent_files.MAX_ENTRIES + 5):
        path = tmp_path / f"f{index}.zip"
        path.write_text("x", encoding="utf-8")
        paths.append(path)
        recent_files.remember(path, store_path=store)

    loaded = recent_files.load(store_path=store)
    assert len(loaded) == recent_files.MAX_ENTRIES
    # 가장 최근 것이 앞에 오고, 오래된 것부터 밀려난다.
    assert loaded[0] == paths[-1]


def test_missing_files_are_dropped_on_load(tmp_path):
    store = _store(tmp_path)
    alive = tmp_path / "alive.zip"
    alive.write_text("x", encoding="utf-8")
    gone = tmp_path / "gone.zip"
    gone.write_text("x", encoding="utf-8")

    recent_files.remember(gone, store_path=store)
    recent_files.remember(alive, store_path=store)
    gone.unlink()

    # 지워진 파일이 메뉴에 남아 있으면 눌렀을 때 오류만 본다.
    assert recent_files.load(store_path=store) == [alive]


def test_missing_store_returns_empty_list(tmp_path):
    assert recent_files.load(store_path=tmp_path / "없는파일.json") == []


def test_corrupted_store_returns_empty_list_instead_of_raising(tmp_path):
    store = _store(tmp_path)
    store.write_text("{망가진 JSON", encoding="utf-8")

    assert recent_files.load(store_path=store) == []


def test_clear_empties_the_list(tmp_path):
    store = _store(tmp_path)
    path = tmp_path / "a.zip"
    path.write_text("x", encoding="utf-8")
    recent_files.remember(path, store_path=store)

    recent_files.clear(store_path=store)

    assert recent_files.load(store_path=store) == []
