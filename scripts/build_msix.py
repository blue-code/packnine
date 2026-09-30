"""MSIX(마이크로소프트 스토어) 패키지 빌드 스크립트.

사용법:
    python -m PyInstaller packnine.spec --noconfirm     # 먼저 dist/PackNine.exe 생성
    python scripts/build_msix.py                        # dist/PackNine.msix 생성

스토어 제출용 MSIX는 마이크로소프트가 서명하므로 코드 서명 인증서가 필요 없다. 로컬에서
설치해 확인하려면 자체 서명이 필요한데, 그건 이 스크립트의 일이 아니다(README 참고).

설계 메모:
- 아카이브 확장자 목록을 context_menu 모듈에서 그대로 읽어온다. 매니페스트에 확장자를
  따로 적어두면 포맷을 추가했을 때 한쪽만 갱신되어 조용히 어긋난다.
- 패키지 버전은 pyproject.toml의 버전을 따르되 4자리로 맞춘다. 스토어는 마지막 자리
  (revision)가 0인 패키지만 받는다.
- "압축하기"처럼 모든 파일/폴더에 붙는 동사는 매니페스트로 선언할 수 없다(IExplorerCommand
  COM 핸들러가 필요). 아카이브 확장자에 붙는 동사만 선언한다.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from packnine.infrastructure.context_menu import _ARCHIVE_EXTENSIONS  # noqa: E402

# Partner Center > 제품 ID 페이지의 값과 정확히 일치해야 한다. 하나라도 다르면 업로드가
# "패키지 ID가 일치하지 않습니다"로 거절된다.
IDENTITY_NAME = "3067F945.PackNine"
IDENTITY_PUBLISHER = "CN=6A813624-B2E1-4883-B336-B24D70A7BB09"
PUBLISHER_DISPLAY_NAME = "수카버스"

_DIST_DIR = _PROJECT_ROOT / "dist"
_LAYOUT_DIR = _DIST_DIR / "msix-layout"
_OUTPUT_MSIX = _DIST_DIR / "PackNine.msix"
_SOURCE_ICON = _PROJECT_ROOT / "packnine" / "presentation" / "gui" / "assets" / "icon_256.png"

# 스토어가 요구하는 최소 타일 자산. 값은 (파일명, 한 변 픽셀).
_ASSET_SIZES = (
    ("Square44x44Logo.png", 44),
    ("Square44x44Logo.targetsize-24_altform-unplated.png", 24),
    ("Square150x150Logo.png", 150),
    ("StoreLogo.png", 50),
    ("Wide310x150Logo.png", 0),  # 0은 가로형(310x150)을 뜻한다 - 아래에서 따로 처리한다.
)


def read_version() -> str:
    """pyproject.toml의 버전을 MSIX용 4자리 버전으로 바꾼다(0.9.0 -> 0.9.0.0)."""
    text = (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise RuntimeError("pyproject.toml에서 version을 찾지 못했습니다")
    parts = match.group(1).split(".")
    while len(parts) < 4:
        parts.append("0")
    # 스토어는 revision(4번째 자리)이 0인 패키지만 받는다.
    parts[3] = "0"
    return ".".join(parts[:4])


def build_manifest(version: str, extensions: tuple[str, ...]) -> str:
    """AppxManifest.xml 내용을 만든다(파일로 쓰지 않으므로 테스트에서 그대로 검증 가능)."""
    file_types = "\n".join(
        f"                  <uap:FileType>{ext}</uap:FileType>" for ext in extensions
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap2="http://schemas.microsoft.com/appx/manifest/uap/windows10/2"
  xmlns:uap3="http://schemas.microsoft.com/appx/manifest/uap/windows10/3"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap2 uap3 rescap">

  <Identity
    Name="{IDENTITY_NAME}"
    Publisher="{IDENTITY_PUBLISHER}"
    Version="{version}"
    ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>PackNine</DisplayName>
    <PublisherDisplayName>{PUBLISHER_DISPLAY_NAME}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" />
  </Dependencies>

  <Resources>
    <Resource Language="ko-KR" />
  </Resources>

  <Applications>
    <Application Id="PackNine" Executable="PackNine.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="PackNine"
        Description="ZIP/7Z/TAR/RAR을 지원하는 오픈소스 압축 프로그램"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png"
        BackgroundColor="transparent">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <uap3:Extension Category="windows.fileTypeAssociation">
          <uap3:FileTypeAssociation Name="packninearchive" Parameters="open &quot;%1&quot;">
            <uap:DisplayName>PackNine 압축 파일</uap:DisplayName>
            <uap:Logo>Assets\\StoreLogo.png</uap:Logo>
            <uap2:SupportedVerbs>
              <uap3:Verb Id="extractsmart" Parameters="smart-extract &quot;%1&quot;">PackNine으로 알아서 풀기</uap3:Verb>
              <uap3:Verb Id="extracthere" Parameters="smart-extract --here &quot;%1&quot;">PackNine으로 여기에 풀기</uap3:Verb>
            </uap2:SupportedVerbs>
            <uap:SupportedFileTypes>
{file_types}
            </uap:SupportedFileTypes>
          </uap3:FileTypeAssociation>
        </uap3:Extension>
      </Extensions>
    </Application>
  </Applications>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def _generate_assets(assets_dir: pathlib.Path) -> None:
    from PIL import Image

    assets_dir.mkdir(parents=True, exist_ok=True)
    source = Image.open(_SOURCE_ICON).convert("RGBA")
    for name, size in _ASSET_SIZES:
        if size == 0:
            # 가로형 타일: 310x150 투명 캔버스 가운데에 아이콘을 얹는다.
            tile = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
            icon = source.resize((150, 150), Image.LANCZOS)
            tile.paste(icon, (80, 0), icon)
            tile.save(assets_dir / name)
            continue
        source.resize((size, size), Image.LANCZOS).save(assets_dir / name)


def _find_makeappx() -> pathlib.Path:
    bin_root = pathlib.Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    candidates = sorted(bin_root.glob("*/x64/makeappx.exe"), reverse=True)
    if not candidates:
        raise RuntimeError(
            "makeappx.exe를 찾지 못했습니다. Windows SDK가 설치되어 있어야 합니다."
        )
    return candidates[0]


def main() -> int:
    exe_path = _DIST_DIR / "PackNine.exe"
    if not exe_path.exists():
        print(f"먼저 실행 파일을 빌드하세요: {exe_path}", file=sys.stderr)
        return 1

    version = read_version()
    shutil.rmtree(_LAYOUT_DIR, ignore_errors=True)
    _LAYOUT_DIR.mkdir(parents=True)

    shutil.copy2(exe_path, _LAYOUT_DIR / "PackNine.exe")
    _generate_assets(_LAYOUT_DIR / "Assets")
    (_LAYOUT_DIR / "AppxManifest.xml").write_text(
        build_manifest(version, _ARCHIVE_EXTENSIONS), encoding="utf-8"
    )

    _OUTPUT_MSIX.unlink(missing_ok=True)
    result = subprocess.run(  # noqa: S603
        [str(_find_makeappx()), "pack", "/d", str(_LAYOUT_DIR), "/p", str(_OUTPUT_MSIX), "/o"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    size_mb = _OUTPUT_MSIX.stat().st_size / 1024 / 1024
    print(f"생성 완료: {_OUTPUT_MSIX} ({size_mb:.1f}MB, 버전 {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
