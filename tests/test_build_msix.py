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


def test_manifest_declares_extract_verbs():
    # 매니페스트로 선언할 수 있는 건 아카이브 확장자에 붙는 동사뿐이다.
    xml = build_msix.build_manifest("0.9.0.0", (".zip",))

    assert "PackNine으로 알아서 풀기" in xml
    assert "PackNine으로 여기에 풀기" in xml
    assert "smart-extract" in xml
