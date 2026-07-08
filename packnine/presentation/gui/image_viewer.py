"""아카이브 내부 이미지를 바로 미리 보는 내장 뷰어.

이미 로컬 디스크(임시 폴더)에 해제된 이미지 파일 경로 목록을 받아 보여주기만 한다.
압축 해제 자체는 MainWindow가 ExtractService.extract_entries()로 미리 수행한다
(이 다이얼로그는 표시 책임만 진다 - application 서비스를 직접 호출하지 않는다).
"""
from __future__ import annotations

import pathlib

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# QPixmap이 플러그인 없이 안정적으로 읽을 수 있는 포맷만 뷰어 대상으로 삼는다.
# WEBP/HEIC 등은 Qt 빌드에 따라 지원 여부가 갈려 실패 시 크래시 대신 빈 화면만 보일 수 있다.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif")


def is_image_name(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(ext) for ext in IMAGE_EXTENSIONS)


class ImageViewerDialog(QDialog):
    """이미지 목록을 이전/다음 버튼과 방향키로 넘겨보는 간단한 뷰어."""

    def __init__(self, image_paths: list[pathlib.Path], start_index: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PackNine 이미지 뷰어")
        self.resize(800, 600)

        self._image_paths = image_paths
        self._index = max(0, min(start_index, len(image_paths) - 1)) if image_paths else 0

        self._image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(200, 200)
        self._name_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)

        self._prev_button = QPushButton("< 이전")
        self._prev_button.clicked.connect(self._show_previous)
        self._next_button = QPushButton("다음 >")
        self._next_button.clicked.connect(self._show_next)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self._prev_button)
        nav_layout.addWidget(self._name_label, stretch=1)
        nav_layout.addWidget(self._next_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._image_label, stretch=1)
        layout.addLayout(nav_layout)

        self._render_current()

    def _show_previous(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render_current()

    def _show_next(self) -> None:
        if self._index < len(self._image_paths) - 1:
            self._index += 1
            self._render_current()

    def _render_current(self) -> None:
        total = len(self._image_paths)
        if total == 0:
            self._name_label.setText("표시할 이미지가 없습니다")
            self._prev_button.setEnabled(False)
            self._next_button.setEnabled(False)
            return

        path = self._image_paths[self._index]
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._image_label.setText(f"이미지를 불러올 수 없습니다: {path.name}")
            self._image_label.setPixmap(QPixmap())
        else:
            scaled = pixmap.scaled(
                self._image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)

        self._name_label.setText(f"{path.name}  ({self._index + 1} / {total})")
        self._prev_button.setEnabled(self._index > 0)
        self._next_button.setEnabled(self._index < total - 1)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 네이밍 컨벤션 유지
        super().resizeEvent(event)
        self._render_current()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Left:
            self._show_previous()
        elif event.key() == Qt.Key.Key_Right:
            self._show_next()
        else:
            super().keyPressEvent(event)
