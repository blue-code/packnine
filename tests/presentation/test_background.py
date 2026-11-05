"""background.run_blocking 테스트 - GUI가 멈추지 않게 하는 실행기의 계약 검증.

여기서 지키려는 것은 두 가지다.
1. 작업은 호출 스레드(=GUI 스레드)가 아닌 곳에서 돌아야 한다. 그래야 큰 파일을
   처리하는 동안에도 창이 계속 그려진다.
2. 진행률 콜백은 반대로 반드시 GUI 스레드에서 불려야 한다. 작업 스레드에서 위젯을
   건드리면 모달 진행률 창의 setValue가 내부에서 processEvents를 부르며 그대로
   멈춰 버린다(실제로 한 번 겪은 교착이라 테스트로 못 박아 둔다).
"""
from __future__ import annotations

import threading

import pytest

from packnine.presentation.gui import background


def test_operation_runs_off_the_calling_thread(qtbot) -> None:
    caller = threading.get_ident()
    seen: dict[str, int] = {}

    def operation(report) -> None:
        seen["worker"] = threading.get_ident()

    background.run_blocking(operation)

    assert seen["worker"] != caller


def test_progress_callback_runs_on_the_calling_thread(qtbot) -> None:
    caller = threading.get_ident()
    reported: list[tuple[str, int, int, int]] = []

    def operation(report) -> None:
        report("파일.txt", 1, 2)
        report("파일2.txt", 2, 2)

    def on_progress(name: str, done: int, total: int) -> None:
        reported.append((name, done, total, threading.get_ident()))

    background.run_blocking(operation, on_progress)

    assert [(n, d, t) for n, d, t, _ in reported] == [
        ("파일.txt", 1, 2),
        ("파일2.txt", 2, 2),
    ]
    # 콜백이 작업 스레드에서 불리면 위젯 갱신이 교착을 만든다.
    assert all(thread_id == caller for *_, thread_id in reported)


def test_exception_is_raised_at_the_call_site(qtbot) -> None:
    class Boom(Exception):
        pass

    def operation(report) -> None:
        raise Boom("실패")

    # 호출부의 기존 try/except 구조를 그대로 쓸 수 있어야 한다.
    with pytest.raises(Boom, match="실패"):
        background.run_blocking(operation)


def test_returns_even_when_operation_finishes_instantly(qtbot) -> None:
    """작업이 루프에 들어가기도 전에 끝나도 멈추지 않아야 한다(경쟁 조건 회귀)."""
    for _ in range(20):
        background.run_blocking(lambda report: None)
