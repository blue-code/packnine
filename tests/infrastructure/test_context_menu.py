"""context_menu.py 테스트 - 실제 Windows 레지스트리에 대해 왕복 검증한다.

주의: register()/unregister()는 실제로 이 머신의 HKCU 레지스트리를 건드린다. 개발자의
진짜 .zip 등 연결을 망가뜨리지 않도록, 진짜 확장자 목록(_ARCHIVE_EXTENSIONS) 대신 테스트
전용 가짜 확장자로 monkeypatch한 뒤 검증하고 테스트가 끝나면 항상 정리한다.

v0.5.3부터 캐스케이드(SubCommands 하위 메뉴)를 버리고 다시 '평면 verb'로 돌아왔다.
캐스케이드는 레거시 Shell.Verbs()/일부 탐색기 경로에서 명령이 실행되지 않아(파일 인자가
전달 안 되거나 아예 안 뜸) "알아서 풀기가 반응 없음" 문제를 일으켰다. 평면 verb는 모든
탐색기 컨텍스트에서 %*로 파일 경로를 확실히 받아 실행된다(각 verb에 아이콘을 붙여
시각적으로 PackNine 항목임을 구분한다).
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
    try:
        context_menu.unregister()
    except Exception:
        pass
    import winreg

    for ext in _FAKE_EXTENSIONS:
        for sub in (
            rf"Software\Classes\SystemFileAssociations\{ext}",
            rf"Software\Classes\{ext}",
        ):
            context_menu._delete_tree(winreg.HKEY_CURRENT_USER, sub)


def _query_value(key_path: str, value_name: str = "") -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return value
    except FileNotFoundError:
        return None


def _verb_command(parent: str, verb: str) -> str | None:
    return _query_value(rf"Software\Classes\{parent}\shell\{verb}\command")


def _verb_has_icon(parent: str, verb: str) -> bool:
    return _query_value(rf"Software\Classes\{parent}\shell\{verb}", "Icon") is not None


def _query_default(ext: str) -> str | None:
    return _query_value(rf"Software\Classes\{ext}")


class TestFlatVerbRegistration:
    def test_file_gets_compress_verb_with_path_arg_and_icon(self):
        context_menu.register()

        cmd = _verb_command("*", context_menu._COMPRESS_VERB)
        # 파일 경로가 "%1"로 전달되어야 실제 클릭 시 실행된다. %*는 실제 탐색기에서
        # 경로가 비어 전달돼(silent fail) "알아서 풀기 반응 없음"의 원인이었다 - 회귀 금지.
        assert cmd is not None and "smart-compress" in cmd and '"%1"' in cmd
        assert "%*" not in cmd
        assert _verb_has_icon("*", context_menu._COMPRESS_VERB)

        context_menu.unregister()
        assert _verb_command("*", context_menu._COMPRESS_VERB) is None

    def test_folder_gets_compress_and_compress_each(self):
        context_menu.register()

        compress = _verb_command("Directory", context_menu._COMPRESS_VERB) or ""
        each = _verb_command("Directory", context_menu._COMPRESS_EACH_VERB) or ""
        assert "smart-compress" in compress and '"%1"' in compress
        assert "--each" in each and '"%1"' in each

        context_menu.unregister()

    def test_archive_gets_extract_smart_here_and_open(self):
        context_menu.register()
        parent = rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}"

        smart = _verb_command(parent, context_menu._EXTRACT_SMART_VERB) or ""
        here = _verb_command(parent, context_menu._EXTRACT_HERE_VERB) or ""
        open_cmd = _verb_command(parent, context_menu._OPEN_VERB) or ""

        # 알아서 풀기: 파일 경로 "%1" 전달, --here 없음
        assert "smart-extract" in smart and '"%1"' in smart and "--here" not in smart
        # 여기에 풀기: --here + "%1"
        assert "smart-extract" in here and "--here" in here and '"%1"' in here
        # 열기: GUI로 아카이브 열기
        assert " open " in open_cmd and '"%1"' in open_cmd
        # 모든 verb에 %*가 없어야 한다(회귀 방지).
        assert "%*" not in smart and "%*" not in here

        context_menu.unregister()
        assert _verb_command(parent, context_menu._EXTRACT_SMART_VERB) is None

    def test_unregister_cleans_legacy_cascade_and_flat_verbs(self):
        # 과거 버전이 남긴 캐스케이드/구식 평면 verb가 있어도 정리되어야 한다.
        import winreg

        ext = _FAKE_EXTENSIONS[0]
        legacy_cascade = rf"Software\Classes\SystemFileAssociations\{ext}\shell\PackNine\shell\x\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, legacy_cascade) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "legacy")

        context_menu.register()
        context_menu.unregister()

        assert (
            _query_value(rf"Software\Classes\SystemFileAssociations\{ext}\shell\PackNine")
            is None
        )


class TestFileAssociation:
    def test_register_sets_file_association_to_packnine(self):
        context_menu.register()

        for ext in _FAKE_EXTENSIONS:
            assert _query_default(ext) == context_menu._PROG_ID

        open_cmd = _query_value(
            rf"Software\Classes\{context_menu._PROG_ID}\shell\open\command"
        )
        assert open_cmd is not None and "open" in open_cmd

        context_menu.unregister()

    def test_unregister_restores_previous_default_association(self):
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
            context_menu._delete_tree(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}"
            )

    def test_unregister_without_previous_association_clears_default(self):
        ext = _FAKE_EXTENSIONS[1]
        assert _query_default(ext) is None

        context_menu.register()
        assert _query_default(ext) == context_menu._PROG_ID

        context_menu.unregister()
        assert _query_default(ext) is None
