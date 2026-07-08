"""탐색기 우클릭 메뉴 등록/해제 유스케이스.

presentation 계층이 infrastructure의 winreg 기반 구현을 직접 참조하지 않도록
얇게 감싼다(계층 경계 유지). 실제 레지스트리 조작은 infrastructure.context_menu가 한다.
"""
from __future__ import annotations

from packnine.infrastructure import context_menu


class ContextMenuService:
    """탐색기 우클릭 메뉴(압축/압축해제) 등록·해제를 담당하는 유스케이스."""

    def register(self) -> None:
        context_menu.register()

    def unregister(self) -> None:
        context_menu.unregister()
