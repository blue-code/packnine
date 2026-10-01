"""MSIX 매니페스트 생성 테스트.

매니페스트는 업로드 단계에서야 검증되므로(왕복이 수십 분) 여기서 미리 계약을 잡아둔다.
특히 Identity 3종은 Partner Center가 발급한 값과 한 글자라도 다르면 업로드가 거절된다.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from scripts import build_msix


def test_version_is_four_parts_with_zero_revision():
    version = build_msix.read_version()
    parts = version.split(".")

    assert len(parts) == 4
    # 스토어는 revision(4번째 자리)이 0인 패키지만 받는다.
    assert parts[3] == "0"


def test_manifest_carries_partner_center_identity():
    xml = build_msix.build_manifest("0.9.0.0", (".zip",))
    root = ET.fromstring(xml)
    ns = {"m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10"}
    identity = root.find("m:Identity", ns)

    assert identity is not None
    assert identity.get("Name") == "3067F945.PackNine"
    assert identity.get("Publisher") == "CN=6A813624-B2E1-4883-B336-B24D70A7BB09"
    assert identity.get("Version") == "0.9.0.0"
    assert identity.get("ProcessorArchitecture") == "x64"


def test_manifest_is_well_formed_xml_with_all_archive_extensions():
    from packnine.infrastructure.context_menu import _ARCHIVE_EXTENSIONS

    xml = build_msix.build_manifest("0.9.0.0", _ARCHIVE_EXTENSIONS)
    ET.fromstring(xml)  # 깨진 XML이면 여기서 실패한다

    for extension in _ARCHIVE_EXTENSIONS:
        assert f"<uap:FileType>{extension}</uap:FileType>" in xml


def test_manifest_declares_full_trust_capability():
    # PySide6 데스크톱 앱이라 runFullTrust가 없으면 실행 자체가 막힌다.
    xml = build_msix.build_manifest("0.9.0.0", (".zip",))

    assert 'Name="runFullTrust"' in xml
    assert 'EntryPoint="Windows.FullTrustApplication"' in xml


def test_manifest_has_no_legacy_verbs_to_avoid_duplicate_menu():
    """파일 연결에 verb를 두면 "추가 옵션 표시"에 모던 메뉴와 같은 항목이 중복으로 뜬다.

    풀기 동작은 전부 IExplorerCommand(PackNine 묶음)가 담당하므로, 여기에는 더블클릭
    연결만 남긴다.
    """
    xml = build_msix.build_manifest("0.9.0.0", (".zip",))

    assert "SupportedVerbs" not in xml
    assert "알아서 풀기" not in xml
    assert "여기에 풀기" not in xml
    # 더블클릭으로 여는 연결 자체는 남아 있어야 한다.
    assert 'Parameters="open &quot;%1&quot;"' in xml


def test_manifest_registers_shell_extension_com_server():
    # Win11 모던 컨텍스트 메뉴는 COM 핸들러를 통해서만 노출된다.
    xml = build_msix.build_manifest("0.11.0.0", (".zip",))
    ET.fromstring(xml)  # 네임스페이스가 늘었으므로 여전히 유효한 XML인지 확인

    assert build_msix.SHELL_EXTENSION_CLSID in xml
    assert build_msix.SHELL_EXTENSION_DLL in xml
    assert "windows.comServer" in xml


def test_manifest_puts_compress_verb_on_all_files_and_folders():
    xml = build_msix.build_manifest("0.11.0.0", (".zip",))

    assert "windows.fileExplorerContextMenus" in xml
    assert '<desktop5:ItemType Type="*">' in xml
    assert '<desktop5:ItemType Type="Directory">' in xml


def test_clsid_matches_rust_source():
    """매니페스트와 Rust 쪽 CLSID가 어긋나면 메뉴가 조용히 안 뜬다 - 값을 직접 비교한다."""
    import pathlib

    source = (
        pathlib.Path(build_msix.__file__).resolve().parent.parent
        / "shellext"
        / "src"
        / "lib.rs"
    ).read_text(encoding="utf-8")

    compact = build_msix.SHELL_EXTENSION_CLSID.replace("-", "").lower()
    assert compact in source.replace("_", "").lower()
