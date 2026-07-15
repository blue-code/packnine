"""context_menu.py 테스트 - 실제 Windows 레지스트리에 대해 왕복 검증한다.

주의: register()/unregister()는 실제로 이 머신의 HKCU 레지스트리를 건드린다. 개발자의
진짜 .zip 등 연결을 망가뜨리지 않도록, 진짜 확장자 목록(_ARCHIVE_EXTENSIONS) 대신 테스트
전용 가짜 확장자로 monkeypatch한 뒤 검증하고 테스트가 끝나면 항상 정리한다.

v0.5부터 개별 verb 대신 "PackNine" 캐스케이드(SubCommands) 하위 메뉴 하나로 묶는다 -
탐색기가 출처(*, SystemFileAssociations, Directory)별로 항목을 흩어 배치해
PackNine 메뉴가 여러 군데 나뉘어 보인다는 피드백에 따른 것이다.
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
    # 키 자체까지 완전히 지워 레지스트리에 잔여물을 남기지 않는다.
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


def _cascade_path(parent: str) -> str:
    return rf"Software\Classes\{parent}\shell\{context_menu._CASCADE_VERB}"


def _sub_command(parent: str, sub_key: str) -> str | None:
    return _query_value(rf"{_cascade_path(parent)}\shell\{sub_key}\command")


def _query_default(ext: str) -> str | None:
    return _query_value(rf"Software\Classes\{ext}")


class TestCascadeRegistration:
    def test_register_creates_single_cascade_per_source(self):
        context_menu.register()

        # 캐스케이드 부모: SubCommands 값이 있어야 탐색기가 하위 메뉴로 그린다.
        for parent in ("*", "Directory", rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}"):
            assert _query_value(_cascade_path(parent), "SubCommands") == "", parent
            assert _query_value(_cascade_path(parent), "MUIVerb") == "PackNine", parent

        context_menu.unregister()

        for parent in ("*", "Directory", rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}"):
            assert _query_value(_cascade_path(parent), "SubCommands") is None, parent

    def test_file_cascade_has_compress_only(self):
        context_menu.register()

        assert "smart-compress" in (_sub_command("*", context_menu._SUB_COMPRESS) or "")
        # 파일 캐스케이드에는 각각 압축하기를 두지 않는다(단일 파일 선택 시 혼란 방지).
        assert _sub_command("*", context_menu._SUB_COMPRESS_EACH) is None

        context_menu.unregister()

    def test_directory_cascade_has_compress_and_each(self):
        context_menu.register()

        assert "smart-compress" in (_sub_command("Directory", context_menu._SUB_COMPRESS) or "")
        each_cmd = _sub_command("Directory", context_menu._SUB_COMPRESS_EACH) or ""
        assert "--each" in each_cmd

        context_menu.unregister()

    def test_archive_cascade_has_extract_here_open_compress(self):
        context_menu.register()
        parent = rf"SystemFileAssociations\{_FAKE_EXTENSIONS[0]}"

        smart_cmd = _sub_command(parent, context_menu._SUB_EXTRACT_SMART) or ""
        here_cmd = _sub_command(parent, context_menu._SUB_EXTRACT_HERE) or ""
        open_cmd = _sub_command(parent, context_menu._SUB_OPEN) or ""

        assert "smart-extract" in smart_cmd and "--here" not in smart_cmd
        assert "smart-extract" in here_cmd and "--here" in here_cmd
        assert " open " in open_cmd
        # 아카이브 캐스케이드에도 압축하기가 있어야 한다('*' 캐스케이드와 같은 verb
        # 이름을 쓰므로 더 구체적인 SystemFileAssociations 쪽이 우선 표시된다).
        assert "smart-compress" in (_sub_command(parent, context_menu._SUB_COMPRESS) or "")

        context_menu.unregister()

    def test_unregister_cleans_legacy_flat_verbs(self):
        # v0.4.x 이하가 등록했던 평면 verb가 남아 있어도 unregister가 정리해야 한다.
        import winreg

        legacy = rf"Software\Classes\{_FAKE_EXTENSIONS[0]}\shell\PackNineExtract\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, legacy) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "legacy command")

        context_menu.register()
        context_menu.unregister()

        assert _query_value(legacy) is None


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
            # 안전망: 테스트가 어디서 실패하든 가짜 키를 남기지 않는다.
            context_menu._delete_tree(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}"
            )

    def test_unregister_without_previous_association_clears_default(self):
        ext = _FAKE_EXTENSIONS[1]
        assert _query_default(ext) is None  # 사전 조건: 원래 아무 연결도 없었음

        context_menu.register()
        assert _query_default(ext) == context_menu._PROG_ID

        context_menu.unregister()
        assert _query_default(ext) is None
