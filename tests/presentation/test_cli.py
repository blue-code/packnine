"""CLI 서브커맨드(compress/extract/list) end-to-end 스모크 테스트.

main()을 argv 리스트로 직접 호출해 서브프로세스 없이 빠르게 검증한다.
"""
from __future__ import annotations

import pathlib

from packnine.presentation.cli import _has_console, main


def _make_source_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("hello a", encoding="utf-8")
    (src_dir / "b.txt").write_text("hello b " * 20, encoding="utf-8")
    return src_dir


def test_compress_then_list(tmp_path, capsys):
    src_dir = _make_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"

    exit_code = main(
        ["compress", str(src_dir / "a.txt"), str(src_dir / "b.txt"), "-o", str(archive_path)]
    )
    assert exit_code == 0
    assert archive_path.exists()
    compress_output = capsys.readouterr().out
    assert "압축 완료" in compress_output

    exit_code = main(["list", str(archive_path)])
    assert exit_code == 0
    list_output = capsys.readouterr().out
    assert "a.txt" in list_output
    assert "b.txt" in list_output


def test_compress_then_extract_round_trip(tmp_path, capsys):
    src_dir = _make_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    destination = tmp_path / "extracted"

    assert main(
        ["compress", str(src_dir / "a.txt"), str(src_dir / "b.txt"), "-o", str(archive_path)]
    ) == 0
    capsys.readouterr()

    exit_code = main(["extract", str(archive_path), "-d", str(destination)])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "압축 해제 완료" in output

    assert (destination / "a.txt").read_text(encoding="utf-8") == "hello a"
    assert (destination / "b.txt").read_text(encoding="utf-8") == "hello b " * 20


def test_extract_missing_archive_returns_exit_code_1_with_friendly_message(tmp_path, capsys):
    missing_archive = tmp_path / "does_not_exist.zip"
    destination = tmp_path / "out"

    exit_code = main(["extract", str(missing_archive), "-d", str(destination)])

    assert exit_code == 1
    captured = capsys.readouterr()
    # 스택트레이스가 아니라 사용자 친화적 메시지가 stderr로 나가야 한다.
    assert "Traceback" not in captured.err
    assert captured.err.strip() != ""


def test_smart_compress_single_file_uses_stem_name(tmp_path, capsys, monkeypatch):
    # 콘솔이 연결되어 있는 상황(터미널에서 직접 실행)을 흉내내 텍스트 출력 분기를 탄다.
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    report = src_dir / "report.docx"
    report.write_text("dummy content", encoding="utf-8")

    exit_code = main(["smart-compress", str(report)])

    assert exit_code == 0
    expected_destination = src_dir / "report.zip"
    assert expected_destination.exists()
    output = capsys.readouterr().out
    assert "압축 완료" in output
    assert str(expected_destination) in output


def test_smart_compress_each_creates_one_archive_per_source(tmp_path, capsys, monkeypatch):
    # 반디집 "각각 압축하기": 여러 항목을 선택해도 하나로 묶지 않고 항목별 zip을 만든다.
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    a = tmp_path / "alpha.txt"
    a.write_text("aaa", encoding="utf-8")
    b = tmp_path / "beta.txt"
    b.write_text("bbb", encoding="utf-8")

    exit_code = main(["smart-compress", "--each", str(a), str(b)])

    assert exit_code == 0
    assert (tmp_path / "alpha.zip").exists()
    assert (tmp_path / "beta.zip").exists()
    output = capsys.readouterr().out
    assert "alpha.zip" in output and "beta.zip" in output


def test_smart_compress_each_continues_after_one_failure(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    good = tmp_path / "good.txt"
    good.write_text("ok", encoding="utf-8")
    missing = tmp_path / "does_not_exist.txt"

    exit_code = main(["smart-compress", "--each", str(missing), str(good)])

    assert exit_code == 1
    assert (tmp_path / "good.zip").exists()
    output = capsys.readouterr().out
    assert "실패" in output


def test_smart_extract_multiple_archives_each_processed(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    src_dir = _make_source_tree(tmp_path)
    archive_a = tmp_path / "out_a.zip"
    archive_b = tmp_path / "out_b.zip"
    assert main(["compress", str(src_dir), "-o", str(archive_a)]) == 0
    assert main(["compress", str(src_dir), "-o", str(archive_b)]) == 0
    capsys.readouterr()

    exit_code = main(["smart-extract", str(archive_a), str(archive_b)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"성공: {archive_a}" in output
    assert f"성공: {archive_b}" in output
    # 소스 트리 자체가 유일한 최상위 항목이므로 아카이브와 같은 폴더 아래 src_dir.name으로 풀린다.
    assert (tmp_path / src_dir.name / "a.txt").exists()


def test_smart_extract_here_ignores_smart_wrapping(tmp_path, capsys, monkeypatch):
    # "여기에 풀기": 최상위 항목이 여러 개라도 하위 폴더를 만들지 않고
    # 아카이브와 같은 폴더에 내용물을 그대로 푼다(알아서 풀기와의 차이점).
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    a = tmp_path / "a.txt"
    a.write_text("aaa", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("bbb", encoding="utf-8")
    archive_path = tmp_path / "loose.zip"
    assert main(["compress", str(a), str(b), "-o", str(archive_path)]) == 0
    a.unlink()
    b.unlink()
    capsys.readouterr()

    exit_code = main(["smart-extract", "--here", str(archive_path)])

    assert exit_code == 0
    # 알아서 풀기라면 tmp_path/loose/ 폴더가 생겼겠지만, 여기에 풀기는 만들지 않는다.
    assert not (tmp_path / "loose").exists()
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "aaa"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "bbb"


def test_smart_extract_continues_after_one_failure(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    src_dir = _make_source_tree(tmp_path)
    good_archive = tmp_path / "good.zip"
    assert main(["compress", str(src_dir), "-o", str(good_archive)]) == 0
    capsys.readouterr()

    missing_archive = tmp_path / "does_not_exist.zip"

    exit_code = main(["smart-extract", str(missing_archive), str(good_archive)])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert f"실패: {missing_archive}" in output
    assert f"성공: {good_archive}" in output


def test_has_console_false_when_stdout_is_none(monkeypatch):
    # PyInstaller windowed(console=False) 빌드가 탐색기에서 콘솔 없이 실행되면
    # sys.stdout 자체가 None이 된다 - 이전에는 .isatty() 호출이 AttributeError로
    # 죽어서 우클릭 메뉴가 "아무 반응 없는" 것처럼 보이는 버그가 있었다.
    monkeypatch.setattr("sys.stdout", None)
    assert _has_console() is False


def test_has_console_true_for_real_tty(monkeypatch):
    class _FakeTTYStdout:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("sys.stdout", _FakeTTYStdout())
    assert _has_console() is True


def test_smart_compress_works_without_console(tmp_path, monkeypatch):
    # sys.stdout이 None인(콘솔 없는 windowed 실행) 상황을 그대로 재현해,
    # 회귀가 다시 생기면 여기서 AttributeError로 바로 드러나게 한다.
    monkeypatch.setattr("sys.stdout", None)

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    report = src_dir / "report.docx"
    report.write_text("dummy content", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        "packnine.presentation.gui.quick_progress.run_with_progress",
        lambda title, operation: (calls.append(title), operation(None), True)[-1],
    )

    exit_code = main(["smart-compress", str(report)])

    assert exit_code == 0
    assert (src_dir / "report.zip").exists()
    assert calls == ["압축 중..."]


def test_smart_extract_without_console_opens_result_folder(tmp_path, monkeypatch):
    # 탐색기 우클릭(콘솔 없음)으로 "알아서 풀기" 성공 시, 결과 폴더를 탐색기로 열어
    # 시각적 피드백을 줘야 한다(이전에는 진행률 창만 깜빡이고 아무것도 안 보였음).
    import pathlib

    monkeypatch.setattr("sys.stdout", None)

    src_dir = tmp_path / "proj"
    src_dir.mkdir()
    (src_dir / "f.txt").write_text("x", encoding="utf-8")
    archive = tmp_path / "proj.zip"
    assert main(["compress", str(src_dir), "-o", str(archive)]) == 0

    # 진행률 창은 실제로 띄우지 않고 operation만 실행해 성공시킨다.
    def _fake_retry(title, operation, archive_name="", initial_password=None):
        operation(None, initial_password)
        return True

    monkeypatch.setattr(
        "packnine.presentation.gui.quick_progress.run_extract_with_password_retry",
        _fake_retry,
    )
    opened: list = []
    monkeypatch.setattr(
        "packnine.presentation.cli._open_folder",
        lambda p: opened.append(pathlib.Path(p)),
    )

    exit_code = main(["smart-extract", str(archive)])

    assert exit_code == 0
    # 최상위 폴더가 하나(proj/)라 아카이브와 같은 폴더에 그대로 풀린다.
    assert (tmp_path / "proj" / "f.txt").exists()
    # 결과 폴더가 탐색기로 열려야 한다.
    assert opened == [tmp_path]


def test_open_command_launches_gui_with_archive(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "packnine.presentation.gui.main_window.run_gui",
        lambda initial_archive=None: calls.append(initial_archive) or 0,
    )

    archive_path = tmp_path / "out.zip"
    exit_code = main(["open", str(archive_path)])

    assert exit_code == 0
    assert calls == [archive_path]


def test_register_context_menu_calls_service(monkeypatch, capsys):
    from packnine.application.context_menu_service import ContextMenuService

    calls = []
    monkeypatch.setattr(ContextMenuService, "register", lambda self: calls.append("register"))
    monkeypatch.setattr(ContextMenuService, "unregister", lambda self: calls.append("unregister"))

    assert main(["register-context-menu"]) == 0
    assert calls == ["register"]
    assert "등록했습니다" in capsys.readouterr().out

    assert main(["register-context-menu", "--unregister"]) == 0
    assert calls == ["register", "unregister"]
    assert "제거했습니다" in capsys.readouterr().out


def test_register_context_menu_failure_returns_friendly_error(monkeypatch, capsys):
    from packnine.application.context_menu_service import ContextMenuService

    def _boom(self):
        raise RuntimeError("레지스트리 접근 실패")

    monkeypatch.setattr(ContextMenuService, "register", _boom)

    exit_code = main(["register-context-menu"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "레지스트리 접근 실패" in captured.err


def test_compress_with_password(tmp_path, capsys):
    src_dir = _make_source_tree(tmp_path)
    archive_path = tmp_path / "secure.zip"

    exit_code = main(
        [
            "compress",
            str(src_dir / "a.txt"),
            "-o",
            str(archive_path),
            "--password",
            "s3cret!",
        ]
    )
    assert exit_code == 0
    assert archive_path.exists()

    exit_code = main(["list", str(archive_path), "--password", "s3cret!"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "a.txt" in output
