"""quick_progress 헬퍼 테스트 - 우클릭 "압축풀기"의 비밀번호 재시도 흐름 검증."""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog

from packnine.domain.exceptions import InvalidPasswordError
from packnine.presentation.gui import quick_progress


def test_password_retry_prompts_until_correct(qtbot, monkeypatch):
    attempts: list[str | None] = []

    def operation(on_progress, password):
        attempts.append(password)
        if password != "pw123":
            raise InvalidPasswordError("비밀번호가 틀렸습니다")

    # 첫 프롬프트에서 틀린 암호, 두 번째에서 맞는 암호를 입력하는 사용자 시나리오.
    answers = iter([("wrong", True), ("pw123", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))

    ok = quick_progress.run_extract_with_password_retry("해제 중", operation)

    assert ok is True
    # 최초 시도(None) → wrong → pw123 순으로 3번 실행되어야 한다.
    assert attempts == [None, "wrong", "pw123"]


def test_password_retry_cancel_returns_false_without_error_dialog(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    def operation(on_progress, password):
        raise InvalidPasswordError("비밀번호가 필요합니다")

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    critical_calls: list = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: critical_calls.append(a))

    ok = quick_progress.run_extract_with_password_retry("해제 중", operation)

    assert ok is False
    # 사용자 취소는 오류가 아니므로 에러 다이얼로그를 띄우지 않는다.
    assert critical_calls == []
