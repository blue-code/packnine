"""Windows 탐색기 우클릭 컨텍스트 메뉴를 수동으로 등록/해제하는 개발용 CLI.

실제 등록/해제 로직은 packnine/infrastructure/context_menu.py에 있다(설치 프로그램과
`packnine register-context-menu` 서브커맨드가 그 모듈을 직접 사용한다). 이 스크립트는
소스 체크아웃 상태에서 exe 빌드 없이 바로 등록/해제해 보고 싶을 때를 위한 얇은 래퍼다.

실행: .venv\\Scripts\\python.exe scripts\\register_context_menu.py [--unregister]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# scripts/는 packnine 패키지 밖에 있으므로, 직접 실행 시 프로젝트 루트를 sys.path에 넣어야
# `packnine.infrastructure`를 임포트할 수 있다(pip install -e . 로 설치된 환경에서는 불필요).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from packnine.infrastructure import context_menu  # noqa: E402 - sys.path 조정 이후에만 import 가능


def main() -> int:
    parser = argparse.ArgumentParser(description="PackNine 탐색기 우클릭 메뉴 등록/해제")
    parser.add_argument("--unregister", action="store_true", help="등록된 메뉴를 제거한다")
    args = parser.parse_args()

    try:
        if args.unregister:
            context_menu.unregister()
            print("PackNine 우클릭 메뉴를 제거했습니다.")
        else:
            context_menu.register()
            print("PackNine 우클릭 메뉴를 등록했습니다.")
    except RuntimeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
