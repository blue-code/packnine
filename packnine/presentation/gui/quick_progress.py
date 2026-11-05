"""탐색기 우클릭 메뉴 등으로 콘솔 없이 실행됐을 때 쓰는 경량 진행률 헬퍼.

메인 윈도우를 띄우지 않고 작은 진행률 창만 보여주다가, 성공하면 조용히 사라지고
(반디집처럼 성공 팝업 없음) 실패했을 때만 에러 다이얼로그를 띄운다.

실제 작업은 background.run_blocking이 작업 스레드에서 돌린다. GUI 스레드에서 직접
돌리던 시절에는 큰 파일 하나를 푸는 동안 창이 흰 사각형으로 굳었고, 닫은 진행률 창이
화면에 남아 비밀번호 입력창을 덮었다. 자세한 배경은 background 모듈 주석 참고.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
)

from packnine.domain.exceptions import InvalidPasswordError, UnsafeArchiveEntryError
from packnine.presentation.gui import background

# 우클릭 메뉴로 실행되는 경로는 MainWindow를 거치지 않아 앱 아이콘이 설정되지 않는다.
# 그대로 두면 진행률 창과 작업 표시줄에 기본 아이콘이 뜬다.
_ICON_PATH = pathlib.Path(__file__).resolve().parent / "assets" / "icon.ico"


def _ensure_app(argv: list[str]) -> QApplication:
    """QApplication을 얻고(없으면 만들고) 앱 아이콘을 보장한다."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv)
    if app.windowIcon().isNull() and _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    return app


def _make_progress(title: str) -> QProgressDialog:
    """진행률 창을 만든다. 취소 버튼은 두지 않는다(None).

    ApplicationModal을 쓰는 이유: 작업이 작업 스레드로 넘어가면서 GUI가 계속 살아 있게
    됐고, 그만큼 사용자가 작업 중에 다른 창을 눌러 같은 작업을 또 시작할 수 있게 됐다.
    부모 창이 없는 독립 실행 경로라 WindowModal은 아무것도 막지 못하므로
    ApplicationModal로 입력을 막는다.
    """
    progress = QProgressDialog(title, None, 0, 100)
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)
    progress.show()
    return progress


def _dismiss(progress: QProgressDialog) -> None:
    """진행률 창을 화면에서 확실히 걷어낸다.

    close()만으로는 부족하다. 바로 뒤에 모달 창(비밀번호 입력)을 띄우면 아직 파괴되지
    않은 진행률 창이 화면에 남아 그 위를 덮는 일이 있었다. 숨기고, 파괴를 예약하고,
    예약된 파괴가 실제로 처리되도록 이벤트 루프를 한 번 돌려 준다.
    """
    progress.hide()
    progress.close()
    progress.deleteLater()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _progress_updater(progress: QProgressDialog) -> Callable[[str, int, int], None]:
    """진행률 창을 갱신하는 GUI 스레드용 슬롯을 만든다."""

    def _update(name: str, done: int, total: int) -> None:
        progress.setLabelText(name)
        if total > 0:
            progress.setMaximum(total)
            progress.setValue(done)

    return _update


def run_with_progress(title: str, operation: Callable[[Callable], None]) -> bool:
    """operation(on_progress)을 진행률 창과 함께 실행하고 성공 여부를 반환한다.

    - operation은 on_progress 콜백 하나를 받는 호출 가능 객체다(예:
      `lambda cb: extract_service.smart_extract(archive, dest, on_progress=cb)`).
    - 실패 시에만 다이얼로그를 띄우고 False를 반환한다. 성공 팝업은 없다.
    """
    _ensure_app(sys.argv)

    progress = _make_progress(title)
    try:
        background.run_blocking(operation, _progress_updater(progress))
    except UnsafeArchiveEntryError as exc:
        _dismiss(progress)
        QMessageBox.critical(None, "보안 경고", str(exc))
        return False
    except Exception as exc:  # noqa: BLE001 - 우클릭 메뉴 실행 시 크래시 대신 다이얼로그로 알림
        _dismiss(progress)
        QMessageBox.critical(None, "오류", str(exc))
        return False
    else:
        _dismiss(progress)
        return True


def run_extract_with_password_retry(
    title: str,
    operation: Callable[[Callable, str | None], None],
    *,
    archive_name: str = "아카이브",
    initial_password: str | None = None,
) -> bool:
    """암호가 걸린 아카이브 해제용 진행률 헬퍼.

    operation(on_progress, password)가 InvalidPasswordError를 던지면 비밀번호 입력
    다이얼로그를 띄워 재시도한다(우클릭 "압축풀기"로 암호 zip을 만난 사용자가
    입력 기회를 얻지 못하고 실패만 보는 문제 방지). 입력을 취소하면 조용히 중단한다.
    """
    _ensure_app(sys.argv)

    password = initial_password
    while True:
        succeeded = _run_once_or_password_error(title, operation, password)
        if succeeded is not None:
            return succeeded
        text, ok = QInputDialog.getText(
            None,
            "비밀번호 필요",
            f"'{archive_name}'의 비밀번호를 입력하세요:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not text:
            return False
        password = text


def _run_once_or_password_error(
    title: str,
    operation: Callable[[Callable, str | None], None],
    password: str | None,
) -> bool | None:
    """한 번 실행을 시도하고 성공(True)/실패(False)/비밀번호 오류(None)를 구분해 반환한다."""
    progress = _make_progress(title)
    try:
        background.run_blocking(
            lambda report: operation(report, password),
            _progress_updater(progress),
        )
    except InvalidPasswordError:
        # 비밀번호 입력창을 띄우기 전에 진행률 창을 반드시 먼저 치운다.
        _dismiss(progress)
        return None
    except UnsafeArchiveEntryError as exc:
        _dismiss(progress)
        QMessageBox.critical(None, "보안 경고", str(exc))
        return False
    except Exception as exc:  # noqa: BLE001 - 우클릭 메뉴 실행 시 크래시 대신 다이얼로그로 알림
        _dismiss(progress)
        QMessageBox.critical(None, "오류", str(exc))
        return False
    else:
        _dismiss(progress)
        return True
