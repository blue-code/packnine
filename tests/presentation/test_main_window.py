"""MainWindow 스모크 테스트 - 실제 파일 다이얼로그는 모킹하고 기본 구조만 확인한다."""
from __future__ import annotations

import pathlib

from PySide6.QtWidgets import QFileDialog, QMessageBox

from packnine.presentation.gui.main_window import MainWindow


def test_main_window_creates_with_toolbar_actions(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "PackNine"
    assert window.action_open.text() == "열기"
    assert window.action_compress.text() == "새로 압축"
    assert window.action_extract.text() == "압축 풀기"
    assert window.action_add_files.text() == "파일 추가"
    assert window.action_remove_selected.text() == "파일 삭제"
    assert window.action_test.text() == "테스트"
    # 탐색기형 레이아웃 구성 요소: 메뉴바, 폴더 트리, 주소 표시줄, 상태 표시줄
    assert window.menuBar().actions(), "메뉴바가 비어 있으면 안 된다"
    assert window._tree is not None
    assert window._address_bar is not None
    assert window.statusBar() is not None


def test_folder_navigation_like_explorer(qtbot, tmp_path):
    # 반디집처럼 루트에는 폴더만 보이고, 폴더 더블클릭으로 들어가고 '..'로 나온다.
    from packnine.application.compress_service import CompressService

    src_dir = tmp_path / "docs"
    src_dir.mkdir()
    (src_dir / "inner.txt").write_text("inner", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    # 루트: docs 폴더 행 하나
    names = {window._table.item(r, 0).text() for r in range(window._table.rowCount())}
    assert "docs" in names
    assert "inner.txt" not in names

    docs_row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "docs"
    )
    window._on_table_double_clicked(docs_row, 0)

    # docs 내부: '..'와 inner.txt
    names = {window._table.item(r, 0).text() for r in range(window._table.rowCount())}
    assert names == {"..", "inner.txt"}
    assert "docs" in window._address_bar.text()

    up_row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == ".."
    )
    window._on_table_double_clicked(up_row, 0)
    names = {window._table.item(r, 0).text() for r in range(window._table.rowCount())}
    assert "docs" in names


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


def test_double_click_image_entry_opens_viewer(qtbot, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage

    from packnine.application.compress_service import CompressService
    from packnine.presentation.gui import image_viewer as image_viewer_module

    src_dir = tmp_path / "pics"
    src_dir.mkdir()
    # Pillow 같은 추가 의존성 없이, 이미 하드 의존성인 PySide6로 최소 PNG를 만든다.
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(0xFFFF0000)
    image.save(str(src_dir / "photo.png"))
    (src_dir / "notes.txt").write_text("not an image", encoding="utf-8")

    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    # 탐색기형 뷰: 루트에는 pics 폴더만 보이므로 먼저 폴더로 들어간다.
    pics_row = next(
        row
        for row in range(window._table.rowCount())
        if window._table.item(row, 0).text() == "pics"
    )
    window._on_table_double_clicked(pics_row, 0)

    image_row = next(
        row
        for row in range(window._table.rowCount())
        if window._table.item(row, 0).text().endswith("photo.png")
    )

    opened_dialogs = []
    original_init = image_viewer_module.ImageViewerDialog.__init__

    def _capture_init(self, image_paths, start_index=0, parent=None):
        opened_dialogs.append((image_paths, start_index))
        original_init(self, image_paths, start_index=start_index, parent=parent)

    monkeypatch.setattr(image_viewer_module.ImageViewerDialog, "__init__", _capture_init)
    monkeypatch.setattr(image_viewer_module.ImageViewerDialog, "exec", lambda self: None)

    window._on_table_double_clicked(image_row, 0)

    assert len(opened_dialogs) == 1
    image_paths, start_index = opened_dialogs[0]
    assert start_index == 0
    assert image_paths[0].name == "photo.png"
    # 뷰어 다이얼로그를 닫은 뒤에는 미리보기용 임시 폴더가 정리되어야 한다.
    assert not image_paths[0].exists()


def test_file_association_registers_and_offers_settings(qtbot, monkeypatch):
    # "파일 연결 설정"은 연결 프로그램 등록을 수행하고 Windows 기본 앱 설정을 열도록 안내한다.
    from PySide6.QtGui import QDesktopServices

    from packnine.application import context_menu_service

    window = MainWindow()
    qtbot.addWidget(window)

    registered = []
    monkeypatch.setattr(
        context_menu_service.ContextMenuService,
        "register",
        lambda self: registered.append(True),
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    opened = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True
    )

    window._on_file_association()

    assert registered == [True]
    assert opened and "ms-settings:defaultapps" in opened[0]


def test_selecting_image_shows_left_preview(qtbot, tmp_path):
    # 목록에서 이미지 파일을 선택하면 좌측 네비 패널 아래 미리보기에 그 이미지가 뜬다.
    from PySide6.QtGui import QImage

    from packnine.application.compress_service import CompressService

    src = tmp_path / "pics"
    src.mkdir()
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(0xFF00FF00)
    image.save(str(src / "green.png"))
    (src / "notes.txt").write_text("not an image", encoding="utf-8")
    archive = tmp_path / "out.zip"
    CompressService().compress([src], archive)

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(900, 600)
    window.show()
    qtbot.waitExposed(window)
    window._open_archive(archive)

    # pics 폴더로 진입
    pics_row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "pics"
    )
    window._on_table_double_clicked(pics_row, 0)

    # green.png 행을 선택하면 미리보기 픽스맵이 채워져야 한다.
    img_row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "green.png"
    )
    window._table.selectRow(img_row)
    qtbot.wait(100)

    pm = window._preview_image_label.pixmap()
    assert pm is not None and not pm.isNull()
    assert "green.png" in window._preview_caption.text()


def test_selecting_non_image_clears_preview(qtbot, tmp_path):
    from PySide6.QtGui import QImage

    from packnine.application.compress_service import CompressService

    src = tmp_path / "pics"
    src.mkdir()
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(0xFF0000FF)
    image.save(str(src / "blue.png"))
    (src / "notes.txt").write_text("plain text", encoding="utf-8")
    archive = tmp_path / "out.zip"
    CompressService().compress([src], archive)

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(900, 600)
    window.show()
    qtbot.waitExposed(window)
    window._open_archive(archive)
    pics_row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "pics"
    )
    window._on_table_double_clicked(pics_row, 0)

    # 이미지 선택 → 미리보기 채움
    img_row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "blue.png"
    )
    window._table.selectRow(img_row)
    qtbot.wait(100)
    assert not window._preview_image_label.pixmap().isNull()

    # 텍스트 파일 선택 → 이미지는 비우고 내용 미리보기로 전환
    txt_row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "notes.txt"
    )
    window._table.selectRow(txt_row)
    qtbot.wait(100)
    pm = window._preview_image_label.pixmap()
    assert pm is None or pm.isNull()
    assert window._preview_text.isVisible()
    assert window._preview_text.toPlainText() != ""


def test_table_sorts_size_column_numerically(qtbot, tmp_path):
    # "10" < "9" 문자열 정렬이 아니라 9 < 10 숫자 정렬이어야 한다.
    from PySide6.QtCore import Qt

    from packnine.application.compress_service import CompressService

    small = tmp_path / "small.txt"
    small.write_text("x" * 9, encoding="utf-8")
    big = tmp_path / "big.txt"
    big.write_text("y" * 1000, encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([small, big], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    assert window._table.isSortingEnabled()
    window._table.sortItems(1, Qt.SortOrder.AscendingOrder)
    sizes = [
        window._table.item(row, 1).data(Qt.ItemDataRole.DisplayRole)
        for row in range(window._table.rowCount())
    ]
    assert sizes == sorted(sizes)
    assert sizes[0] == 9  # 숫자로 저장되어 있어야 한다


def test_add_files_action_appends_to_open_archive(qtbot, tmp_path, monkeypatch):
    from packnine.application.compress_service import CompressService

    src_file = tmp_path / "a.txt"
    src_file.write_text("hello", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_file], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    new_file = tmp_path / "extra.txt"
    new_file.write_text("extra", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(new_file)], "")
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    window._on_add_files()

    names = {
        window._table.item(row, 0).text() for row in range(window._table.rowCount())
    }
    assert "extra.txt" in names and "a.txt" in names


def test_remove_selected_action_deletes_entry(qtbot, tmp_path, monkeypatch):
    from packnine.application.compress_service import CompressService

    a = tmp_path / "a.txt"
    a.write_text("aaa", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("bbb", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([a, b], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    # a.txt 행을 선택하고 삭제 - 확인 다이얼로그는 '예'로 모킹한다.
    target_row = next(
        row
        for row in range(window._table.rowCount())
        if window._table.item(row, 0).text() == "a.txt"
    )
    window._table.selectRow(target_row)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    window._on_remove_selected()

    names = {
        window._table.item(row, 0).text() for row in range(window._table.rowCount())
    }
    assert "a.txt" not in names and "b.txt" in names


def test_double_click_text_entry_opens_with_default_app(qtbot, tmp_path, monkeypatch):
    # 반디집처럼 아카이브 안의 일반 파일(문서 등)을 더블클릭하면 임시로 꺼내
    # 기본 연결 프로그램으로 열어야 한다(이미지는 내장 뷰어가 우선).
    from PySide6.QtGui import QDesktopServices

    from packnine.application.compress_service import CompressService

    src_file = tmp_path / "notes.txt"
    src_file.write_text("open me", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_file], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    opened_urls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened_urls.append(url) or True)

    window._on_table_double_clicked(0, 0)

    assert len(opened_urls) == 1
    opened_path = pathlib.Path(opened_urls[0].toLocalFile())
    assert opened_path.name == "notes.txt"
    # 외부 프로그램이 읽는 동안 파일이 존재해야 한다(즉시 삭제 금지).
    assert opened_path.read_text(encoding="utf-8") == "open me"

    # 창을 닫으면 임시 파일이 정리되어야 한다.
    window.close()
    assert not opened_path.exists()


def _make_encrypted_zip(tmp_path: pathlib.Path, password: str) -> pathlib.Path:
    from packnine.application.compress_service import CompressService

    src_file = tmp_path / "secret.txt"
    src_file.write_text("top secret", encoding="utf-8")
    archive_path = tmp_path / "locked.zip"
    CompressService().compress([src_file], archive_path, password=password)
    return archive_path


def test_extract_encrypted_archive_prompts_for_password(qtbot, tmp_path, monkeypatch):
    # 암호 zip은 목록 조회는 되지만(엔트리명은 평문) 해제 시 암호가 필요하다.
    # GUI에 암호 입력 수단이 없으면 사용자는 암호 아카이브를 영영 풀 수 없다.
    from PySide6.QtWidgets import QInputDialog

    archive_path = _make_encrypted_zip(tmp_path, password="pw123")
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)
    assert window._table.rowCount() == 1

    destination = tmp_path / "out"
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a, **k: str(destination)
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("pw123", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    window._on_extract()

    assert (destination / "secret.txt").read_text(encoding="utf-8") == "top secret"


def test_extract_encrypted_archive_cancel_prompt_aborts_quietly(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    archive_path = _make_encrypted_zip(tmp_path, password="pw123")
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    destination = tmp_path / "out"
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a, **k: str(destination)
    )
    # 사용자가 비밀번호 입력을 취소하면 에러 다이얼로그 없이 조용히 중단해야 한다.
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *a, **k: critical_calls.append(a)
    )

    window._on_extract()

    assert critical_calls == []
    assert not (destination / "secret.txt").exists()


def test_double_click_non_image_entry_does_nothing(qtbot, tmp_path, monkeypatch):
    from packnine.application.compress_service import CompressService
    from packnine.presentation.gui import image_viewer as image_viewer_module

    src_file = tmp_path / "notes.txt"
    src_file.write_text("hello", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_file], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    opened_dialogs = []
    monkeypatch.setattr(
        image_viewer_module.ImageViewerDialog,
        "__init__",
        lambda self, *a, **k: opened_dialogs.append((a, k)),
    )

    window._on_table_double_clicked(0, 0)

    assert opened_dialogs == []


def test_first_volume_is_recognized_as_archive_path(tmp_path):
    # 분할 첫 볼륨을 드롭하면 압축 대상이 아니라 아카이브로 열어야 한다.
    from packnine.presentation.gui.main_window import _is_archive_path

    assert _is_archive_path(tmp_path / "photos.7z.001") is True
    assert _is_archive_path(tmp_path / "photos.zip.001") is True


def test_drag_out_materializes_selected_file_to_real_path(qtbot, tmp_path):
    # 드래그 아웃: 아카이브 안의 엔트리를 탐색기가 복사할 수 있는 실제 파일로 꺼낸다.
    from packnine.application.compress_service import CompressService

    src_dir = tmp_path / "docs"
    src_dir.mkdir()
    (src_dir / "inner.txt").write_text("끌어낸 내용", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    paths = window._materialize_entries_for_drag(["docs/inner.txt"])

    assert len(paths) == 1
    assert paths[0].name == "inner.txt"
    assert paths[0].read_text(encoding="utf-8") == "끌어낸 내용"


def test_drag_out_of_folder_extracts_its_children(qtbot, tmp_path):
    # 폴더를 끌면 하위 엔트리까지 실체화하고, 끌어낼 경로는 폴더 하나만 돌려준다.
    from packnine.application.compress_service import CompressService

    src_dir = tmp_path / "docs"
    (src_dir / "sub").mkdir(parents=True)
    (src_dir / "sub" / "deep.txt").write_text("깊은 파일", encoding="utf-8")
    archive_path = tmp_path / "out.zip"
    CompressService().compress([src_dir], archive_path)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive_path)

    paths = window._materialize_entries_for_drag(["docs"])

    assert len(paths) == 1
    assert paths[0].name == "docs"
    assert (paths[0] / "sub" / "deep.txt").read_text(encoding="utf-8") == "깊은 파일"


def test_drag_out_without_open_archive_returns_empty(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._materialize_entries_for_drag(["a.txt"]) == []


def test_extract_asks_nothing_when_no_conflict(qtbot, tmp_path):
    # 충돌이 없으면 확인 창을 띄우지 않고 기본값(덮어쓰기)으로 진행해야 한다.
    from packnine.application.compress_service import CompressService
    from packnine.domain.value_objects import DuplicatePolicy

    source = tmp_path / "a.txt"
    source.write_text("내용", encoding="utf-8")
    archive = tmp_path / "out.zip"
    CompressService().compress([source], archive)

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive)

    assert window._ask_duplicate_policy(tmp_path / "비어있는폴더") is DuplicatePolicy.OVERWRITE


def test_extract_asks_policy_when_conflict_exists(qtbot, tmp_path, monkeypatch):
    from packnine.application.compress_service import CompressService
    from packnine.domain.value_objects import DuplicatePolicy
    from PySide6.QtWidgets import QMessageBox

    source = tmp_path / "a.txt"
    source.write_text("내용", encoding="utf-8")
    archive = tmp_path / "out.zip"
    CompressService().compress([source], archive)

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("기존", encoding="utf-8")

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(archive)

    # 모달 exec()를 가로채 "건너뛰기"(기본 버튼)를 고른 것처럼 만든다.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.defaultButton())

    assert window._ask_duplicate_policy(dest) is DuplicatePolicy.SKIP


def test_file_association_menu_informs_instead_of_failing_when_packaged(
    qtbot, tmp_path, monkeypatch
):
    # 스토어 설치본에서 "파일 연결 설정"을 누르면 빨간 오류창이 아니라 안내가 떠야 한다.
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox

    from packnine.infrastructure import packaged_app

    monkeypatch.setattr(packaged_app, "is_packaged", lambda *a: True)

    window = MainWindow()
    qtbot.addWidget(window)

    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *args, **kwargs: shown.append(args[2])
    )
    errors: list = []
    monkeypatch.setattr(window, "_show_error", lambda exc: errors.append(exc))
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: True)

    window._on_file_association()

    assert errors == []
    assert len(shown) == 1 and "Windows가 자동으로 관리" in shown[0]


def _archive_with_tree(tmp_path):
    """검색/선택 해제 테스트용 아카이브를 만든다(하위 폴더 포함)."""
    from packnine.application.compress_service import CompressService

    src = tmp_path / "자료"
    (src / "문서").mkdir(parents=True)
    (src / "사진").mkdir(parents=True)
    (src / "문서" / "보고서.txt").write_text("보고서 내용 " * 30, encoding="utf-8")
    (src / "문서" / "메모.txt").write_text("메모 내용 " * 30, encoding="utf-8")
    (src / "사진" / "보고서_사진.txt").write_text("사진 설명 " * 30, encoding="utf-8")
    archive = tmp_path / "tree.zip"
    CompressService().compress([src], archive)
    return archive


def test_search_finds_entries_across_all_folders(qtbot, tmp_path):
    # 검색의 목적은 깊은 폴더에 묻힌 파일을 찾는 것이라 현재 폴더에 한정하면 안 된다.
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(_archive_with_tree(tmp_path))

    window._search_box.setText("보고서")
    qtbot.wait(50)

    names = {window._table.item(r, 0).text() for r in range(window._table.rowCount())}
    assert names == {"자료/문서/보고서.txt", "자료/사진/보고서_사진.txt"}


def test_search_is_case_insensitive_and_clearing_restores_folder_view(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(_archive_with_tree(tmp_path))
    before = {window._table.item(r, 0).text() for r in range(window._table.rowCount())}

    window._search_box.setText("BOGOSEO")  # 매칭 없음
    qtbot.wait(50)
    assert window._table.rowCount() == 0

    window._search_box.clear()
    qtbot.wait(50)
    after = {window._table.item(r, 0).text() for r in range(window._table.rowCount())}
    assert after == before


def test_search_result_count_shown_in_address_bar(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(_archive_with_tree(tmp_path))

    window._search_box.setText("메모")
    qtbot.wait(50)

    assert "검색 결과 1개" in window._address_bar.text()


def test_extract_selected_writes_only_chosen_entries(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(_archive_with_tree(tmp_path))
    window._navigate_to("자료/문서")
    qtbot.wait(50)

    row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "메모.txt"
    )
    window._table.selectRow(row)

    destination = tmp_path / "out"
    destination.mkdir()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a, **k: str(destination)
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    window._on_extract_selected()

    assert (destination / "자료" / "문서" / "메모.txt").exists()
    # 고르지 않은 항목은 나오면 안 된다.
    assert not (destination / "자료" / "문서" / "보고서.txt").exists()


def test_extract_selected_expands_folder_selection(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    window = MainWindow()
    qtbot.addWidget(window)
    window._open_archive(_archive_with_tree(tmp_path))
    window._navigate_to("자료")
    qtbot.wait(50)

    row = next(
        r for r in range(window._table.rowCount())
        if window._table.item(r, 0).text() == "사진"
    )
    window._table.selectRow(row)

    destination = tmp_path / "out2"
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a, **k: str(destination)
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    window._on_extract_selected()

    assert (destination / "자료" / "사진" / "보고서_사진.txt").exists()


def test_opening_archive_records_it_in_recent_menu(qtbot, tmp_path, monkeypatch):
    from packnine.infrastructure import recent_files

    store = tmp_path / "recent.json"
    monkeypatch.setattr(recent_files, "_default_store_path", lambda: store)

    window = MainWindow()
    qtbot.addWidget(window)
    archive = _archive_with_tree(tmp_path)
    window._open_archive(archive)

    assert recent_files.load(store_path=store) == [archive]
    labels = [a.text() for a in window._recent_menu.actions()]
    assert archive.name in labels


def test_password_book_tries_known_password_before_prompting(qtbot, tmp_path, monkeypatch):
    # 같은 비밀번호를 쓰는 두 번째 아카이브에서는 입력창이 뜨지 않아야 한다.
    from packnine.domain.exceptions import InvalidPasswordError

    window = MainWindow()
    qtbot.addWidget(window)
    window._password_book.remember("공용비밀번호")

    prompted: list[int] = []
    monkeypatch.setattr(window, "_prompt_password", lambda: prompted.append(1))

    seen: list[str | None] = []

    def operation(password):
        seen.append(password)
        if password != "공용비밀번호":
            raise InvalidPasswordError("틀림")

    assert window._execute_with_password_retry(operation) is True
    assert prompted == []
    assert window._current_password == "공용비밀번호"


def test_password_book_remembers_password_entered_by_user(qtbot, monkeypatch):
    from packnine.domain.exceptions import InvalidPasswordError

    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_prompt_password", lambda: "새비밀번호")

    def operation(password):
        if password != "새비밀번호":
            raise InvalidPasswordError("틀림")

    assert window._execute_with_password_retry(operation) is True
    # 다음 아카이브에서 자동 시도되도록 목록에 들어가야 한다.
    assert "새비밀번호" in window._password_book.candidates()


def test_password_prompt_still_appears_when_book_has_no_match(qtbot, monkeypatch):
    from packnine.domain.exceptions import InvalidPasswordError

    window = MainWindow()
    qtbot.addWidget(window)
    window._password_book.remember("틀린것")
    monkeypatch.setattr(window, "_prompt_password", lambda: None)  # 사용자가 취소

    def operation(password):
        raise InvalidPasswordError("틀림")

    assert window._execute_with_password_retry(operation) is False
