"""MainWindow 스모크 테스트 - 실제 파일 다이얼로그는 모킹하고 기본 구조만 확인한다."""
from __future__ import annotations

import pathlib

from PySide6.QtWidgets import QFileDialog, QMessageBox

from packnine.presentation.gui.main_window import MainWindow


def test_main_window_creates_with_toolbar_actions(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "PackNine"
    assert window.action_compress is not None
    assert window.action_compress.text() == "압축하기"
    assert window.action_open.text() == "열기"
    assert window.action_extract.text() == "압축풀기"
    assert window.action_test.text() == "테스트"


def test_open_archive_populates_table(qtbot, tmp_path, monkeypatch):
    # 실제 InspectService.compress round-trip으로 아카이브를 하나 만든다.
    from packnine.application.compress_service import CompressService

    src_file = tmp_path / "a.txt"
    src_file.write_text("hello", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_file], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)

    # QFileDialog는 실제로 띄우지 않고 경로만 즉시 반환하도록 모킹한다.
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (str(archive_path), "")
    )

    window._on_open()

    assert window._current_archive_path == archive_path
    assert window._table.rowCount() == 1
    assert window._table.item(0, 0).text() == "a.txt"


def test_open_missing_archive_shows_error_without_crash(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)

    critical_calls = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: critical_calls.append(args)
    )

    window._open_archive(tmp_path / "does_not_exist.zip")

    assert critical_calls, "존재하지 않는 아카이브를 열면 오류 다이얼로그가 표시되어야 한다"
    assert window._current_archive_path is None


def test_drop_archive_file_opens_it_directly(qtbot, tmp_path):
    from packnine.application.compress_service import CompressService

    src_file = tmp_path / "a.txt"
    src_file.write_text("hello", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_file], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)

    # dropEvent가 내부적으로 호출하는 _open_archive를 직접 검증(실제 QDropEvent 생성은
    # 플랫폼 의존적이라 회피하고, 판별 로직 자체는 _is_archive_path로 별도 검증한다).
    from packnine.presentation.gui.main_window import _is_archive_path

    assert _is_archive_path(archive_path) is True
    assert _is_archive_path(src_file) is False

    window._open_archive(archive_path)
    assert window._current_archive_path == archive_path
    assert window._table.rowCount() == 1
