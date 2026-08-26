"""selection_collector 테스트.

탐색기는 "%1" verb를 선택 항목마다 프로세스 하나씩 띄운다. 그 다중 프로세스 상황을
스레드로 흉내내어, 대표(leader) 하나만 살아남고 나머지 경로가 그 대표에게 합쳐지는지
검증한다. 실제 파일 락을 쓰므로 session_dir을 tmp_path로 격리해 개발자의 실제
%LOCALAPPDATA%\\PackNine을 건드리지 않는다.
"""
from __future__ import annotations

import os
import threading
import time

from packnine.application import selection_collector


def test_single_caller_becomes_leader_and_returns_its_own_paths(tmp_path):
    result = selection_collector.collect_selection(
        [r"C:\work\a.txt"],
        window_seconds=0.05,
        session_dir=tmp_path / "pending",
    )

    assert result == [r"C:\work\a.txt"]


def test_follower_returns_none_and_leader_merges_all_paths(tmp_path):
    session_dir = tmp_path / "pending"
    leader_result: dict[str, list[str] | None] = {}

    def run_leader() -> None:
        leader_result["value"] = selection_collector.collect_selection(
            ["a.txt"], window_seconds=0.6, session_dir=session_dir
        )

    leader_thread = threading.Thread(target=run_leader)
    leader_thread.start()
    # 대표가 락을 잡을 시간을 준 뒤 뒤따라 들어온 프로세스를 흉내낸다.
    time.sleep(0.15)
    follower = selection_collector.collect_selection(
        ["b.txt"], window_seconds=0.6, session_dir=session_dir
    )
    leader_thread.join(timeout=10)

    # 뒤따라온 쪽은 다이얼로그를 띄우지 않고 조용히 빠져야 한다(창 중복 방지).
    assert follower is None
    assert sorted(leader_result["value"] or []) == ["a.txt", "b.txt"]


def test_leader_after_window_leaves_no_residue_so_next_run_works(tmp_path):
    session_dir = tmp_path / "pending"

    first = selection_collector.collect_selection(
        ["a.txt"], window_seconds=0.05, session_dir=session_dir
    )
    second = selection_collector.collect_selection(
        ["b.txt"], window_seconds=0.05, session_dir=session_dir
    )

    # 앞선 실행이 락/임시 파일을 남기면 다음 우클릭이 영영 응답하지 않는다(회귀 금지).
    assert first == ["a.txt"]
    assert second == ["b.txt"]


def test_stale_lock_is_reclaimed(tmp_path):
    session_dir = tmp_path / "pending"
    session_dir.mkdir(parents=True)
    lock_path = session_dir / selection_collector._LOCK_NAME
    lock_path.write_text("", encoding="utf-8")
    # 강제 종료 등으로 남은 오래된 락은 무시하고 새 대표가 나와야 한다.
    stale_time = time.time() - 3600
    os.utime(lock_path, (stale_time, stale_time))

    result = selection_collector.collect_selection(
        ["a.txt"],
        window_seconds=0.05,
        session_dir=session_dir,
        stale_after_seconds=60.0,
    )

    assert result == ["a.txt"]


def test_duplicate_paths_are_collapsed(tmp_path):
    result = selection_collector.collect_selection(
        ["a.txt", "a.txt", "b.txt"],
        window_seconds=0.05,
        session_dir=tmp_path / "pending",
    )

    assert result == ["a.txt", "b.txt"]
