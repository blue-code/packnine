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
