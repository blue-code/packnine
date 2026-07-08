"""CompressDialog 스모크 테스트 - 위젯에 값을 직접 세팅해 get_result()를 검증한다."""
from __future__ import annotations

import pathlib

from packnine.domain.value_objects import CompressionLevel
from packnine.presentation.gui.compress_dialog import CompressDialog


def test_get_result_returns_values_entered_by_user(qtbot, tmp_path):
    initial_file = tmp_path / "a.txt"
    initial_file.write_text("hello", encoding="utf-8")

    dialog = CompressDialog(initial_files=[initial_file])
    qtbot.addWidget(dialog)

    destination = tmp_path / "out.zip"
    dialog._destination_edit.setText(str(destination))
    dialog._level_slider.setValue(9)
    dialog._password_edit.setText("secret")
    dialog._password_confirm_edit.setText("secret")

    source_paths, result_destination, password, level = dialog.get_result()

    assert source_paths == [initial_file]
    assert result_destination == destination
    assert password == "secret"
    assert level == CompressionLevel.MAXIMUM


def test_initial_files_prefill_file_list(qtbot, tmp_path):
    files = [tmp_path / "a.txt", tmp_path / "b.txt"]
    for f in files:
        f.write_text("x", encoding="utf-8")

    dialog = CompressDialog(initial_files=files)
    qtbot.addWidget(dialog)

    assert dialog._file_list.count() == 2
    listed = {pathlib.Path(dialog._file_list.item(i).text()) for i in range(2)}
    assert listed == set(files)


def test_password_mismatch_blocks_accept(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    # QMessageBox.warning은 모달이라 테스트가 멈추므로, 호출 여부만 확인하도록 대체한다.
    warning_calls = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: warning_calls.append(args)
    )

    dialog = CompressDialog(initial_files=[tmp_path / "a.txt"])
    qtbot.addWidget(dialog)

    dialog._destination_edit.setText(str(tmp_path / "out.zip"))
    dialog._password_edit.setText("secret")
    dialog._password_confirm_edit.setText("different")

    # _on_accept는 검증 실패 시 accept()를 호출하지 않아야 한다(다이얼로그가 닫히지 않음).
    dialog._on_accept()

    assert warning_calls, "비밀번호 불일치 시 경고가 표시되어야 한다"
    assert dialog.result() != CompressDialog.DialogCode.Accepted
