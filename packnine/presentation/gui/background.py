"""오래 걸리는 작업을 작업 스레드로 내보내 GUI가 멈추지 않게 하는 실행기.

왜 필요한가: 예전에는 압축·해제를 GUI 스레드에서 그대로 돌리면서 진행률 콜백 안에서
QApplication.processEvents()를 불러 화면을 갱신했다. 그런데 진행률 콜백은 엔트리
하나를 "다 쓴 뒤"에야 불린다. 6GB짜리 동영상 하나가 든 아카이브라면 그 한 엔트리를
처리하는 몇십 분 동안 이벤트를 단 한 번도 처리하지 못한다. 그 사이 Windows는 창을
응답 없음으로 판정하고 내용 대신 흰 사각형(ghost window)을 그린다. 사용자가 본
"그냥 하얀 창"이 정확히 이것이고, 같은 이유로 이미 닫은 진행률 창이 화면에 남아
비밀번호 입력창을 덮어버렸다.

해결 방식: 작업은 QThread에서 돌리고 GUI 스레드는 중첩 이벤트 루프만 돌린다. 창은
계속 다시 그려지고, 진행률은 시그널로 넘어오므로 스레드 경계를 안전하게 건넌다
(Qt 위젯은 GUI 스레드에서만 만질 수 있다 - 작업 스레드에서 직접 setValue를 부르면
간헐적으로 죽는다).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QEventLoop, QObject, QThread, Signal, Slot

# 진행률 보고 형태: (현재 항목 이름, 진행량, 전체량). 단위는 어댑터가 정한다
# (엔트리 개수이거나 바이트 수). GUI는 비율로만 쓰므로 단위를 알 필요가 없다.
ProgressReporter = Callable[[str, int, int], None]


class ProgressBridge(QObject):
    """작업 스레드 → GUI 스레드로 진행률을 넘기는 통로.

    emit은 어느 스레드에서 불러도 안전하다.

    주의해서 봐야 할 지점: 시그널을 그냥 파이썬 함수에 connect하면 안 된다. Qt는
    수신자가 QObject일 때만 그 객체의 소속 스레드를 보고 큐에 담을지 정하는데,
    평범한 함수에는 소속 스레드가 없어 기본값인 직접 연결이 된다. 그러면 콜백이
    작업 스레드에서 그대로 실행되고, 거기서 위젯을 건드리는 순간(특히 모달
    QProgressDialog.setValue는 내부에서 processEvents를 부른다) 그대로 멈춰 버린다.
    그래서 수신자를 이 객체의 슬롯으로 두고 QueuedConnection을 명시한다.
    """

    progressed = Signal(str, int, int)

    def __init__(self, on_progress: ProgressReporter | None = None) -> None:
        super().__init__()
        self._on_progress = on_progress
        self.progressed.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    @Slot(str, int, int)
    def _deliver(self, name: str, done: int, total: int) -> None:
        if self._on_progress is not None:
            self._on_progress(name, done, total)


class _OperationThread(QThread):
    """operation(report)를 돌리고 예외를 보관했다가 호출자에게 돌려준다."""

    def __init__(self, operation: Callable[[ProgressReporter], None], report: ProgressReporter) -> None:
        super().__init__()
        self._operation = operation
        self._report = report
        self.error: BaseException | None = None

    def run(self) -> None:  # noqa: D102 - QThread 오버라이드
        try:
            self._operation(self._report)
        except BaseException as exc:  # noqa: BLE001 - 호출자가 기존대로 처리하도록 그대로 넘긴다
            self.error = exc


def run_blocking(
    operation: Callable[[ProgressReporter], None],
    on_progress: ProgressReporter | None = None,
) -> None:
    """operation을 작업 스레드에서 끝까지 돌린다. GUI는 그동안 계속 반응한다.

    호출자 입장에서는 동기 함수처럼 보인다(끝날 때까지 돌아오지 않고, 작업 중 발생한
    예외는 이 호출 지점에서 그대로 다시 올라온다). 기존 호출부의 try/except 구조를
    하나도 바꾸지 않고 멈춤만 없애기 위한 의도적인 설계다.
    """
    bridge = ProgressBridge(on_progress)

    thread = _OperationThread(operation, bridge.progressed.emit)
    loop = QEventLoop()
    finished = False

    def _on_finished() -> None:
        nonlocal finished
        finished = True
        loop.quit()

    thread.finished.connect(_on_finished)
    thread.start()
    # finished는 큐를 거쳐 GUI 스레드로 오므로 루프에 들어가기 전에는 처리될 수 없지만,
    # 모달 진행률 창의 setValue가 내부에서 processEvents를 부르며 먼저 집어갈 수 있다.
    # 그 경우 루프에 들어가면 영원히 나오지 못하므로 깃발을 확인하고 건너뛴다.
    while not finished:
        loop.exec()
    thread.wait()

    if thread.error is not None:
        raise thread.error
