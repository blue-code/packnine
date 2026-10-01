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

    source_paths, result_destination, password, level, volume_size, _ = dialog.get_result()

    assert source_paths == [initial_file]
    assert result_destination == destination
    assert password == "secret"
    assert level == CompressionLevel.MAXIMUM
    # 분할을 건드리지 않았으면 분할 없음(None)이어야 기존 동작이 그대로다.
    assert volume_size is None


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


def test_initial_destination_prefills_output_path_and_format(qtbot, tmp_path):
    # 우클릭 "PackNine으로 압축하기..."는 목적지를 미리 계산해 넘긴다 - 사용자가 매번
    # 출력 경로를 직접 타이핑하지 않아도 바로 확인만 하면 되게 한다.
    initial_file = tmp_path / "a.txt"
    initial_file.write_text("hello", encoding="utf-8")
    destination = tmp_path / "a.7z"

    dialog = CompressDialog(initial_files=[initial_file], initial_destination=destination)
    qtbot.addWidget(dialog)

    assert dialog._destination_edit.text() == str(destination)
    # 확장자와 포맷 콤보가 어긋나면 _on_format_changed가 경로를 덮어써 혼란스럽다.
    assert dialog._format_combo.currentText() == ".7z"

    source_paths, result_destination, _, _, volume_size, _ = dialog.get_result()
    assert source_paths == [initial_file]
    assert result_destination == destination
    assert volume_size is None


def test_initial_destination_with_unknown_extension_keeps_path(qtbot, tmp_path):
    # 콤보에 없는 확장자(.zipx 등)를 넘겨도 경로는 그대로 유지되어야 한다.
    destination = tmp_path / "a.unknown"

    dialog = CompressDialog(initial_destination=destination)
    qtbot.addWidget(dialog)

    assert dialog._destination_edit.text() == str(destination)


def _preset_index(label_keyword: str) -> int:
    from packnine.domain.value_objects import SPLIT_PRESETS

    for offset, preset in enumerate(SPLIT_PRESETS):
        if label_keyword in preset.label:
            return offset + 1  # 0번은 "분할 안 함"
    raise AssertionError(f"프리셋을 찾을 수 없음: {label_keyword}")


def test_split_preset_fills_spinbox_and_result_carries_volume_size(qtbot, tmp_path):
    dialog = CompressDialog(initial_files=[tmp_path / "a.txt"], initial_destination=tmp_path / "a.7z")
    qtbot.addWidget(dialog)

    dialog._split_combo.setCurrentIndex(_preset_index("네이버 메일 일반첨부"))

    assert dialog._volume_spin.isEnabled()
    assert dialog._volume_spin.value() == 10
    _, _, _, _, volume_size, _ = dialog.get_result()
    assert volume_size is not None
    assert volume_size.megabytes == 10


def test_editing_spinbox_after_preset_switches_to_custom(qtbot, tmp_path):
    dialog = CompressDialog(initial_destination=tmp_path / "a.7z")
    qtbot.addWidget(dialog)

    dialog._split_combo.setCurrentIndex(_preset_index("다음 메일 일반첨부"))
    dialog._volume_spin.setValue(30)

    # 숫자를 고치면 더 이상 그 프리셋이 아니므로 "사용자 지정"으로 표시되고 값은 유지된다.
    assert dialog._split_combo.currentText() == "사용자 지정..."
    assert dialog.selected_volume_size().megabytes == 30


def test_tar_format_disables_split_and_yields_none(qtbot, tmp_path):
    dialog = CompressDialog(initial_destination=tmp_path / "a.zip")
    qtbot.addWidget(dialog)
    dialog._split_combo.setCurrentIndex(_preset_index("Gmail"))

    dialog._format_combo.setCurrentText(".tar.gz")

    assert not dialog._split_combo.isEnabled()
    assert not dialog._volume_spin.isEnabled()
    assert dialog.get_result()[4] is None

    # zip으로 돌아오면 이전 선택이 그대로 살아난다.
    dialog._format_combo.setCurrentText(".zip")
    assert dialog._split_combo.isEnabled()
    assert dialog.get_result()[4].megabytes == 25


def test_zip_split_shows_compatibility_note_but_7z_does_not(qtbot, tmp_path):
    dialog = CompressDialog(initial_destination=tmp_path / "a.zip")
    qtbot.addWidget(dialog)

    dialog._split_combo.setCurrentIndex(_preset_index("네이버 메일 대용량첨부"))
    assert "탐색기" in dialog._split_note_label.text()

    dialog._format_combo.setCurrentText(".7z")
    assert "탐색기" not in dialog._split_note_label.text()
    # 프리셋 안내는 포맷과 무관하게 남는다.
    assert "2GB" in dialog._split_note_label.text()


def test_split_combo_lists_every_preset_with_tooltip(qtbot):
    from PySide6.QtCore import Qt

    from packnine.domain.value_objects import SPLIT_PRESETS

    dialog = CompressDialog()
    qtbot.addWidget(dialog)

    labels = [dialog._split_combo.itemText(i) for i in range(dialog._split_combo.count())]
    assert labels[0] == "분할 안 함"
    assert labels[-1] == "사용자 지정..."
    assert labels[1:-1] == [p.label for p in SPLIT_PRESETS]
    for i, preset in enumerate(SPLIT_PRESETS, start=1):
        assert dialog._split_combo.itemData(i, Qt.ItemDataRole.ToolTipRole) == preset.note


def test_exclude_field_becomes_filter_in_result(qtbot, tmp_path):
    # 옵션 창에 적은 제외 패턴이 압축에 그대로 전달되어야 한다.
    dialog = CompressDialog()
    qtbot.addWidget(dialog)
    dialog._exclude_edit.setText(".git, node_modules, *.tmp")

    exclude_filter = dialog.get_result()[5]

    assert exclude_filter.patterns == (".git", "node_modules", "*.tmp")


def test_empty_exclude_field_filters_nothing(qtbot):
    # 빈 입력이 "전부 제외"로 해석되면 빈 아카이브가 만들어진다 - 반드시 비어 있어야 한다.
    dialog = CompressDialog()
    qtbot.addWidget(dialog)

    assert dialog.get_result()[5].is_empty
