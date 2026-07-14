"""PackNine 메인 윈도우.

application 계층의 CompressService/ExtractService/InspectService만 호출하며
infrastructure 어댑터는 직접 참조하지 않는다(계층 경계 유지).
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QTableWidget,
    QTableWidgetItem,
)

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
from packnine.application.inspect_service import InspectService
from packnine.domain.entities import ArchiveManifest
from packnine.domain.exceptions import InvalidPasswordError, UnsafeArchiveEntryError
from packnine.presentation.gui.image_viewer import ImageViewerDialog, is_image_name

# 이미지 미리보기를 위해 한 번에 임시 폴더로 미리 꺼내둘 이미지 개수 상한.
# 이미지가 매우 많은 아카이브에서 더블클릭 한 번에 전부 해제하느라 오래 걸리는 것을 막는다.
_MAX_PREVIEW_IMAGES = 200

# 아카이브로 인식할 확장자 - 드래그앤드롭 시 압축 대상 파일인지 아카이브인지
# 구분하는 데 사용한다 (format_registry의 지원 확장자와 동일해야 하지만,
# infrastructure 모듈을 import하지 않기 위해 여기서 별도로 정의한다).
_ARCHIVE_EXTENSIONS = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tgz",
    ".tar",
    ".zip",
    ".7z",
    ".rar",
)

_TABLE_HEADERS = ["이름", "크기", "압축크기", "압축률"]

# PyInstaller로 빌드하면 리소스가 sys._MEIPASS 아래에 풀리므로, 개발 환경(소스 실행)과
# 빌드 환경 양쪽에서 아이콘을 찾을 수 있도록 두 경로를 모두 시도한다.
_ICON_PATH = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent)) / "assets" / "icon.ico"
if not _ICON_PATH.exists():
    _ICON_PATH = pathlib.Path(__file__).resolve().parent / "assets" / "icon.ico"


def _is_archive_path(path: pathlib.Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(ext) for ext in _ARCHIVE_EXTENSIONS)


class MainWindow(QMainWindow):
    """아카이브 열기/압축/해제/테스트를 수행하는 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PackNine")
        self.resize(800, 500)
        self.setAcceptDrops(True)
        if _ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(_ICON_PATH)))

        self._compress_service = CompressService()
        self._extract_service = ExtractService()
        self._inspect_service = InspectService()

        # 현재 열려있는 아카이브 경로 - "압축풀기"/"테스트" 액션이 대상으로 사용한다.
        self._current_archive_path: pathlib.Path | None = None
        # 현재 아카이브에서 검증된 비밀번호. 열기/해제 어느 시점에 입력받았든 이후
        # 동작(테스트, 미리보기)에서 재입력 없이 재사용한다.
        self._current_password: str | None = None
        # 더블클릭한 행이 어떤 엔트리인지 알아야 이미지 뷰어를 열 수 있어 목록도 보관한다.
        self._current_manifest: ArchiveManifest | None = None

        self._table = QTableWidget(0, len(_TABLE_HEADERS))
        self._table.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.cellDoubleClicked.connect(self._on_table_double_clicked)
        self.setCentralWidget(self._table)

        self._build_toolbar()

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("메인")

        self.action_open = QAction("열기", self)
        self.action_open.triggered.connect(self._on_open)
        toolbar.addAction(self.action_open)

        self.action_compress = QAction("압축하기", self)
        self.action_compress.triggered.connect(self._on_compress)
        toolbar.addAction(self.action_compress)

        self.action_extract = QAction("압축풀기", self)
        self.action_extract.triggered.connect(self._on_extract)
        toolbar.addAction(self.action_extract)

        self.action_test = QAction("테스트", self)
        self.action_test.triggered.connect(self._on_test)
        toolbar.addAction(self.action_test)

    # ------------------------------------------------------------------
    # 툴바 액션 핸들러
    # ------------------------------------------------------------------
    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "아카이브 열기")
        if not path_str:
            return
        self._open_archive(pathlib.Path(path_str))

    def _on_compress(self) -> None:
        # 지연 import: compress_dialog는 main_window와 상호 참조하지 않지만,
        # 다이얼로그 생성 비용을 실제로 필요할 때만 지불하기 위해 여기서 import한다.
        from packnine.presentation.gui.compress_dialog import CompressDialog

        dialog = CompressDialog(parent=self)
        if dialog.exec() != CompressDialog.DialogCode.Accepted:
            return
        source_paths, destination, password, compression_level = dialog.get_result()
        self._run_compress(source_paths, destination, password, compression_level)

    def _on_extract(self) -> None:
        if self._current_archive_path is None:
            QMessageBox.information(self, "안내", "먼저 아카이브를 열어주세요.")
            return
        destination_str = QFileDialog.getExistingDirectory(self, "압축 해제할 폴더 선택")
        if not destination_str:
            return
        destination = pathlib.Path(destination_str)
        progress = self._make_progress_dialog("압축 해제 중...")
        try:
            completed = self._execute_with_password_retry(
                lambda password: self._extract_service.extract(
                    self._current_archive_path,
                    destination,
                    password=password,
                    on_progress=self._progress_callback(progress),
                )
            )
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
        except Exception as exc:  # noqa: BLE001 - 애플리케이션 크래시 방지를 위해 광범위하게 처리
            self._show_error(exc)
        else:
            if completed:
                QMessageBox.information(self, "완료", f"압축 해제가 완료되었습니다: {destination}")
        finally:
            progress.close()

    def _on_test(self) -> None:
        """현재 아카이브를 임시 폴더에 해제해보고 성공/실패만 알려준다(결과물은 남기지 않음)."""
        if self._current_archive_path is None:
            QMessageBox.information(self, "안내", "먼저 아카이브를 열어주세요.")
            return

        temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="packnine_test_"))
        progress = self._make_progress_dialog("무결성 테스트 중...")
        try:
            completed = self._execute_with_password_retry(
                lambda password: self._extract_service.extract(
                    self._current_archive_path,
                    temp_dir,
                    password=password,
                    on_progress=self._progress_callback(progress),
                )
            )
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "테스트 실패", f"아카이브 무결성 테스트에 실패했습니다:\n{exc}")
        else:
            if completed:
                QMessageBox.information(self, "테스트 성공", "아카이브가 정상적으로 해제 가능합니다.")
        finally:
            progress.close()
            # 실제 위치에 결과물을 남기지 않는다는 요구사항에 따라 임시 폴더는 항상 삭제한다.
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _run_compress(
        self,
        source_paths: list[pathlib.Path],
        destination: pathlib.Path,
        password: str | None,
        compression_level,
    ) -> None:
        progress = self._make_progress_dialog("압축 중...")
        try:
            manifest = self._compress_service.compress(
                source_paths,
                destination,
                password=password,
                compression_level=compression_level,
                on_progress=self._progress_callback(progress),
            )
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
        else:
            self._current_archive_path = destination
            self._populate_table(manifest)
            QMessageBox.information(self, "완료", f"압축이 완료되었습니다: {destination}")
        finally:
            progress.close()

    def _open_archive(self, archive_path: pathlib.Path) -> None:
        # 다른 아카이브의 비밀번호를 새 아카이브에 재사용하지 않는다.
        if archive_path != self._current_archive_path:
            self._current_password = None
        try:
            manifest: ArchiveManifest | None = None

            def _list(password: str | None) -> None:
                nonlocal manifest
                # 헤더 암호화된 7z 등은 목록 조회 단계에서부터 비밀번호가 필요하다.
                manifest = self._inspect_service.list_contents(archive_path, password=password)

            completed = self._execute_with_password_retry(_list)
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
        else:
            if not completed or manifest is None:
                return
            self._current_archive_path = archive_path
            self._populate_table(manifest)

    def _prompt_password(self) -> str | None:
        """비밀번호 입력 다이얼로그를 띄운다. 취소하면 None을 반환한다."""
        name = self._current_archive_path.name if self._current_archive_path else "아카이브"
        text, ok = QInputDialog.getText(
            self,
            "비밀번호 필요",
            f"'{name}'의 비밀번호를 입력하세요:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not text:
            return None
        return text

    def _execute_with_password_retry(self, operation) -> bool:
        """operation(password)를 실행하되, 비밀번호 오류면 입력받아 재시도한다.

        성공하면 검증된 비밀번호를 보관하고 True, 사용자가 입력을 취소하면 False.
        비밀번호 외의 예외는 그대로 전파해 호출자의 기존 except 절이 처리하게 한다.
        """
        password = self._current_password
        while True:
            try:
                operation(password)
            except InvalidPasswordError:
                password = self._prompt_password()
                if password is None:
                    return False
            else:
                self._current_password = password
                return True

    def _populate_table(self, manifest: ArchiveManifest) -> None:
        self._current_manifest = manifest
        self._table.setRowCount(len(manifest.entries))
        for row, entry in enumerate(manifest.entries):
            self._table.setItem(row, 0, QTableWidgetItem(entry.name))
            self._table.setItem(row, 1, QTableWidgetItem(str(entry.size)))
            self._table.setItem(row, 2, QTableWidgetItem(str(entry.compressed_size)))
            self._table.setItem(row, 3, QTableWidgetItem(f"{entry.compression_ratio:.2f}"))

    # ------------------------------------------------------------------
    # 내장 이미지 뷰어
    # ------------------------------------------------------------------
    def _on_table_double_clicked(self, row: int, _column: int) -> None:
        if self._current_manifest is None or self._current_archive_path is None:
            return
        if row < 0 or row >= len(self._current_manifest.entries):
            return
        entry = self._current_manifest.entries[row]
        if entry.is_dir or not is_image_name(entry.name):
            return
        self._open_image_viewer(clicked_entry_name=entry.name)

    def _open_image_viewer(self, clicked_entry_name: str) -> None:
        assert self._current_manifest is not None
        assert self._current_archive_path is not None

        image_entries = [
            e for e in self._current_manifest.entries if not e.is_dir and is_image_name(e.name)
        ]
        if not image_entries:
            return
        if len(image_entries) > _MAX_PREVIEW_IMAGES:
            image_entries = image_entries[:_MAX_PREVIEW_IMAGES]

        temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="packnine_preview_"))
        try:
            entry_names = [e.name for e in image_entries]
            completed = self._execute_with_password_retry(
                lambda password: self._extract_service.extract_entries(
                    self._current_archive_path, entry_names, temp_dir, password=password
                )
            )
            if not completed:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return

        try:
            image_paths = [temp_dir / e.name for e in image_entries]
            start_index = next(
                (i for i, e in enumerate(image_entries) if e.name == clicked_entry_name), 0
            )
            dialog = ImageViewerDialog(image_paths, start_index=start_index, parent=self)
            dialog.exec()
        finally:
            # 미리보기용으로 임시로 꺼낸 것이므로 뷰어를 닫으면 항상 정리한다.
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _make_progress_dialog(self, label: str) -> QProgressDialog:
        progress = QProgressDialog(label, "취소", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        return progress

    def _progress_callback(self, progress: QProgressDialog):
        def _callback(name: str, done: int, total: int) -> None:
            progress.setLabelText(name)
            if total > 0:
                progress.setMaximum(total)
                progress.setValue(done)
            # UI가 즉시 갱신되도록 이벤트 루프에 양보한다.
            QApplication.processEvents()

        return _callback

    def _show_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "오류", str(exc))

    def _show_security_warning(self, exc: UnsafeArchiveEntryError) -> None:
        QMessageBox.critical(self, "보안 경고", str(exc))

    # ------------------------------------------------------------------
    # 드래그 앤 드롭
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 네이밍 컨벤션 유지
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        paths = [pathlib.Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
        if not paths:
            return

        # 아카이브 파일 하나만 드롭한 경우 바로 목록을 열어 보여준다.
        if len(paths) == 1 and paths[0].is_file() and _is_archive_path(paths[0]):
            self._open_archive(paths[0])
            return

        # 그 외에는 압축 대상 파일들로 간주해 CompressDialog를 미리 채워 연다.
        from packnine.presentation.gui.compress_dialog import CompressDialog

        dialog = CompressDialog(initial_files=paths, parent=self)
        if dialog.exec() == CompressDialog.DialogCode.Accepted:
            source_paths, destination, password, compression_level = dialog.get_result()
            self._run_compress(source_paths, destination, password, compression_level)


def run_gui(initial_archive: pathlib.Path | None = None) -> int:
    """GUI 애플리케이션을 실행한다. 이미 QApplication 인스턴스가 있으면 재사용한다.

    initial_archive가 주어지면(파일 연결로 더블클릭 실행된 경우) 창을 띄우자마자
    그 아카이브를 바로 연다.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    window = MainWindow()
    if initial_archive is not None:
        window._open_archive(initial_archive)
    window.show()
    return app.exec()
