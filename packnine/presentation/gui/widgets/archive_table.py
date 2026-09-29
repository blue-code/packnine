"""아카이브 내용 표 위젯 - 항목을 탐색기로 끌어내는 드래그 아웃을 담당한다.

탐색기는 드롭 대상에 "진짜 파일 경로"를 요구한다. 아카이브 안의 엔트리는 실체가 없으므로
드래그가 시작되는 순간 임시 폴더에 해제해 실체를 만들고, 그 경로를 file:// URL로 넘긴다
(반디집도 같은 방식이다). 실제 해제는 이 위젯이 하지 않고, 주입받은 materializer가
application 서비스를 통해 수행한다 - 위젯은 Qt 표현 계층에만 머무른다.

임시 파일은 드롭 대상이 복사를 끝낼 때까지 살아 있어야 하므로 여기서 지우지 않는다.
%TEMP% 아래에 두어 OS/사용자 정리에 맡긴다(대안인 "드래그 종료 시 삭제"는 탐색기가
비동기로 복사하는 경우 복사 실패를 유발한다).
"""
from __future__ import annotations

import pathlib
from typing import Callable

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTableWidget

# 표의 각 행이 들고 있는 데이터. _ROLE_PATH는 아카이브 내부 전체 경로("pics/photo.png"),
# _ROLE_KIND는 "file"/"folder"/"up"이다. main_window가 표를 채울 때 같은 롤을 쓴다.
ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_KIND = Qt.ItemDataRole.UserRole + 1

# 엔트리 경로들을 임시 폴더에 실체화하고, 끌어낼 실제 파일/폴더 경로를 돌려주는 함수.
DragMaterializer = Callable[[list[str]], list[pathlib.Path]]


class ArchiveTableWidget(QTableWidget):
    """아카이브 내용을 보여주고, 선택 항목을 탐색기로 끌어낼 수 있는 표."""

    def __init__(self, rows: int = 0, columns: int = 0, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self._materializer: DragMaterializer | None = None
        self.setDragEnabled(True)
        self.setDragDropMode(QTableWidget.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def set_drag_materializer(self, materializer: DragMaterializer | None) -> None:
        self._materializer = materializer

    def collect_drag_entry_paths(self) -> list[str]:
        """선택된 행들의 아카이브 내부 경로를 행 순서대로 모은다.

        '..'(상위 폴더) 행은 실체가 없으므로 제외한다. 폴더 행은 그대로 넘기고,
        하위 엔트리까지 펼치는 일은 materializer(=서비스 계층)가 맡는다.
        """
        paths: list[str] = []
        for row in sorted({index.row() for index in self.selectedIndexes()}):
            item = self.item(row, 0)
            if item is None or item.data(ROLE_KIND) == "up":
                continue
            path = item.data(ROLE_PATH)
            if path:
                paths.append(path)
        return paths

    def build_drag_mime_data(self, file_paths: list[pathlib.Path]) -> QMimeData:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in file_paths])
        return mime

    def startDrag(self, supportedActions) -> None:  # noqa: N802 - Qt 오버라이드 네이밍
        entry_paths = self.collect_drag_entry_paths()
        if not entry_paths or self._materializer is None:
            return

        file_paths = self._materializer(entry_paths)
        if not file_paths:
            # 해제 실패(암호 취소 등)면 드래그를 시작하지 않는다. 빈 드래그를 띄우면
            # 탐색기에 0바이트 파일이 생기는 것처럼 보여 더 혼란스럽다.
            return

        drag = QDrag(self)
        drag.setMimeData(self.build_drag_mime_data(file_paths))
        drag.exec(Qt.DropAction.CopyAction)
