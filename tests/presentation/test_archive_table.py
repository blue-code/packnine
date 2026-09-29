"""ArchiveTableWidget(드래그 아웃) 테스트.

QDrag.exec()는 실제 마우스 루프를 돌려 테스트에서 멈추므로, 드래그를 구성하는 두 조각
(선택 행 → 엔트리 경로 수집, 실제 파일 경로 → QMimeData)을 따로 검증한다.
startDrag 자체는 "재료가 없으면 드래그를 시작하지 않는다"만 확인한다.
"""
from __future__ import annotations

import pathlib

from PySide6.QtWidgets import QTableWidgetItem

from packnine.presentation.gui.widgets.archive_table import (
    ROLE_KIND,
    ROLE_PATH,
    ArchiveTableWidget,
)


def _make_table(qtbot, rows: list[tuple[str, str, str]]) -> ArchiveTableWidget:
    """rows = [(표시이름, kind, 엔트리경로)] 로 표를 채운다."""
    table = ArchiveTableWidget(len(rows), 1)
    qtbot.addWidget(table)
    for row, (display, kind, path) in enumerate(rows):
        item = QTableWidgetItem(display)
        item.setData(ROLE_KIND, kind)
        item.setData(ROLE_PATH, path)
        table.setItem(row, 0, item)
    return table


def test_collects_entry_paths_of_selected_rows(qtbot):
    table = _make_table(
        qtbot,
        [
            ("..", "up", ""),
            ("pics", "folder", "pics"),
            ("a.txt", "file", "a.txt"),
        ],
    )
    table.selectRow(2)

    assert table.collect_drag_entry_paths() == ["a.txt"]


def test_folder_rows_are_draggable_too(qtbot):
    table = _make_table(qtbot, [("pics", "folder", "pics"), ("a.txt", "file", "a.txt")])
    table.selectAll()

    # 폴더도 통째로 끌어낼 수 있어야 한다. 순서는 행 순서를 따른다.
    assert table.collect_drag_entry_paths() == ["pics", "a.txt"]


def test_up_row_is_never_dragged(qtbot):
    # '..'는 상위 폴더 이동용 가짜 행이라 실체가 없다 - 끌어내면 안 된다.
    table = _make_table(qtbot, [("..", "up", "")])
    table.selectAll()

    assert table.collect_drag_entry_paths() == []


def test_mime_data_carries_local_file_urls(qtbot, tmp_path):
    table = _make_table(qtbot, [("a.txt", "file", "a.txt")])
    first = tmp_path / "a.txt"
    first.write_text("hello", encoding="utf-8")
    second = tmp_path / "pics"
    second.mkdir()

    mime = table.build_drag_mime_data([first, second])

    assert mime.hasUrls()
    assert [pathlib.Path(url.toLocalFile()) for url in mime.urls()] == [first, second]


def test_start_drag_does_nothing_without_materializer(qtbot):
    # 재료 공급자가 없으면(아카이브 미오픈 등) 조용히 끝나야 한다 - 예외가 나면 GUI가 죽는다.
    table = _make_table(qtbot, [("a.txt", "file", "a.txt")])
    table.selectAll()

    table.startDrag(table.defaultDropAction())  # 예외 없이 반환되면 성공


def test_start_drag_skips_when_materializer_returns_nothing(qtbot):
    table = _make_table(qtbot, [("a.txt", "file", "a.txt")])
    table.selectAll()
    called: list[list[str]] = []

    def materializer(entry_paths):
        called.append(entry_paths)
        return []  # 해제 실패/취소를 흉내낸다

    table.set_drag_materializer(materializer)
    table.startDrag(table.defaultDropAction())

    assert called == [["a.txt"]]
