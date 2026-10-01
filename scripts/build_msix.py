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

# 탐색기 컨텍스트 메뉴 핸들러(shellext)의 CLSID. Rust 쪽 lib.rs의 값과 반드시 같아야 한다.
SHELL_EXTENSION_CLSID = "D1C9C67D-CF0A-494E-9E84-4FEDB96D2272"
SHELL_EXTENSION_DLL = "packnine_shellext.dll"
# 탐색기 미리보기 창 핸들러의 CLSID. Rust 쪽 preview.rs의 값과 반드시 같아야 한다.
PREVIEW_HANDLER_CLSID = "D400F75F-2A57-4259-B4FC-9AF59272AFE8"

_DIST_DIR = _PROJECT_ROOT / "dist"
_LAYOUT_DIR = _DIST_DIR / "msix-layout"
_OUTPUT_MSIX = _DIST_DIR / "PackNine.msix"
_SOURCE_ICON = _PROJECT_ROOT / "packnine" / "presentation" / "gui" / "assets" / "icon_256.png"
_SHELLEXT_DLL_PATH = _PROJECT_ROOT / "shellext" / "target" / "release" / SHELL_EXTENSION_DLL

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
  xmlns:uap3="http://schemas.microsoft.com/appx/manifest/uap/windows10/3"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  xmlns:com="http://schemas.microsoft.com/appx/manifest/com/windows10"
  xmlns:desktop4="http://schemas.microsoft.com/appx/manifest/desktop/windows10/4"
  xmlns:desktop5="http://schemas.microsoft.com/appx/manifest/desktop/windows10/5"
  xmlns:desktop2="http://schemas.microsoft.com/appx/manifest/desktop/windows10/2"
  IgnorableNamespaces="uap uap3 rescap com desktop2 desktop4 desktop5">

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
        <!-- Windows 11 기본(모던) 우클릭 메뉴. 레지스트리 verb는 "추가 옵션 표시" 안쪽으로
             밀려나므로, 기본 메뉴에 올리려면 IExplorerCommand COM 핸들러가 필요하다. -->
        <com:Extension Category="windows.comServer">
          <com:ComServer>
            <com:SurrogateServer DisplayName="PackNine Shell Extension">
              <com:Class Id="{SHELL_EXTENSION_CLSID}" Path="{SHELL_EXTENSION_DLL}" ThreadingModel="STA" />
              <com:Class Id="{PREVIEW_HANDLER_CLSID}" Path="{SHELL_EXTENSION_DLL}" ThreadingModel="STA" />
            </com:SurrogateServer>
          </com:ComServer>
        </com:Extension>
        <desktop4:Extension Category="windows.fileExplorerContextMenus">
          <desktop4:FileExplorerContextMenus>
            <!-- 모든 파일과 폴더에 "압축하기"를 올린다. 레지스트리 방식으로는 스토어
                 설치본에서 불가능했던 항목이다. -->
            <desktop5:ItemType Type="*">
              <desktop5:Verb Id="PackNineCompress" Clsid="{SHELL_EXTENSION_CLSID}" />
            </desktop5:ItemType>
            <desktop5:ItemType Type="Directory">
              <desktop5:Verb Id="PackNineCompress" Clsid="{SHELL_EXTENSION_CLSID}" />
            </desktop5:ItemType>
          </desktop4:FileExplorerContextMenus>
        </desktop4:Extension>
        <uap3:Extension Category="windows.fileTypeAssociation">
          <!-- 파일 연결(더블클릭)만 담당한다. 풀기 동작은 모던 메뉴의 PackNine 묶음에
               있으므로 여기에 verb를 두면 "추가 옵션 표시"에 같은 항목이 중복으로 뜬다. -->
          <uap3:FileTypeAssociation Name="packninearchive" Parameters="open &quot;%1&quot;">
            <uap:DisplayName>PackNine 압축 파일</uap:DisplayName>
            <uap:Logo>Assets\\StoreLogo.png</uap:Logo>
            <uap:SupportedFileTypes>
{file_types}
            </uap:SupportedFileTypes>
            <!-- 탐색기 미리보기 창에 압축 파일 내용을 보여준다(zip만 목록 표시). -->
            <desktop2:DesktopPreviewHandler Clsid="{PREVIEW_HANDLER_CLSID}" />
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


def _clean_alpha(image):
    """거의 투명한 픽셀의 색을 지운다(작업 표시줄 타일 모서리에 색이 비치는 것 방지).

    둥근 모서리를 작게 줄이면 알파가 한 자리 수인 색 픽셀이 남아, 렌더링 경로에 따라
    네 귀퉁이에 점이 찍힌 것처럼 보인다. generate_icon.py와 같은 처리를 한다.
    """
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] < 16:
                pixels[x, y] = (0, 0, 0, 0)
    return image


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
        _clean_alpha(source.resize((size, size), Image.LANCZOS)).save(assets_dir / name)


def _find_makeappx() -> pathlib.Path:
    bin_root = pathlib.Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    candidates = sorted(bin_root.glob("*/x64/makeappx.exe"), reverse=True)
    if not candidates:
        raise RuntimeError(
            "makeappx.exe를 찾지 못했습니다. Windows SDK가 설치되어 있어야 합니다."
        )
    return candidates[0]


def main() -> int:
    # 폴더(onedir) 빌드를 쓴다. 단일 파일은 실행마다 54MB를 임시 폴더에 풀어내 기동에만
    # 2초 넘게 걸리는데, 우클릭 "알아서 풀기"처럼 짧은 작업에서는 그 시간이 체감 속도를
    # 지배한다(실측 2081ms -> 260ms).
    onedir_path = _DIST_DIR / "PackNine"
    exe_path = onedir_path / "PackNine.exe"
    if not exe_path.exists():
        print(
            f"먼저 폴더 모드로 빌드하세요: {exe_path}\n"
            "  python -m PyInstaller packnine.onedir.spec --noconfirm",
            file=sys.stderr,
        )
        return 1

    version = read_version()
    shutil.rmtree(_LAYOUT_DIR, ignore_errors=True)
    _LAYOUT_DIR.mkdir(parents=True)

    # 폴더 전체를 패키지 루트에 펼쳐 담는다(exe와 _internal 등).
    shutil.copytree(onedir_path, _LAYOUT_DIR, dirs_exist_ok=True)
    if not _SHELLEXT_DLL_PATH.exists():
        print(
            f"셸 확장 DLL이 없습니다: {_SHELLEXT_DLL_PATH}\n"
            "shellext 폴더에서 빌드하세요: "
            "cargo +stable-x86_64-pc-windows-gnu build --release",
            file=sys.stderr,
        )
        return 1
    shutil.copy2(_SHELLEXT_DLL_PATH, _LAYOUT_DIR / SHELL_EXTENSION_DLL)
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
