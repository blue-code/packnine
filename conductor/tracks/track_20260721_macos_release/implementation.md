[Document Path]
\conductor\tracks\track_20260721_macos_release\implementation.md

---
트랙ID: track_20260721_macos_release
문서경로: \conductor\tracks\track_20260721_macos_release\implementation.md
프로젝트명: PackNine
작업일시: 2026-07-21
작성자: Kent
문서유형: Implementation
세션목적: macOS 코어 릴리스 구현 전략 및 빌드 파이프라인 확정
track_status: draft
parent_track: track_20260708_packnine_archiver
depends_on:
  - track_20260721_macos_release (analysis.md)
impact_matrix:
  track_20260708_packnine_archiver: High
  track_20260714_bandizip_parity: Medium
---

## 1. 구현 전략

analysis.md 결론대로 **코어 코드는 수정 없이(add-only), macOS 전용 산출물만 신규 추가**한다.
기존 Windows 산출물(`packnine.spec`, `installer.nsi`, `ci.yml`의 `windows-latest`/
`ubuntu-latest` 매트릭스)은 그대로 두어 회귀 위험을 없앤다.

작업 순서:
1. `scripts/generate_icon.py`에 `.icns` 출력 추가 → `icon.icns` 생성·커밋
2. `packnine.mac.spec` 신규 작성 (`packnine.spec`과 나란히 위치)
3. `.github/workflows/ci.yml`에 `macos-latest` pytest 매트릭스 추가
4. `README.md`에 macOS 섹션 추가(설치·Gatekeeper·RAR 의존성 안내)
5. 로컬 빌드 산출물(또는 CI 아티팩트)로 수동 스모크 테스트

## 2. 아키텍처 (신규/변경 파일)

| 파일 | 종류 | 내용 |
|---|---|---|
| `scripts/generate_icon.py` | 변경 | `canvas.save(icns_path, format="ICNS")` 한 줄 추가. Pillow의 ICNS 인코더는 순수 포맷 변환이라 **macOS가 아닌 현재 Windows 개발 환경에서도 생성 가능**(`iconutil` 등 macOS 전용 도구 불필요) |
| `packnine/presentation/gui/assets/icon.icns` | 신규 자산 | 생성 스크립트 산출물, 저장소에 커밋(기존 `icon.ico`/`icon_256.png`와 동일한 관리 방식) |
| `pyproject.toml` | 변경 | `[tool.setuptools.package-data]`의 `packnine` 항목에 `presentation/gui/assets/*.icns` 패턴 추가 |
| `packnine.mac.spec` | 신규 | PyInstaller macOS 스펙. `Analysis`/`PYZ` 단계는 `packnine.spec`과 동일 구조, 마지막에 `BUNDLE()`로 `PackNine.app` 생성 |
| `.github/workflows/ci.yml` | 변경 | `test` 잡의 `matrix.os`에 `macos-latest` 추가 (기존 `fail-fast: false`가 이미 있어 다른 OS 실패에 영향 없음) |
| `README.md` | 변경 | "macOS 릴리스" 섹션 신규: 다운로드·압축 해제·Gatekeeper 허용 절차, `brew install unrar` 안내 |

## 3. 컴포넌트 설계

### 3.1 `packnine.mac.spec`

```python
# 개념 구조 (packnine.spec과 Analysis/PYZ 단계 동일, 마지막 패키징만 다름)
a = Analysis(['packnine/main.py'], datas=[
    ('packnine/presentation/gui/assets/icon.icns', 'packnine/presentation/gui/assets'),
    ('packnine/presentation/gui/assets/icon_256.png', 'packnine/presentation/gui/assets'),
], ...)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PackNine',
          console=False, icon='packnine/presentation/gui/assets/icon.icns')
coll = COLLECT(exe, a.binaries, a.datas, name='PackNine')
app = BUNDLE(coll, name='PackNine.app',
             icon='packnine/presentation/gui/assets/icon.icns',
             bundle_identifier='com.packnine.app',
             info_plist={
                 'CFBundleShortVersionString': _read_version_from_pyproject(),
                 'NSHighResolutionCapable': True,
                 'LSMinimumSystemVersion': '11.0',
             })
```

- **버전 문자열 이중 관리 방지**: `info_plist['CFBundleShortVersionString']`는 하드코딩하지
  않고 spec 파일 내에서 `pyproject.toml`을 파싱해 `[project].version`을 읽어 사용한다
  (Windows `packnine.spec`은 버전 문자열을 다루지 않으므로 이번에 처음 도입하는 패턴).
- `exclude_binaries=True` + `COLLECT`는 PyInstaller가 `.app` 번들을 만들 때 권장하는
  표준 구성(단일 `EXE`가 아니라 `Contents/MacOS`, `Contents/Resources` 구조로 분리).
- `LSMinimumSystemVersion='11.0'`: GitHub Actions `macos-latest`가 Apple Silicon 전용이고
  Rosetta 없이 arm64 네이티브로만 실행되므로, macOS 11(Big Sur, 최초 Apple Silicon 지원
  버전) 이상으로 명시해 사용자에게 실행 가능 여부를 사전에 안내한다.

### 3.2 CI 매트릭스 확장

기존 `ci.yml`의 `test` 잡 `matrix.os`에 `macos-latest`만 추가한다. macOS 러너에는 Ubuntu처럼
Qt6 시스템 라이브러리 설치 스텝이 필요 없다(Homebrew의 Qt 의존성은 PySide6 wheel에 포함된
프레임워크로 대체됨). `QT_QPA_PLATFORM=offscreen` 환경변수는 Ubuntu 스텝과 동일하게
macOS 스텝에도 적용해 헤드리스 테스트가 GUI 세션 없이 통과하도록 한다.

앱 빌드(`pyinstaller packnine.mac.spec`) 자체는 이번 `ci.yml` 변경 범위에 포함하지 않는다.
빌드·zip 패키징·아티팩트 업로드는 태그 푸시 시 실행되는 별도 릴리스 워크플로 몫이며,
이번 트랙은 "테스트가 macOS에서도 통과한다"는 신호 확보까지만 범위로 한정한다(범위 확대는
7장 개선 포인트로 이월).

## 4. 데이터 흐름 (수동/릴리스 빌드 파이프라인)

1. macOS 머신(로컬 Mac 또는 `macos-latest` 러너)에서 `pip install -e ".[dev]"`
2. `pyinstaller packnine.mac.spec --noconfirm` 실행 → `dist/PackNine.app` 생성
3. `ditto -c -k --sequesterRsrc --keepParent dist/PackNine.app PackNine-macOS-arm64.zip`으로
   압축(표준 `zip` 대신 `ditto` 사용 — macOS 확장 속성/리소스 포크를 보존하는 Apple 표준
   압축 도구, 표준 `zip`은 이를 깨뜨려 앱이 손상되어 보일 수 있음)
4. 산출물을 GitHub Release에 수동 첨부(자동화는 후속 트랙)

## 5. 예외 처리

analysis.md 3.1에서 "CLI `register-context-menu`가 macOS에서 트레이스백을 노출할 수
있다"고 우려했으나, `presentation/cli.py`의 `main()`을 다시 확인한 결과 **이미 안전함을
확인했다**(우려 기각).

- `cli.py:506-521`에 최상위 `try/except RuntimeError`가 존재하며, `command dispatch` 전체
  (`register-context-menu` 포함)를 감싸고 있다.
- `infrastructure/context_menu.py`의 `_require_windows()`가 던지는 `RuntimeError`는 이
  블록에서 잡혀 `오류: 이 기능은 Windows 전용입니다 (winreg 모듈이 필요합니다)` 형태로
  `stderr`에 출력되고 종료 코드 1을 반환한다. 트레이스백 노출 없음.
- GUI 경로(`main_window.py:419-430`)도 analysis.md에서 이미 확인한 대로 `try/except
  Exception`으로 감싸져 오류 다이얼로그로 전환된다.

**결론: `infrastructure/motw.py`, `infrastructure/context_menu.py`,
`presentation/cli.py`, `presentation/gui/main_window.py` 중 이번 트랙에서 코드를 수정할
파일은 없다.** 전부 기존 방어 로직만으로 macOS에서 안전하게 동작한다.

## 6. 테스트 전략

- **자동화**: `ci.yml`의 `macos-latest` 매트릭스에서 기존 pytest 스위트(전체) 그린 확인.
  신규 테스트 추가는 없음(코드 변경이 없으므로 TDD 대상 자체가 없음 — 순수 배포 산출물
  작업).
- **수동 스모크 테스트** (릴리스 전 1회, 로컬 Mac 또는 CI 아티팩트 다운로드):
  1. `PackNine.app` Gatekeeper 경고 우회 후 실행
  2. 파일 드래그 앤 드롭 → zip/7z 압축 → 해제 왕복(round-trip) 확인
  3. 암호 설정 zip/7z 생성 및 올바른/틀린 비밀번호 처리 확인
  4. `brew install unrar` 후 RAR 해제 확인, 미설치 상태에서 안내 메시지 확인
  5. 터미널에서 `PackNine.app/Contents/MacOS/PackNine register-context-menu` 실행 →
     "Windows 전용" 오류 메시지가 트레이스백 없이 출력되는지 확인

## 7. 개선 포인트 (후속 트랙 후보)

- `.dmg` 배포 + Apple Developer 코드 서명/Notarization
- Finder Quick Action(Automator) 기반 우클릭 메뉴 등가 기능 — `track_20260721_macos_release`
  후속으로 `track_..._macos_context_menu` 분리 제안
- `com.apple.quarantine` xattr 기반 MoTW 등가 기능
- Intel(`x86_64`) 빌드 매트릭스 추가(`macos-13` 러너)
- 태그 푸시 시 Windows exe + macOS zip을 함께 GitHub Release에 자동 첨부하는 릴리스
  워크플로 도입
