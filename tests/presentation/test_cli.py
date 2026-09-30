"""CLI 서브커맨드(compress/extract/list) end-to-end 스모크 테스트.

main()을 argv 리스트로 직접 호출해 서브프로세스 없이 빠르게 검증한다.
"""
from __future__ import annotations

import pathlib

import pytest

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


def test_smart_extract_without_console_reveals_extracted_item(tmp_path, monkeypatch):
    # 탐색기 우클릭(콘솔 없음)으로 "알아서 풀기" 성공 시, 해제된 항목을 탐색기에서
    # 선택된 상태로 열어 어디에 풀렸는지 바로 보이게 해야 한다(이전에는 진행률 창만
    # 깜빡이고 아무것도 안 보여서 "안 된다"고 느껴졌음).
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
    revealed: list = []
    monkeypatch.setattr(
        "packnine.presentation.cli._reveal_in_explorer",
        lambda p: revealed.append(pathlib.Path(p)),
    )

    exit_code = main(["smart-extract", str(archive)])

    assert exit_code == 0
    # 최상위 폴더가 하나(proj/)라 아카이브와 같은 폴더에 그대로 풀린다.
    assert (tmp_path / "proj" / "f.txt").exists()
    # 해제된 최상위 항목(proj 폴더)이 선택된 상태로 열려야 한다.
    assert revealed == [tmp_path / "proj"]


def test_smart_extract_multi_top_reveals_created_subfolder(tmp_path, monkeypatch):
    # 최상위 항목이 여러 개면 "알아서 풀기"는 아카이브명 하위 폴더를 만들어 푼다.
    # 그 안의 항목을 선택해 열어, 하위 폴더가 생긴 것을 사용자가 바로 알 수 있게 한다.
    import pathlib

    monkeypatch.setattr("sys.stdout", None)

    a = tmp_path / "a.txt"
    a.write_text("a", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("b", encoding="utf-8")
    archive = tmp_path / "bundle.zip"
    assert main(["compress", str(a), str(b), "-o", str(archive)]) == 0

    def _fake_retry(title, operation, archive_name="", initial_password=None):
        operation(None, initial_password)
        return True

    monkeypatch.setattr(
        "packnine.presentation.gui.quick_progress.run_extract_with_password_retry",
        _fake_retry,
    )
    revealed: list = []
    monkeypatch.setattr(
        "packnine.presentation.cli._reveal_in_explorer",
        lambda p: revealed.append(pathlib.Path(p)),
    )

    exit_code = main(["smart-extract", str(archive)])

    assert exit_code == 0
    # 최상위가 여러 개라 bundle/ 하위 폴더에 풀린다.
    assert (tmp_path / "bundle" / "a.txt").exists()
    # 그 하위 폴더 안의 항목이 선택된 채 열려야 한다(부모=bundle 폴더가 보임).
    assert len(revealed) == 1
    assert revealed[0].parent == tmp_path / "bundle"


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


class _FakeCompressDialog:
    """CompressDialog 대역 - 실제 모달 창을 띄우지 않고 입력값을 흉내낸다."""

    class DialogCode:
        Accepted = 1
        Rejected = 0

    accepted = True
    result: tuple | None = None
    seen_files: list[pathlib.Path] | None = None
    seen_destination: pathlib.Path | None = None

    def __init__(self, initial_files=None, parent=None, initial_destination=None):
        type(self).seen_files = initial_files
        type(self).seen_destination = initial_destination

    def exec(self):
        return self.DialogCode.Accepted if type(self).accepted else self.DialogCode.Rejected

    def get_result(self):
        return type(self).result


def _patch_compress_dialog(monkeypatch, *, accepted, result=None):
    from packnine.presentation.gui import compress_dialog as dialog_module

    _FakeCompressDialog.accepted = accepted
    _FakeCompressDialog.result = result
    _FakeCompressDialog.seen_files = None
    _FakeCompressDialog.seen_destination = None
    monkeypatch.setattr(dialog_module, "CompressDialog", _FakeCompressDialog)
    return _FakeCompressDialog


def test_compress_dialog_command_prefills_sources_and_auto_destination(
    qtbot, tmp_path, monkeypatch
):
    # 우클릭 "PackNine으로 압축하기..." 진입 경로: 선택 항목과 자동 계산된 목적지가
    # 다이얼로그에 미리 채워져야 사용자가 확인만 하고 바로 압축할 수 있다.
    from packnine.domain.value_objects import CompressionLevel

    source = tmp_path / "a.txt"
    source.write_text("hello " * 20, encoding="utf-8")
    destination = tmp_path / "custom.zip"
    fake = _patch_compress_dialog(
        monkeypatch, accepted=True, result=([source], destination, None, CompressionLevel.NORMAL, None)
    )

    exit_code = main(["compress-dialog", "--no-collect", str(source)])

    assert exit_code == 0
    assert destination.exists()
    assert fake.seen_files == [source]
    # 자동 목적지는 smart-compress와 동일한 규칙(파일명.zip)을 따른다.
    assert fake.seen_destination == tmp_path / "a.zip"


def test_compress_dialog_command_cancel_creates_nothing(qtbot, tmp_path, monkeypatch):
    source = tmp_path / "a.txt"
    source.write_text("hello", encoding="utf-8")
    _patch_compress_dialog(monkeypatch, accepted=False)

    exit_code = main(["compress-dialog", "--no-collect", str(source)])

    assert exit_code == 0
    assert list(tmp_path.glob("*.zip")) == []


def test_compress_dialog_command_exits_quietly_when_another_instance_leads(
    qtbot, tmp_path, monkeypatch
):
    # 다중 선택 시 탐색기가 항목마다 프로세스를 띄운다. 대표가 아닌 프로세스는
    # 다이얼로그를 만들지 않고 조용히 끝나야 창이 여러 개 뜨지 않는다.
    from packnine.application import selection_collector
    from packnine.presentation.gui import compress_dialog as dialog_module

    source = tmp_path / "a.txt"
    source.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(selection_collector, "collect_selection", lambda *a, **k: None)

    created = []

    class _ShouldNotBeCreated:
        def __init__(self, *args, **kwargs):
            created.append(args)

    monkeypatch.setattr(dialog_module, "CompressDialog", _ShouldNotBeCreated)

    exit_code = main(["compress-dialog", str(source)])

    assert exit_code == 0
    assert created == []


def test_compress_dialog_command_uses_collected_paths(qtbot, tmp_path, monkeypatch):
    # 대표 프로세스는 다른 프로세스가 남긴 경로까지 합쳐서 다이얼로그에 채운다.
    from packnine.application import selection_collector
    from packnine.domain.value_objects import CompressionLevel

    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    for path in (first, second):
        path.write_text("hello " * 20, encoding="utf-8")
    destination = tmp_path / "merged.zip"

    monkeypatch.setattr(
        selection_collector, "collect_selection", lambda *a, **k: [str(first), str(second)]
    )
    fake = _patch_compress_dialog(
        monkeypatch,
        accepted=True,
        result=([first, second], destination, None, CompressionLevel.NORMAL, None),
    )

    exit_code = main(["compress-dialog", str(first)])

    assert exit_code == 0
    assert fake.seen_files == [first, second]
    assert destination.exists()


def _make_incompressible_source(tmp_path: pathlib.Path) -> pathlib.Path:
    import os

    src = tmp_path / "blob.bin"
    src.write_bytes(os.urandom(2_500_000))
    return src


def test_compress_with_volume_size_splits_and_reports_volumes(tmp_path, capsys):
    src = _make_incompressible_source(tmp_path)
    archive_path = tmp_path / "out.7z"

    exit_code = main(["compress", str(src), "-o", str(archive_path), "--volume-size", "1"])

    assert exit_code == 0
    assert not archive_path.exists()
    assert (tmp_path / "out.7z.001").exists()
    assert (tmp_path / "out.7z.003").exists()
    output = capsys.readouterr().out
    assert "out.7z.001" in output
    assert "볼륨" in output


def test_list_and_extract_accept_first_volume(tmp_path, capsys):
    src = _make_incompressible_source(tmp_path)
    archive_path = tmp_path / "out.zip"
    assert main(["compress", str(src), "-o", str(archive_path), "--volume-size", "1"]) == 0
    capsys.readouterr()
    first_volume = tmp_path / "out.zip.001"

    assert main(["list", str(first_volume)]) == 0
    assert "blob.bin" in capsys.readouterr().out

    destination = tmp_path / "extracted"
    assert main(["extract", str(first_volume), "-d", str(destination)]) == 0
    assert (destination / "blob.bin").read_bytes() == src.read_bytes()


def test_compress_volume_size_zero_is_rejected(tmp_path, capsys):
    # SystemExit로 끝내면 콘솔 없는 실행에서 main()이 모달 메시지 박스를 띄우므로,
    # 다른 입력 오류와 같이 종료 코드 1 + stderr 안내로 처리해야 한다.
    src = _make_incompressible_source(tmp_path)

    exit_code = main(["compress", str(src), "-o", str(tmp_path / "out.zip"), "--volume-size", "0"])

    assert exit_code == 1
    assert "volume-size" in capsys.readouterr().err
    assert list(tmp_path.glob("out.zip*")) == []


def test_compress_volume_size_with_tar_fails_cleanly(tmp_path, capsys):
    src = _make_incompressible_source(tmp_path)

    exit_code = main(
        ["compress", str(src), "-o", str(tmp_path / "out.tar.gz"), "--volume-size", "1"]
    )

    assert exit_code == 1
    assert "분할" in capsys.readouterr().err


def test_compress_dialog_command_passes_volume_size_to_service(qtbot, tmp_path, monkeypatch):
    from packnine.domain.value_objects import CompressionLevel, VolumeSize

    src = _make_incompressible_source(tmp_path)
    destination = tmp_path / "split.7z"
    _patch_compress_dialog(
        monkeypatch,
        accepted=True,
        result=([src], destination, None, CompressionLevel.NORMAL, VolumeSize.from_megabytes(1)),
    )

    exit_code = main(["compress-dialog", "--no-collect", str(src)])

    assert exit_code == 0
    assert not destination.exists()
    assert (tmp_path / "split.7z.001").exists()


def test_smart_compress_each_accepts_jobs_option(tmp_path, capsys, monkeypatch):
    # -j는 동시 실행 개수 상한이다. 1로 줘도 결과는 동일해야 한다(순차 경로 회귀 방지).
    monkeypatch.setattr("packnine.presentation.cli._has_console", lambda: True)
    sources = []
    for name in ("a.txt", "b.txt", "c.txt"):
        path = tmp_path / name
        path.write_text(f"{name} " * 50, encoding="utf-8")
        sources.append(str(path))

    exit_code = main(["smart-compress", "--each", "-j", "1", *sources])

    assert exit_code == 0
    assert {p.name for p in tmp_path.glob("*.zip")} == {"a.zip", "b.zip", "c.zip"}
    assert capsys.readouterr().out.count("성공") == 3


def test_extract_on_conflict_skip_keeps_existing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("packnine.presentation.cli._has_console", lambda: True)
    source = tmp_path / "a.txt"
    source.write_text("아카이브 내용", encoding="utf-8")
    archive = tmp_path / "out.zip"
    assert main(["compress", str(source), "-o", str(archive)]) == 0
    capsys.readouterr()

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("기존 내용", encoding="utf-8")

    exit_code = main(["extract", str(archive), "-d", str(dest), "--on-conflict", "skip"])

    assert exit_code == 0
    assert (dest / "a.txt").read_text(encoding="utf-8") == "기존 내용"


def test_smart_extract_on_conflict_rename_keeps_both(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("packnine.presentation.cli._has_console", lambda: True)
    source = tmp_path / "a.txt"
    source.write_text("아카이브 내용", encoding="utf-8")
    archive = tmp_path / "out.zip"
    assert main(["compress", str(source), "-o", str(archive)]) == 0
    capsys.readouterr()

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("기존 내용", encoding="utf-8")

    exit_code = main(
        ["smart-extract", str(archive), "--dest-dir", str(dest), "--here", "--on-conflict", "rename"]
    )

    assert exit_code == 0
    assert (dest / "a.txt").read_text(encoding="utf-8") == "기존 내용"
    assert (dest / "a_2.txt").read_text(encoding="utf-8") == "아카이브 내용"


def test_compress_exclude_option_skips_patterns(tmp_path, capsys):
    src = tmp_path / "proj"
    (src / ".git").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (src / "keep.txt").write_text("keep " * 40, encoding="utf-8")
    archive = tmp_path / "out.zip"

    exit_code = main(["compress", str(src), "-o", str(archive), "--exclude", ".git"])

    assert exit_code == 0
    capsys.readouterr()
    assert main(["list", str(archive)]) == 0
    listing = capsys.readouterr().out
    assert "keep.txt" in listing
    assert "HEAD" not in listing
