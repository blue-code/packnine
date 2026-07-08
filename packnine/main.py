"""패키지 실행 진입점 (`python -m packnine.main` 또는 빌드된 exe에서 사용)."""
from __future__ import annotations

from packnine.presentation.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
