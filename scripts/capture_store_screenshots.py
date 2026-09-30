"""스토어 리스팅용 스크린샷을 만든다.

사용법:
    python scripts/capture_store_screenshots.py [출력폴더]

마이크로소프트 스토어는 데스크톱 앱 리스팅에 최소 1장의 스크린샷을 요구하며 권장 해상도는
1366x768 이상이다. 수동으로 캡처하면 창 크기와 내용이 매번 달라져 재현이 안 되므로,
실제 MainWindow를 정해진 크기로 띄우고 QWidget.grab()으로 찍는다(오프스크린에서도 동작).

샘플 아카이브는 임시 폴더에 매번 새로 만든다 - 개인 파일이 스크린샷에 섞여 들어가면
안 되기 때문이다.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_WIDTH = 1366
_HEIGHT = 768


def _build_sample_archive(work_dir: pathlib.Path) -> pathlib.Path:
    """스크린샷에 보여줄 샘플 아카이브를 만든다(내용은 전부 가짜 파일)."""
    from packnine.application.compress_service import CompressService

    source = work_dir / "프로젝트 자료"
    (source / "문서").mkdir(parents=True)
    (source / "사진").mkdir(parents=True)

    (source / "문서" / "기획안.txt").write_text("기획안 내용 " * 400, encoding="utf-8")
    (source / "문서" / "회의록.txt").write_text("회의록 내용 " * 250, encoding="utf-8")
    (source / "문서" / "예산표.csv").write_text("항목,금액\n" + "자재비,120000\n" * 80, encoding="utf-8")
    (source / "사진" / "현장01.txt").write_text("사진 자리 " * 300, encoding="utf-8")
    (source / "사진" / "현장02.txt").write_text("사진 자리 " * 320, encoding="utf-8")
    (source / "읽어보기.txt").write_text("샘플 아카이브입니다. " * 120, encoding="utf-8")

    archive_path = work_dir / "프로젝트 자료.zip"
    CompressService().compress([source], archive_path)
    return archive_path


def capture(output_dir: pathlib.Path) -> list[pathlib.Path]:
    from PySide6.QtWidgets import QApplication

    from packnine.presentation.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[pathlib.Path] = []

    with tempfile.TemporaryDirectory(prefix="packnine_shot_") as temp_name:
        work_dir = pathlib.Path(temp_name)
        archive_path = _build_sample_archive(work_dir)

        window = MainWindow()
        window.resize(_WIDTH, _HEIGHT)
        window.show()
        window._open_archive(archive_path)
        app.processEvents()

        # 1) 아카이브를 연 기본 화면
        target = output_dir / "01-archive-view.png"
        window.grab().save(str(target))
        saved.append(target)

        # 2) 폴더로 들어간 화면 - 탐색기식 탐색을 보여준다
        window._navigate_to("프로젝트 자료/문서")
        app.processEvents()
        target = output_dir / "02-folder-view.png"
        window.grab().save(str(target))
        saved.append(target)

        window.close()

    return saved


def main() -> int:
    output_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else _PROJECT_ROOT / "dist" / "store-screenshots"
    for path in capture(output_dir):
        print(f"저장: {path} ({path.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
