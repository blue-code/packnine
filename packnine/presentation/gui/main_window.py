"""PackNine 메인 윈도우 - 탐색기형(아카이버 표준) 레이아웃.

반디집/7-Zip류 압축 프로그램의 일반적인 작업 흐름(툴바 + 좌측 폴더 트리 +
우측 현재 폴더 파일 목록 + 상태 표시줄)을 따른다. 레이아웃/동작 패턴은 아카이버
표준 UX를 구현한 것이며, 특정 제품의 아이콘·로고·시각 디자인은 복제하지 않는다
(아이콘은 Qt 표준 아이콘 사용 - README의 비복제 원칙 유지).

application 계층의 서비스만 호출하며 infrastructure 어댑터는 직접 참조하지 않는다
(계층 경계 유지).
"""
from __future__ import annotations

import datetime
import pathlib
import shutil
import sys
import tempfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
from packnine.application.inspect_service import InspectService
from packnine.application.update_service import UpdateService
from packnine.domain.entities import ArchiveEntry, ArchiveManifest
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
    ".gz",
    ".bz2",
    ".xz",
)

_TABLE_HEADERS = ["이름", "크기", "압축크기", "압축률", "수정한 날짜"]

# 테이블 아이템에 붙이는 커스텀 데이터 롤.
# _ROLE_PATH: 아카이브 내부 전체 경로("pics/photo.png"), _ROLE_KIND: "file"/"folder"/"up"
_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_KIND = Qt.ItemDataRole.UserRole + 1

# PyInstaller로 빌드하면 리소스가 sys._MEIPASS 아래에 풀리므로, 개발 환경(소스 실행)과
# 빌드 환경 양쪽에서 아이콘을 찾을 수 있도록 두 경로를 모두 시도한다.
_ICON_PATH = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent)) / "assets" / "icon.ico"
if not _ICON_PATH.exists():
    _ICON_PATH = pathlib.Path(__file__).resolve().parent / "assets" / "icon.ico"


def _is_archive_path(path: pathlib.Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(ext) for ext in _ARCHIVE_EXTENSIONS)


def _format_timestamp(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


class _GroupedItem(QTableWidgetItem):
    """'..' → 폴더 → 파일 순 그룹을 유지하면서 그룹 안에서만 값으로 정렬되는 아이템.

    일반 QTableWidgetItem으로 정렬하면 크기 기준 정렬 시 폴더 행이 파일들
    사이에 흩어진다. 탐색기/반디집처럼 그룹 우선 정렬을 위해 비교 연산을 재정의한다.
    """

    def __init__(self, group: int, sort_value, text: str = "") -> None:
        super().__init__(text)
        self._group = group
        self._sort_value = sort_value

    def __lt__(self, other) -> bool:  # noqa: D105
        if isinstance(other, _GroupedItem):
            if self._group != other._group:
                return self._group < other._group
            try:
                return self._sort_value < other._sort_value
            except TypeError:
                return str(self._sort_value) < str(other._sort_value)
        return super().__lt__(other)


def _direct_children(
    entries: list[ArchiveEntry], folder: str
) -> tuple[list[str], list[ArchiveEntry]]:
    """현재 폴더 바로 아래의 (하위 폴더 이름들, 파일 엔트리들)을 계산한다.

    아카이브에는 디렉터리 엔트리가 없을 수도 있으므로(zip은 생략 가능),
    파일 경로에서 중간 폴더를 유도해야 목록에서 폴더가 누락되지 않는다.
    """
    prefix = f"{folder}/" if folder else ""
    subfolders: set[str] = set()
    files: list[ArchiveEntry] = []
    for entry in entries:
        name = entry.name.rstrip("/")
        if not name.startswith(prefix) or name == folder:
            continue
        rest = name[len(prefix):]
        if "/" in rest:
            subfolders.add(rest.split("/", 1)[0])
        elif entry.is_dir:
            subfolders.add(rest)
        else:
            files.append(entry)
    return sorted(subfolders), files


class MainWindow(QMainWindow):
    """아카이브 열기/압축/해제/편집을 수행하는 메인 윈도우(탐색기형)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PackNine")
        self.resize(960, 600)
        self.setAcceptDrops(True)
        if _ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(_ICON_PATH)))

        self._compress_service = CompressService()
        self._extract_service = ExtractService()
        self._inspect_service = InspectService()
        self._update_service = UpdateService()

        # 현재 열려있는 아카이브 경로 - "압축 풀기"/"테스트" 액션이 대상으로 사용한다.
        self._current_archive_path: pathlib.Path | None = None
        # 더블클릭한 행이 어떤 엔트리인지 알아야 이미지 뷰어/열기를 수행할 수 있어 보관한다.
        self._current_manifest: ArchiveManifest | None = None
        # 탐색기형 뷰의 현재 폴더(""=루트). 테이블은 이 폴더의 직속 항목만 보여준다.
        self._current_folder: str = ""
        # 현재 아카이브에서 검증된 비밀번호. 열기/해제 어느 시점에 입력받았든 이후
        # 동작(테스트, 미리보기)에서 재입력 없이 재사용한다.
        self._current_password: str | None = None
        # 더블클릭 "기본 프로그램으로 열기"용 임시 폴더들. 외부 프로그램이 파일을 읽는
        # 동안에는 지울 수 없으므로 모아두었다가 창을 닫을 때 일괄 정리한다.
        self._open_temp_dirs: list[pathlib.Path] = []

        self._build_central()
        self._build_toolbar()
        self._build_menus()
        self.statusBar().showMessage("아카이브를 열거나 파일을 끌어다 놓으세요")

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------
    def _build_central(self) -> None:
        # 주소 표시줄: "아카이브명\현재\폴더" - 탐색기처럼 현재 위치를 보여준다.
        self._address_bar = QLineEdit()
        self._address_bar.setReadOnly(True)
        self._address_bar.setPlaceholderText("열린 아카이브 없음")

        # 좌측: 아카이브 내부 폴더 트리
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemClicked.connect(self._on_tree_item_clicked)

        # 우측: 현재 폴더의 파일 목록
        self._table = QTableWidget(0, len(_TABLE_HEADERS))
        self._table.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.cellDoubleClicked.connect(self._on_table_double_clicked)
        self._table.itemSelectionChanged.connect(self._update_status_bar)
        self._table.setColumnWidth(0, 320)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._table)
        # 반디집처럼 좌측 트리는 좁게, 우측 목록을 넓게 시작한다.
        splitter.setSizes([220, 740])
        splitter.setStretchFactor(1, 1)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self._address_bar)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def _std_icon(self, pixmap: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(pixmap)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("메인")
        toolbar.setMovable(False)
        # 반디집처럼 아이콘 아래 텍스트가 있는 큰 버튼 스타일.
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        self.action_open = QAction(self._std_icon(QStyle.StandardPixmap.SP_DirOpenIcon), "열기", self)
        self.action_open.triggered.connect(self._on_open)
        toolbar.addAction(self.action_open)

        self.action_compress = QAction(
            self._std_icon(QStyle.StandardPixmap.SP_FileIcon), "새로 압축", self
        )
        self.action_compress.triggered.connect(self._on_compress)
        toolbar.addAction(self.action_compress)

        self.action_extract = QAction(
            self._std_icon(QStyle.StandardPixmap.SP_DialogSaveButton), "압축 풀기", self
        )
        self.action_extract.triggered.connect(self._on_extract)
        toolbar.addAction(self.action_extract)

        toolbar.addSeparator()

        self.action_add_files = QAction(
            self._std_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "파일 추가", self
        )
        self.action_add_files.triggered.connect(self._on_add_files)
        toolbar.addAction(self.action_add_files)

        self.action_remove_selected = QAction(
            self._std_icon(QStyle.StandardPixmap.SP_TrashIcon), "파일 삭제", self
        )
        self.action_remove_selected.triggered.connect(self._on_remove_selected)
        toolbar.addAction(self.action_remove_selected)

        toolbar.addSeparator()

        self.action_test = QAction(
            self._std_icon(QStyle.StandardPixmap.SP_DialogApplyButton), "테스트", self
        )
        self.action_test.triggered.connect(self._on_test)
        toolbar.addAction(self.action_test)

        self.action_up = QAction(self._std_icon(QStyle.StandardPixmap.SP_ArrowUp), "상위 폴더", self)
        self.action_up.triggered.connect(self._on_navigate_up)
        toolbar.addAction(self.action_up)

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("파일(&F)")
        file_menu.addAction(self.action_open)
        file_menu.addAction(self.action_compress)
        file_menu.addSeparator()
        action_quit = QAction("끝내기(&X)", self)
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        edit_menu = menu_bar.addMenu("편집(&E)")
        edit_menu.addAction(self.action_add_files)
        edit_menu.addAction(self.action_remove_selected)

        tool_menu = menu_bar.addMenu("도구(&T)")
        tool_menu.addAction(self.action_extract)
        tool_menu.addAction(self.action_test)

        help_menu = menu_bar.addMenu("도움말(&H)")
        action_about = QAction("PackNine 정보(&A)", self)
        action_about.triggered.connect(
            lambda: QMessageBox.about(
                self,
                "PackNine 정보",
                "PackNine - 오픈소스 Windows 압축 프로그램\n"
                "ZIP / 7Z / TAR 계열 압축·해제, RAR 해제 지원\n\n"
                "MIT License",
            )
        )
        help_menu.addAction(action_about)

    # ------------------------------------------------------------------
    # 툴바 액션 핸들러
    # ------------------------------------------------------------------
    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "아카이브 열기")
        if not path_str:
            return
        self._open_archive(pathlib.Path(path_str))

    def _on_compress(self) -> None:
        # 지연 import: 다이얼로그 생성 비용을 실제로 필요할 때만 지불하기 위함.
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

    def _on_add_files(self) -> None:
        """열려 있는 아카이브에 파일을 추가한다."""
        if self._current_archive_path is None:
            QMessageBox.information(self, "안내", "먼저 아카이브를 열어주세요.")
            return
        paths_str, _ = QFileDialog.getOpenFileNames(self, "추가할 파일 선택")
        if not paths_str:
            return
        new_paths = [pathlib.Path(p) for p in paths_str]

        progress = self._make_progress_dialog("파일 추가 중...")
        try:
            manifest: ArchiveManifest | None = None

            def _add(password: str | None) -> None:
                nonlocal manifest
                manifest = self._update_service.add_files(
                    self._current_archive_path,
                    new_paths,
                    password=password,
                    on_progress=self._progress_callback(progress),
                )

            completed = self._execute_with_password_retry(_add)
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
        else:
            if completed and manifest is not None:
                self._populate_table(manifest)
                QMessageBox.information(self, "완료", f"{len(new_paths)}개 항목을 추가했습니다.")
        finally:
            progress.close()

    def _on_remove_selected(self) -> None:
        """선택한 엔트리를 아카이브에서 삭제한다."""
        if self._current_archive_path is None or self._current_manifest is None:
            QMessageBox.information(self, "안내", "먼저 아카이브를 열어주세요.")
            return
        entry_names = self._selected_entry_paths()
        if not entry_names:
            QMessageBox.information(self, "안내", "삭제할 항목을 먼저 선택해주세요.")
            return

        answer = QMessageBox.question(
            self,
            "삭제 확인",
            f"선택한 {len(entry_names)}개 항목을 아카이브에서 삭제할까요?\n"
            "(이 작업은 되돌릴 수 없습니다)",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        progress = self._make_progress_dialog("삭제 중...")
        try:
            manifest: ArchiveManifest | None = None

            def _remove(password: str | None) -> None:
                nonlocal manifest
                manifest = self._update_service.remove_entries(
                    self._current_archive_path,
                    entry_names,
                    password=password,
                    on_progress=self._progress_callback(progress),
                )

            completed = self._execute_with_password_retry(_remove)
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
        else:
            if completed and manifest is not None:
                self._populate_table(manifest)
        finally:
            progress.close()

    def _on_navigate_up(self) -> None:
        if not self._current_folder:
            return
        parent = self._current_folder.rsplit("/", 1)[0] if "/" in self._current_folder else ""
        self._navigate_to(parent)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _selected_entry_paths(self) -> list[str]:
        """선택된 행들의 아카이브 내부 전체 경로 목록을 반환한다('..' 행은 제외)."""
        paths: list[str] = []
        for row in sorted({index.row() for index in self._table.selectedIndexes()}):
            item = self._table.item(row, 0)
            if item is None or item.data(_ROLE_KIND) == "up":
                continue
            path = item.data(_ROLE_PATH)
            if path:
                paths.append(path)
        return paths

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
            self._current_password = password
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
            self.setWindowTitle(f"{archive_path.name} - PackNine")
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

    # ------------------------------------------------------------------
    # 탐색기형 뷰 갱신
    # ------------------------------------------------------------------
    def _populate_table(self, manifest: ArchiveManifest) -> None:
        """새 manifest를 받아 루트 폴더 기준으로 트리/목록/주소를 전부 갱신한다."""
        self._current_manifest = manifest
        self._current_folder = ""
        self._rebuild_tree()
        self._refresh_file_list()

    def _navigate_to(self, folder: str) -> None:
        self._current_folder = folder
        self._refresh_file_list()

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        if self._current_manifest is None or self._current_archive_path is None:
            return

        root = QTreeWidgetItem([self._current_archive_path.name])
        root.setIcon(0, self._std_icon(QStyle.StandardPixmap.SP_DriveHDIcon))
        root.setData(0, _ROLE_PATH, "")
        self._tree.addTopLevelItem(root)

        # 파일 경로에서 모든 중간 폴더를 유도한다(zip은 디렉터리 엔트리를 생략할 수 있음).
        folders: set[str] = set()
        for entry in self._current_manifest.entries:
            parts = entry.name.rstrip("/").split("/")
            prefix_parts = parts[:-1] if not entry.is_dir else parts
            for depth in range(1, len(prefix_parts) + 1):
                folders.add("/".join(parts[:depth]))

        nodes: dict[str, QTreeWidgetItem] = {"": root}
        for folder in sorted(folders):
            parent_path = folder.rsplit("/", 1)[0] if "/" in folder else ""
            parent_item = nodes.get(parent_path, root)
            item = QTreeWidgetItem([folder.rsplit("/", 1)[-1]])
            item.setIcon(0, self._std_icon(QStyle.StandardPixmap.SP_DirIcon))
            item.setData(0, _ROLE_PATH, folder)
            parent_item.addChild(item)
            nodes[folder] = item
        root.setExpanded(True)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        folder = item.data(0, _ROLE_PATH)
        if folder is not None:
            self._navigate_to(folder)

    def _refresh_file_list(self) -> None:
        if self._current_manifest is None:
            self._table.setRowCount(0)
            self._address_bar.clear()
            return

        subfolders, files = _direct_children(self._current_manifest.entries, self._current_folder)

        # 채우는 동안 정렬이 켜져 있으면 행이 삽입 즉시 재배열되어 데이터가 섞이므로
        # 반드시 끄고 채운 뒤 다시 켠다(Qt 표준 패턴).
        self._table.setSortingEnabled(False)
        rows: list[tuple[str, str, ArchiveEntry | None]] = []
        if self._current_folder:
            rows.append(("..", "up", None))
        for folder_name in subfolders:
            rows.append((folder_name, "folder", None))
        for entry in files:
            rows.append((entry.name.rsplit("/", 1)[-1], "file", entry))

        # 그룹 우선순위: '..'(0) → 폴더(1) → 파일(2). 어떤 칼럼으로 정렬해도 유지된다.
        _GROUP = {"up": 0, "folder": 1, "file": 2}

        prefix = f"{self._current_folder}/" if self._current_folder else ""
        self._table.setRowCount(len(rows))
        for row, (display_name, kind, entry) in enumerate(rows):
            group = _GROUP[kind]
            name_item = _GroupedItem(group, display_name.lower(), display_name)
            name_item.setData(_ROLE_KIND, kind)
            if kind == "up":
                parent = (
                    self._current_folder.rsplit("/", 1)[0] if "/" in self._current_folder else ""
                )
                name_item.setData(_ROLE_PATH, parent)
                name_item.setIcon(self._std_icon(QStyle.StandardPixmap.SP_FileDialogToParent))
            elif kind == "folder":
                name_item.setData(_ROLE_PATH, f"{prefix}{display_name}")
                name_item.setIcon(self._std_icon(QStyle.StandardPixmap.SP_DirIcon))
            else:
                assert entry is not None
                name_item.setData(_ROLE_PATH, entry.name)
                name_item.setIcon(self._std_icon(QStyle.StandardPixmap.SP_FileIcon))
            self._table.setItem(row, 0, name_item)

            if kind == "file" and entry is not None:
                # 크기 칼럼은 DisplayRole에 숫자를 넣어야 "9 < 10" 같은 숫자 정렬이 된다.
                size_item = _GroupedItem(group, entry.size)
                size_item.setData(Qt.ItemDataRole.DisplayRole, entry.size)
                self._table.setItem(row, 1, size_item)
                compressed_item = _GroupedItem(group, entry.compressed_size)
                compressed_item.setData(Qt.ItemDataRole.DisplayRole, entry.compressed_size)
                self._table.setItem(row, 2, compressed_item)
                ratio = round(entry.compression_ratio, 2)
                ratio_item = _GroupedItem(group, ratio)
                ratio_item.setData(Qt.ItemDataRole.DisplayRole, ratio)
                self._table.setItem(row, 3, ratio_item)
                self._table.setItem(
                    row,
                    4,
                    _GroupedItem(group, entry.modified_at or 0.0, _format_timestamp(entry.modified_at)),
                )
            else:
                for column in range(1, len(_TABLE_HEADERS)):
                    self._table.setItem(row, column, _GroupedItem(group, -1, ""))
        self._table.setSortingEnabled(True)
        # 탐색 진입 시 기본 정렬: 이름 오름차순(그룹 우선은 _GroupedItem이 보장).
        self._table.sortItems(0, Qt.SortOrder.AscendingOrder)

        archive_name = self._current_archive_path.name if self._current_archive_path else ""
        folder_display = self._current_folder.replace("/", "\\")
        self._address_bar.setText(
            f"{archive_name}\\{folder_display}" if folder_display else archive_name
        )
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        if self._current_manifest is None:
            return
        total = len([e for e in self._current_manifest.entries if not e.is_dir])
        selected = len(self._selected_entry_paths())
        message = f"전체 {total}개 파일"
        if selected:
            message += f", {selected}개 선택"
        self.statusBar().showMessage(message)

    # ------------------------------------------------------------------
    # 더블클릭: 폴더 탐색 / 내장 이미지 뷰어 / 기본 프로그램으로 열기
    # ------------------------------------------------------------------
    def _on_table_double_clicked(self, row: int, _column: int) -> None:
        if self._current_manifest is None or self._current_archive_path is None:
            return
        name_item = self._table.item(row, 0)
        if name_item is None:
            return
        kind = name_item.data(_ROLE_KIND)
        path = name_item.data(_ROLE_PATH)
        if kind in ("up", "folder"):
            self._navigate_to(path or "")
            return

        entry = next((e for e in self._current_manifest.entries if e.name == path), None)
        if entry is None or entry.is_dir:
            return
        if is_image_name(entry.name):
            self._open_image_viewer(clicked_entry_name=entry.name)
        else:
            self._open_entry_with_default_app(entry.name)

    def _open_entry_with_default_app(self, entry_name: str) -> None:
        """엔트리를 임시 폴더에 꺼내 OS 기본 연결 프로그램으로 연다."""
        assert self._current_archive_path is not None

        temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="packnine_open_"))
        try:
            completed = self._execute_with_password_retry(
                lambda password: self._extract_service.extract_entries(
                    self._current_archive_path, [entry_name], temp_dir, password=password
                )
            )
        except UnsafeArchiveEntryError as exc:
            self._show_security_warning(exc)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return
        if not completed:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return

        # 외부 프로그램이 파일을 여는 동안 살아있어야 하므로 창 종료 시점까지 보관한다.
        self._open_temp_dirs.append(temp_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(temp_dir / entry_name)))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 네이밍 컨벤션 유지
        for temp_dir in self._open_temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)
        self._open_temp_dirs.clear()
        super().closeEvent(event)

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
