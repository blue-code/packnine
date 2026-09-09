"""압축 옵션을 입력받는 다이얼로그.

이 모듈은 QFileDialog로 실제 다이얼로그를 띄우는 것 외에는 서비스 계층을
호출하지 않는다 - 실제 CompressService 호출은 MainWindow가 get_result()로
받은 값을 가지고 수행한다(다이얼로그는 입력값 수집만 책임진다).
"""
from __future__ import annotations

import pathlib

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from packnine.domain.value_objects import SPLIT_PRESETS, CompressionLevel, VolumeSize

# 포맷 콤보박스에 노출할 확장자 목록 (7z_adapter/tar_adapter/zip_adapter가 지원하는 것 중
# "쓰기" 가능한 것만 - RAR은 라이선스상 쓰기 미지원이라 제외)
_FORMAT_EXTENSIONS = [".zip", ".7z", ".tar", ".tar.gz", ".tar.bz2", ".tar.xz"]
# 분할 압축을 지원하는 포맷(format_registry._VOLUME_CAPABLE_EXTENSIONS와 같아야 한다.
# infrastructure를 import하지 않으려고 여기서 따로 둔다).
_SPLITTABLE_EXTENSIONS = (".zip", ".7z")

# 분할 콤보의 고정 항목. 프리셋은 SPLIT_PRESETS에서 그 사이에 채운다.
_SPLIT_NONE_LABEL = "분할 안 함"
_SPLIT_CUSTOM_LABEL = "사용자 지정..."
# 스핀박스 상한. 다음 대용량(4095MB)보다 크게 잡되 무의미하게 큰 값은 막는다(64GB).
_MAX_VOLUME_MEGABYTES = 65536
_ZIP_SPLIT_NOTE = (
    "zip 분할은 7-Zip 방식(.zip.001)입니다. 반디집·7-Zip·알집으로 열 수 있지만 "
    "Windows 탐색기 기본 압축 풀기로는 열리지 않습니다. 받는 쪽을 모르면 7z를 권장합니다."
)


class CompressDialog(QDialog):
    """압축 대상/출력 경로/옵션을 입력받는 모달 다이얼로그."""

    def __init__(
        self,
        initial_files: list[pathlib.Path] | None = None,
        parent=None,
        initial_destination: pathlib.Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("압축하기")
        self.resize(480, 420)

        self._file_list = QListWidget()
        for path in initial_files or []:
            self._file_list.addItem(str(path))

        add_button = QPushButton("파일 추가")
        add_button.clicked.connect(self._on_add_files)
        remove_button = QPushButton("선택 제거")
        remove_button.clicked.connect(self._on_remove_selected)

        file_buttons_layout = QHBoxLayout()
        file_buttons_layout.addWidget(add_button)
        file_buttons_layout.addWidget(remove_button)

        self._destination_edit = QLineEdit()
        destination_button = QPushButton("찾아보기...")
        destination_button.clicked.connect(self._on_browse_destination)
        destination_layout = QHBoxLayout()
        destination_layout.addWidget(self._destination_edit)
        destination_layout.addWidget(destination_button)

        self._format_combo = QComboBox()
        self._format_combo.addItems(_FORMAT_EXTENSIONS)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)

        self._level_slider = QSlider(Qt.Orientation.Horizontal)
        self._level_slider.setRange(0, 9)
        self._level_slider.setValue(int(CompressionLevel.NORMAL))
        self._level_label = QLabel(str(self._level_slider.value()))
        self._level_slider.valueChanged.connect(
            lambda value: self._level_label.setText(str(value))
        )
        level_layout = QHBoxLayout()
        level_layout.addWidget(self._level_slider)
        level_layout.addWidget(self._level_label)

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_confirm_edit = QLineEdit()
        self._password_confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # 분할 압축: 콤보(프리셋)로 MB 스핀박스를 채우고, 실제 값은 항상 스핀박스가 기준이다.
        # 메일 한도는 바뀌므로 프리셋은 단축키일 뿐 사용자가 숫자를 고쳐 쓸 수 있어야 한다.
        self._split_combo = QComboBox()
        self._split_combo.addItem(_SPLIT_NONE_LABEL)
        for index, preset in enumerate(SPLIT_PRESETS, start=1):
            self._split_combo.addItem(preset.label)
            self._split_combo.setItemData(index, preset.note, Qt.ItemDataRole.ToolTipRole)
        self._split_combo.addItem(_SPLIT_CUSTOM_LABEL)
        self._split_combo.currentIndexChanged.connect(self._on_split_changed)

        self._volume_spin = QSpinBox()
        self._volume_spin.setRange(1, _MAX_VOLUME_MEGABYTES)
        self._volume_spin.setSuffix(" MB")
        self._volume_spin.setValue(SPLIT_PRESETS[0].megabytes)
        self._volume_spin.setEnabled(False)
        self._volume_spin.valueChanged.connect(self._on_volume_edited)

        split_layout = QHBoxLayout()
        split_layout.addWidget(self._split_combo, 1)
        split_layout.addWidget(self._volume_spin)

        self._split_note_label = QLabel()
        self._split_note_label.setWordWrap(True)
        self._split_note_label.setStyleSheet("color: gray;")
        self._split_note_label.hide()

        form_layout = QFormLayout()
        form_layout.addRow("출력 경로", destination_layout)
        form_layout.addRow("포맷", self._format_combo)
        form_layout.addRow("압축 강도", level_layout)
        form_layout.addRow("비밀번호", self._password_edit)
        form_layout.addRow("비밀번호 확인", self._password_confirm_edit)
        form_layout.addRow("분할 압축", split_layout)
        form_layout.addRow("", self._split_note_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel("압축할 파일/폴더"))
        main_layout.addWidget(self._file_list)
        main_layout.addLayout(file_buttons_layout)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(button_box)

        if initial_destination is not None:
            self._apply_initial_destination(initial_destination)

    def _apply_initial_destination(self, destination: pathlib.Path) -> None:
        """미리 계산된 출력 경로를 채워 넣는다(우클릭 "압축하기..." 진입 경로).

        포맷 콤보를 먼저 맞춘 뒤 경로를 넣어야 한다 - 순서를 바꾸면 콤보 변경 시그널이
        _on_format_changed를 태워 방금 넣은 경로의 확장자를 다시 덮어쓴다.
        확장자는 ".tar.gz"처럼 두 단계인 것이 있으므로 긴 것부터 비교한다.
        """
        text = str(destination)
        for ext in sorted(_FORMAT_EXTENSIONS, key=len, reverse=True):
            if text.lower().endswith(ext):
                self._format_combo.setCurrentText(ext)
                break
        self._destination_edit.setText(text)

    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "압축할 파일 선택")
        for file_path in files:
            self._file_list.addItem(file_path)

    def _on_remove_selected(self) -> None:
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _on_browse_destination(self) -> None:
        ext = self._format_combo.currentText()
        path, _ = QFileDialog.getSaveFileName(self, "출력 아카이브 경로", filter=f"*{ext}")
        if path:
            # 사용자가 확장자를 입력하지 않았으면 현재 선택된 포맷을 붙여준다.
            if not path.lower().endswith(ext):
                path += ext
            self._destination_edit.setText(path)

    def _on_format_changed(self, new_ext: str) -> None:
        self._update_split_availability(new_ext)
        # 이미 경로가 입력된 상태에서 포맷을 바꾸면 확장자도 함께 갱신한다.
        current = self._destination_edit.text()
        if not current:
            return
        for ext in _FORMAT_EXTENSIONS:
            if current.lower().endswith(ext):
                self._destination_edit.setText(current[: -len(ext)] + new_ext)
                return
        self._destination_edit.setText(current + new_ext)

    # ------------------------------------------------------------------
    # 분할 압축
    # ------------------------------------------------------------------
    def _update_split_availability(self, ext: str) -> None:
        """tar 계열은 분할을 지원하지 않으므로 콤보/스핀박스를 함께 잠근다.

        포맷을 tar로 바꿨다가 다시 zip으로 돌아오면 이전 선택이 그대로 살아나도록
        값은 건드리지 않고 enabled 상태만 바꾼다.
        """
        splittable = ext in _SPLITTABLE_EXTENSIONS
        self._split_combo.setEnabled(splittable)
        self._volume_spin.setEnabled(splittable and self.is_split_enabled())
        self._refresh_split_note()

    def is_split_enabled(self) -> bool:
        return self._split_combo.currentIndex() != 0

    def _on_split_changed(self, index: int) -> None:
        if index == 0:
            self._volume_spin.setEnabled(False)
        else:
            preset_index = index - 1
            if preset_index < len(SPLIT_PRESETS):
                # 프리셋 값을 넣는 동안 valueChanged가 콤보를 "사용자 지정"으로 되돌리지 않게 막는다.
                self._volume_spin.blockSignals(True)
                self._volume_spin.setValue(SPLIT_PRESETS[preset_index].megabytes)
                self._volume_spin.blockSignals(False)
            self._volume_spin.setEnabled(self._split_combo.isEnabled())
        self._refresh_split_note()

    def _on_volume_edited(self, _value: int) -> None:
        # 프리셋을 고른 뒤 숫자를 손으로 바꾸면 더 이상 그 프리셋이 아니므로 "사용자 지정"으로 표시한다.
        if 0 < self._split_combo.currentIndex() <= len(SPLIT_PRESETS):
            self._split_combo.blockSignals(True)
            self._split_combo.setCurrentIndex(self._split_combo.count() - 1)
            self._split_combo.blockSignals(False)
            self._refresh_split_note()

    def _refresh_split_note(self) -> None:
        """프리셋 안내와 zip 분할 호환 경고를 상황에 맞게 보여준다."""
        if not self.is_split_enabled() or not self._split_combo.isEnabled():
            self._split_note_label.hide()
            return
        notes: list[str] = []
        preset_index = self._split_combo.currentIndex() - 1
        if preset_index < len(SPLIT_PRESETS):
            notes.append(SPLIT_PRESETS[preset_index].note)
        if self._format_combo.currentText() == ".zip":
            notes.append(_ZIP_SPLIT_NOTE)
        self._split_note_label.setText("\n".join(notes))
        self._split_note_label.setVisible(bool(notes))

    def selected_volume_size(self) -> VolumeSize | None:
        """분할을 켰을 때만 스핀박스 값을 VolumeSize로 돌려준다(tar처럼 잠겨 있으면 None)."""
        if not self.is_split_enabled() or not self._split_combo.isEnabled():
            return None
        return VolumeSize.from_megabytes(self._volume_spin.value())

    def _on_accept(self) -> None:
        if self._file_list.count() == 0:
            QMessageBox.warning(self, "입력 오류", "압축할 파일을 하나 이상 추가하세요.")
            return
        if not self._destination_edit.text().strip():
            QMessageBox.warning(self, "입력 오류", "출력 경로를 지정하세요.")
            return
        if self._password_edit.text() != self._password_confirm_edit.text():
            QMessageBox.warning(self, "입력 오류", "비밀번호와 비밀번호 확인이 일치하지 않습니다.")
            return
        self.accept()

    def get_result(
        self,
    ) -> tuple[
        list[pathlib.Path], pathlib.Path, str | None, CompressionLevel, VolumeSize | None
    ]:
        """다이얼로그 입력값을 (소스경로들, 출력경로, 비밀번호, 압축강도, 분할크기)로 반환한다.

        분할크기는 분할을 켜지 않았거나 포맷이 분할을 지원하지 않으면 None이다.
        """
        source_paths = [
            pathlib.Path(self._file_list.item(i).text())
            for i in range(self._file_list.count())
        ]
        destination = pathlib.Path(self._destination_edit.text().strip())
        password = self._password_edit.text() or None
        compression_level = _closest_compression_level(self._level_slider.value())
        return source_paths, destination, password, compression_level, self.selected_volume_size()


def _closest_compression_level(value: int) -> CompressionLevel:
    # 슬라이더는 0-9 연속값이지만 CompressionLevel은 STORE/FASTEST/NORMAL/MAXIMUM
    # 네 값만 있는 IntEnum이라 구간별로 가장 가까운 값에 매핑한다.
    if value <= CompressionLevel.STORE:
        return CompressionLevel.STORE
    if value <= CompressionLevel.FASTEST:
        return CompressionLevel.FASTEST
    if value <= CompressionLevel.NORMAL:
        return CompressionLevel.NORMAL
    return CompressionLevel.MAXIMUM
