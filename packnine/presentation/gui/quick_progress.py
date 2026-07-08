"""탐색기 우클릭 메뉴 등으로 콘솔 없이 실행됐을 때 쓰는 경량 진행률 헬퍼.

메인 윈도우를 띄우지 않고 작은 진행률 창만 보여주다가, 성공하면 조용히 사라지고
(반디집처럼 성공 팝업 없음) 실패했을 때만 에러 다이얼로그를 띄운다.
"""
from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from packnine.domain.exceptions import UnsafeArchiveEntryError


def run_with_progress(title: str, operation: Callable[[Callable], None]) -> bool:
    """operation(on_progress)을 진행률 창과 함께 실행하고 성공 여부를 반환한다.

    - operation은 on_progress 콜백 하나를 받는 호출 가능 객체다(예:
      `lambda cb: extract_service.smart_extract(archive, dest, on_progress=cb)`).
    - 취소 버튼은 없음(None으로 지정) - 우클릭 메뉴에서 실행되는 짧은 작업이라
      사용자가 취소할 여지를 주지 않아도 되기 때문이다.
    - 실패 시에만 다이얼로그를 띄우고 False를 반환한다. 성공 팝업은 없다.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    progress = QProgressDialog(title, None, 0, 100)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    progress.show()

    def on_progress(name: str, done: int, total: int) -> None:
        progress.setLabelText(name)
        if total > 0:
            progress.setMaximum(total)
            progress.setValue(done)
        # 진행률 창이 즉시 갱신되도록 이벤트 루프에 양보한다.
        QApplication.processEvents()

    try:
        operation(on_progress)
    except UnsafeArchiveEntryError as exc:
        progress.close()
        QMessageBox.critical(None, "보안 경고", str(exc))
        return False
    except Exception as exc:  # noqa: BLE001 - 우클릭 메뉴 실행 시 크래시 대신 다이얼로그로 알림
        progress.close()
        QMessageBox.critical(None, "오류", str(exc))
        return False
    else:
        progress.close()
        return True
