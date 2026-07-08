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
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from packnine.domain.value_objects import CompressionLevel

# 포맷 콤보박스에 노출할 확장자 목록 (7z_adapter/tar_adapter/zip_adapter가 지원하는 것 중
# "쓰기" 가능한 것만 - RAR은 라이선스상 쓰기 미지원이라 제외)
_FORMAT_EXTENSIONS = [".zip", ".7z", ".tar", ".tar.gz", ".tar.bz2", ".tar.xz"]


class CompressDialog(QDialog):
    """압축 대상/출력 경로/옵션을 입력받는 모달 다이얼로그."""

    def __init__(
        self,
        initial_files: list[pathlib.Path] | None = None,
        parent=None,
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

        form_layout = QFormLayout()
        form_layout.addRow("출력 경로", destination_layout)
        form_layout.addRow("포맷", self._format_combo)
        form_layout.addRow("압축 강도", level_layout)
        form_layout.addRow("비밀번호", self._password_edit)
        form_layout.addRow("비밀번호 확인", self._password_confirm_edit)

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
        # 이미 경로가 입력된 상태에서 포맷을 바꾸면 확장자도 함께 갱신한다.
        current = self._destination_edit.text()
        if not current:
            return
        for ext in _FORMAT_EXTENSIONS:
            if current.lower().endswith(ext):
                self._destination_edit.setText(current[: -len(ext)] + new_ext)
                return
        self._destination_edit.setText(current + new_ext)

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
    ) -> tuple[list[pathlib.Path], pathlib.Path, str | None, CompressionLevel]:
        """다이얼로그 입력값을 (소스경로들, 출력경로, 비밀번호, 압축강도)로 반환한다."""
        source_paths = [
            pathlib.Path(self._file_list.item(i).text())
            for i in range(self._file_list.count())
        ]
        destination = pathlib.Path(self._destination_edit.text().strip())
        password = self._password_edit.text() or None
        compression_level = _closest_compression_level(self._level_slider.value())
        return source_paths, destination, password, compression_level


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
