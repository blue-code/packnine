"""탐색기 우클릭 메뉴 등록/해제 유스케이스.

presentation 계층이 infrastructure의 winreg 기반 구현을 직접 참조하지 않도록
얇게 감싼다(계층 경계 유지). 실제 레지스트리 조작은 infrastructure.context_menu가 한다.
"""
from __future__ import annotations

from packnine.infrastructure import context_menu, packaged_app


class ContextMenuService:
    """탐색기 우클릭 메뉴(압축/압축해제) 등록·해제를 담당하는 유스케이스."""

    def is_managed_by_windows(self) -> bool:
        """스토어(MSIX) 설치본이라 파일 연결을 Windows가 관리하는 상태인지 알려준다.

        presentation 계층이 infrastructure를 직접 보지 않도록 여기서 한 번 감싼다.
        """
        return packaged_app.is_packaged()

    def register(self) -> None:
        context_menu.register()

    def unregister(self) -> None:
        context_menu.unregister()
