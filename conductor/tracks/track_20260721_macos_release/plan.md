[Document Path]
\conductor\tracks\track_20260721_macos_release\plan.md

---
트랙ID: track_20260721_macos_release
문서경로: \conductor\tracks\track_20260721_macos_release\plan.md
프로젝트명: PackNine
작업일시: 2026-07-21
작성자: Kent
문서유형: Plan
세션목적: PackNine macOS 정식 릴리스 가능성 검토 및 1단계(코어 앱) 배포 계획 수립
track_status: approved
parent_track: track_20260708_packnine_archiver
depends_on:
  - track_20260708_packnine_archiver
  - track_20260714_bandizip_parity
impact_matrix:
  track_20260708_packnine_archiver: High
  track_20260714_packnine_fundamentals: Low
  track_20260714_bandizip_parity: Medium
---

## 1. 기획 배경

최초 트랙(`track_20260708_packnine_archiver`)에서는 "macOS/Linux GUI 정식 지원"을 Phase 2+
Out of Scope로 명시하고 Windows 단일 플랫폼으로 개발을 시작했다. 이후 CI(`ci.yml`)가
`ubuntu-latest`에서도 pytest를 돌리도록 이미 확장되어 있어, 코어 로직(도메인/애플리케이션/
포맷 어댑터)이 사실상 크로스플랫폼으로 검증되고 있다는 근거가 쌓였다. 사용자가 macOS
릴리스 가능 여부를 문의함에 따라, 기존 Out of Scope 결정을 재검토하고 실제 배포 경로를
수립한다.

## 2. 문제 정의

코드베이스를 실사한 결과, macOS 이식을 가로막는 요소는 전부 "Windows 전용 API에 직접
의존하는 일부 인프라 모듈"에 국한되어 있고, 코어 압축/해제 로직은 그대로 재사용 가능하다.

| 영역 | 현재 상태 | macOS 이식 가능 여부 |
|------|-----------|----------------------|
| GUI/CLI (PySide6, argparse) | 크로스플랫폼 라이브러리 | 그대로 사용 가능 |
| 압축/해제 엔진 (py7zr, pyzipper, rarfile) | 크로스플랫폼 라이브러리 | 그대로 사용 가능 |
| 도메인 계층 (`domain/*`) | 순수 Python, 외부 의존성 없음 | 그대로 사용 가능 |
| `infrastructure/context_menu.py` | `winreg`(HKCU) 기반 탐색기 우클릭 메뉴 | Windows 전용, macOS는 Finder Quick Action/Automator로 별도 구현 필요 |
| `infrastructure/motw.py` | NTFS ADS(`Zone.Identifier`) 기반 MoTW 전파 (`sys.platform != "win32"`면 즉시 no-op) | Windows 전용, macOS는 `com.apple.quarantine` xattr로 별도 구현 필요 |
| `installer.nsi` | NSIS(Windows 전용 설치 프로그램) | macOS는 `.dmg`/`.pkg`로 별도 제작 필요 |
| `packnine.spec` | PyInstaller, Windows용 `.ico` 아이콘 지정 | macOS `.app` 빌드는 별도 spec + `.icns` 필요, macOS 머신에서 직접 빌드해야 함(크로스 컴파일 불가) |
| RAR 해제 (`unrar`/`bsdtar`) | 시스템 바이너리 의존 | macOS는 Homebrew(`brew install unrar` 또는 `libarchive`)로 대체 확보 필요 |

## 3. 목표

1. PackNine 코어 기능(압축/해제/GUI/CLI)을 macOS `.app`으로 빌드해 GitHub Release에 배포한다.
2. Windows 전용 편의 기능(탐색기 우클릭 메뉴, MoTW 전파)은 macOS 등가 기능으로 별도 트랙에서
   재구현하되, 이번 트랙에서는 "부재 시에도 코어 기능은 정상 동작"함을 보장한다.
3. CI에 macOS 빌드/테스트를 추가해 회귀를 상시 검증한다.

## 4. 범위 (In / Out)

### In Scope — 이번 트랙 (macOS 코어 릴리스)
- macOS(Apple Silicon, `arm64`) 대상 PyInstaller 빌드 스펙(`packnine.mac.spec`) 신규 작성
  (`.icns` 아이콘, `BUNDLE()`로 `.app` 패키징)
- GitHub Actions CI에 `macos-latest` 매트릭스 추가(pytest 그린 확인)
- `context_menu_service.py`/`motw.py` 호출부에 플랫폼 가드 확인 및 macOS에서 예외 없이
  "미지원 기능"으로 조용히 스킵되는지 검증(신규 기능 추가 없음, 회귀 방지만)
- RAR 해제 의존성(`unrar`/`bsdtar`) macOS 설치 가이드를 README에 추가
- `.dmg` 또는 zip 아카이브 형태의 최소 배포물 제작, GitHub Release 첨부
- 코드 서명/공증(Notarization) 여부 조사 및 리스크로 문서화(실제 서명은 Out)

### Out of Scope — 후속 트랙 후보
- Finder Quick Action/Automator 기반 우클릭 메뉴 등가 기능 (`track_20260721_macos_context_menu`
  후보로 별도 트랙 분리)
- `com.apple.quarantine` xattr 기반 MoTW 등가 기능
- Apple Developer 인증서 코드 서명 및 Notarization 정식 적용(비용/계정 필요)
- Intel(`x86_64`) macOS 빌드(우선 Apple Silicon만 대응, 필요 시 후속 트랙)
- Linux 정식 지원(이번 트랙 범위 아님, CI 테스트만 기존대로 유지)

## 5. 사용자 시나리오

1. macOS 사용자가 GitHub Release에서 PackNine `.app`(또는 `.dmg`)을 내려받아 실행한다.
2. 파일을 드래그 앤 드롭해 압축하거나, 기존 `.zip`/`.7z`/`.tar.*`/`.rar`를 열어 해제한다.
3. 우클릭 메뉴나 MoTW 전파 없이도 GUI/CLI 핵심 기능은 Windows와 동일하게 동작한다.
4. RAR 해제 시 `unrar`/`bsdtar`가 없으면 설치 안내 메시지가 표시된다.

## 6. 성공 기준

- [x] `macos-latest` CI 매트릭스에서 pytest 전체 통과
- [x] macOS에서 PyInstaller 빌드한 `.app`이 실행되어 압축/해제 왕복(round-trip) 검증 완료
      (사람이 손으로 한 수동 검증이 아니라 CI `build-macos` 잡의 자동 스모크 테스트로
      대체 — 매 push마다 실제 macOS 러너에서 재검증됨. GUI 창 렌더링 자체는 여전히
      미검증, review.md 7장 참고)
- [x] 우클릭 메뉴/MoTW 미지원 상태에서도 크래시 없이 정상 동작(예외 미노출) 확인
      (CI 스모크 테스트에서 `register-context-menu` 실행 시 트레이스백 없이 "Windows
      전용" 오류 메시지 + 종료코드 1로 안전 종료됨을 자동 확인)
- [x] GitHub Release에 macOS 배포물(`.dmg` 또는 zip) 첨부
      (v0.6.0 릴리스에 `PackNine-macOS-arm64.zip` 첨부, 릴리스 노트에 macOS 베타 안내 추가)
- [x] README에 macOS 설치/실행/RAR 의존성 안내 추가

## 7. 리스크 및 가정

- **가정**: PyInstaller는 크로스 컴파일을 지원하지 않으므로, 실제 macOS 앱 빌드에는
  macOS 머신(로컬 Mac 또는 GitHub Actions `macos-latest` 러너)이 필요하다.
- **리스크**: 코드 서명 없는 `.app`은 Gatekeeper에 의해 "확인되지 않은 개발자" 경고가 뜬다
  → README에 "시스템 설정 > 개인정보 보호 및 보안"에서 실행 허용하는 안내 문구 추가로 우선
  대응하고, 정식 서명/Notarization은 후속 트랙에서 비용·계정 확보 후 진행한다.
- **리스크**: RAR 해제용 `unrar`/`bsdtar`가 macOS 기본 설치되어 있지 않음 → Homebrew 설치
  안내로 대응(Windows와 동일한 패턴).
- **리스크**: `domain/security_policy.py`의 심볼릭 링크/절대경로 거부 로직이 POSIX 권한
  모델(실행 비트, 케이스 센시티브 파일시스템 차이 등)에서 Windows와 다르게 동작할 가능성
  → 이번 트랙 테스트 단계에서 회귀 여부 별도 확인.
- **리스크**: "정식 Windows Shell Extension"처럼 macOS도 "정식 Finder 확장(Finder Sync
  Extension)"까지 가려면 별도 Xcode/Swift 작업이 필요해 범위가 커짐 → 이번 트랙은 Automator
  Quick Action 수준까지만 후속 트랙 범위로 잡고, Finder Sync Extension은 백로그로 남긴다.

## Approval Gate 체크리스트

```yaml
approval_checklist:
  - [x] plan.md 작성 완료
  - [x] analysis.md 작성 완료
  - [x] implementation.md 방향 확정
  - [x] 주요 리스크 문서화
  - [x] 상위 track 정합성 확인 (track_20260708_packnine_archiver의 Out of Scope 결정을
        의도적으로 재검토 - 4. 범위 참고)
  - [x] 영향도 매트릭스 작성
```

문서 체크리스트는 모두 충족했으나, `track_status: draft`는 실제 구현(아이콘 생성,
`packnine.mac.spec` 작성, `ci.yml`/`README.md` 반영, 빌드 스모크 테스트)이 완료될
때까지 유지한다. implementation.md 기준으로 실제 코드/설정 변경을 진행한 뒤
review.md로 결과를 정리하고, 그때 `approved` 전환을 재검토한다.
