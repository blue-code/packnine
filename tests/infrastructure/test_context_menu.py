"""context_menu.py 테스트 - 실제 Windows 레지스트리에 대해 왕복 검증한다.

주의: register()/unregister()는 실제로 이 머신의 HKCU 레지스트리를 건드린다. 개발자의
진짜 .zip 등 연결을 망가뜨리지 않도록, 진짜 확장자 목록(_ARCHIVE_EXTENSIONS) 대신 테스트
전용 가짜 확장자로 monkeypatch한 뒤 검증하고 테스트가 끝나면 항상 정리한다.
"""
from __future__ import annotations

import sys

import pytest

from packnine.infrastructure import context_menu

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="레지스트리 등록은 Windows 전용 기능입니다"
)

_FAKE_EXTENSIONS = (".pncktest1", ".pncktest2")


@pytest.fixture(autouse=True)
def _use_fake_extensions(monkeypatch):
    # 실제 .zip/.7z 등을 절대 건드리지 않도록 테스트 동안만 가짜 확장자로 바꾼다.
    monkeypatch.setattr(context_menu, "_ARCHIVE_EXTENSIONS", _FAKE_EXTENSIONS)
    yield
    # 테스트가 실패해 unregister를 못 부르는 경우를 대비한 안전망 - 가짜 확장자
    # 키 자체(빈 shell 컨테이너 포함)까지 완전히 지워 레지스트리에 잔여물을 남기지 않는다.
    try:
        context_menu.unregister()
    except Exception:
        pass
    import winreg

    for ext in _FAKE_EXTENSIONS:
        for sub in (
            rf"Software\Classes\{ext}\shell",
            rf"Software\Classes\{ext}",
            rf"Software\Classes\SystemFileAssociations\{ext}\shell",
            rf"Software\Classes\SystemFileAssociations\{ext}",
        ):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass


def _query_default(ext: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
            value, _ = winreg.QueryValueEx(key, "")
            return value or None
    except FileNotFoundError:
        return None


def _query_verb_command(parent: str, verb: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{parent}\shell\{verb}\command"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return value
    except FileNotFoundError:
        return None


def test_compress_and_extract_use_different_verb_names():
    # "*"의 압축하기와 확장자별 압축풀기가 같은 verb 이름을 쓰면 탐색기가 병합하면서
    # 하나만 표시해버리는 실제 버그가 있었다 - 이름이 다른지 직접 확인한다.
    assert context_menu._COMPRESS_VERB != context_menu._EXTRACT_VERB


def test_register_creates_distinct_menu_entries_for_wildcard_and_extension():
    context_menu.register()

    compress_cmd = _query_verb_command("*", context_menu._COMPRESS_VERB)
    # 압축풀기/열기는 확장자 키가 아니라 SystemFileAssociations에 있어야 한다.
    # 확장자 키에 ProgID(기본 프로그램)가 연결되어 있으면 탐색기가 ext\shell의
    # verb를 무시하는데(UserChoice가 다른 앱이면 더더욱), SystemFileAssociations의
    # verb는 기본 프로그램과 무관하게 항상 병합 표시된다 - 실제로 .zip 기본 앱이
    # 탐색기(CompressedFolder)인 환경에서 압축풀기 메뉴가 사라지는 문제가 있었다.
    extract_cmd = _query_verb_command(
        rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}", context_menu._EXTRACT_VERB
    )

    assert compress_cmd is not None and "smart-compress" in compress_cmd
    assert extract_cmd is not None and "smart-extract" in extract_cmd

    context_menu.unregister()

    assert _query_verb_command("*", context_menu._COMPRESS_VERB) is None
    assert (
        _query_verb_command(
            rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}", context_menu._EXTRACT_VERB
        )
        is None
    )


def test_register_creates_open_and_compress_each_entries():
    # 아카이브 "PackNine으로 열기"는 SystemFileAssociations에, "각각 압축하기"는
    # 파일 1개 선택 시 뜨는 혼란을 막기 위해 폴더(Directory) 전용으로 등록한다.
    context_menu.register()

    open_cmd = _query_verb_command(
        rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}", context_menu._OPEN_VERB
    )
    each_cmd = _query_verb_command("Directory", context_menu._COMPRESS_EACH_VERB)
    dir_compress_cmd = _query_verb_command("Directory", context_menu._COMPRESS_VERB)

    assert open_cmd is not None and " open " in open_cmd
    assert each_cmd is not None and "--each" in each_cmd
    # 폴더 우클릭에도 "압축하기"가 있어야 한다('*'는 파일에만 적용되므로 별도 등록).
    assert dir_compress_cmd is not None and "smart-compress" in dir_compress_cmd
    # 파일 전체('*')에는 각각 압축하기를 두지 않는다(단일 파일 선택 시 혼란 방지).
    assert _query_verb_command("*", context_menu._COMPRESS_EACH_VERB) is None

    context_menu.unregister()

    assert (
        _query_verb_command(
            rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}", context_menu._OPEN_VERB
        )
        is None
    )
    assert _query_verb_command("Directory", context_menu._COMPRESS_EACH_VERB) is None
    assert _query_verb_command("Directory", context_menu._COMPRESS_VERB) is None


def test_register_sets_file_association_to_packnine():
    context_menu.register()

    for ext in _FAKE_EXTENSIONS:
        assert _query_default(ext) == context_menu._PROG_ID

    open_cmd = _query_verb_command(context_menu._PROG_ID, "open")
    assert open_cmd is not None and "open" in open_cmd

    context_menu.unregister()


def test_unregister_restores_previous_default_association():
    import winreg

    previous_owner = "SomeOtherApp.Archive"
    ext = _FAKE_EXTENSIONS[0]
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, previous_owner)

    try:
        context_menu.register()
        assert _query_default(ext) == context_menu._PROG_ID

        context_menu.unregister()
        assert _query_default(ext) == previous_owner
    finally:
        # 안전망: 테스트가 어디서 실패하든 가짜 키를 남기지 않는다.
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Classes", 0, winreg.KEY_SET_VALUE
            ) as parent:
                winreg.DeleteKey(parent, ext.lstrip("."))
        except (FileNotFoundError, OSError):
            pass


def test_unregister_without_previous_association_clears_default():
    ext = _FAKE_EXTENSIONS[1]
    assert _query_default(ext) is None  # 사전 조건: 원래 아무 연결도 없었음

    context_menu.register()
    assert _query_default(ext) == context_menu._PROG_ID

    context_menu.unregister()
    assert _query_default(ext) is None
