[Document Path]
\conductor\tracks\track_20260721_macos_release\review.md

---
트랙ID: track_20260721_macos_release
문서경로: \conductor\tracks\track_20260721_macos_release\review.md
프로젝트명: PackNine
작업일시: 2026-07-21
작성자: Kent
문서유형: Review
세션목적: macOS 코어 릴리스 1단계 구현 결과 정리
track_status: draft
parent_track: track_20260708_packnine_archiver
depends_on:
  - track_20260721_macos_release (implementation.md)
impact_matrix:
  track_20260708_packnine_archiver: High
  track_20260714_bandizip_parity: Medium
---

## 1. 구현 결과 요약

implementation.md의 계획대로 코어 코드 수정 없이 macOS 전용 산출물만 추가했다.

| # | 산출물 | 내용 |
|---|--------|------|
| 1 | `scripts/generate_icon.py` | `.icns` 출력 추가, 실행해 `icon.icns`(161KB) 생성·저장 |
| 2 | `pyproject.toml` | `package-data`에 `presentation/gui/assets/*.icns` 패턴 추가 |
| 3 | `packnine.mac.spec` | 신규 작성. `Analysis`/`PYZ`는 `packnine.spec`과 동일, `BUNDLE()`로 `PackNine.app` 패키징, 버전은 `pyproject.toml`에서 파싱 |
| 4 | `.github/workflows/ci.yml` | `test` 잡 `matrix.os`에 `macos-latest` 추가, `QT_QPA_PLATFORM=offscreen`으로 헤드리스 테스트 스텝 추가 |
| 5 | `README.md` | "macOS (베타, Apple Silicon 전용)" 섹션 추가: 다운로드·Gatekeeper 허용·RAR(`brew install unrar`) 안내 |
| 6 | 회귀 확인 | 로컬(Windows) `pytest -q` 전체 재실행 — **257 passed, 1 skipped**, 기존과 동일(회귀 없음) |

## 2. 설계 대비 차이

- implementation.md 설계와 실제 구현은 동일하다. 다만 **`packnine.mac.spec`은 이번 세션에서
  실제 빌드까지 검증하지 못했다** — PyInstaller의 `BUNDLE()`은 macOS에서 실행할 때만
  `.app`을 만들며, 현재 개발 환경이 Windows라 로컬에서 빌드 자체가 불가능하다(analysis.md
  2장에서 이미 예견한 제약). 스펙 파일 문법과 구조는 PyInstaller 공식 문서 패턴을 따랐으나,
  **macOS 머신 또는 `macos-latest` CI에서의 실제 빌드 성공 여부는 아직 미검증**이다.
- `ci.yml` 변경은 implementation.md에서 정한 범위(pytest 매트릭스 확장까지)를 그대로
  지켰고, 앱 빌드·아티팩트 업로드는 계획대로 포함하지 않았다.

## 3. 잘된 점

- Pillow의 ICNS 인코더가 macOS 전용 도구 없이 동작함을 실제로 확인해, Windows 개발
  환경에서도 `icon.icns`를 안전하게 생성·커밋할 수 있었다(빌드 파이프라인에 macOS 의존성을
  추가하지 않음).
- analysis.md에서 제기했던 "CLI `register-context-menu` 트레이스백 노출" 우려를
  implementation.md 단계에서 코드(`cli.py:506-521`)를 재확인해 기각함으로써, 불필요한
  방어 코드를 추가하지 않고 실제로 필요한 변경(문서·빌드 산출물)에만 집중했다.
- 회귀 테스트(`pytest -q`)가 전부 통과해, 이번 트랙의 "코드 로직은 건드리지 않는다"는
  add-only 전략이 실제로 지켜졌음을 확인했다.

## 4. 아쉬운 점

- 이번 세션은 Windows 로컬 환경에서 진행되어 **실제 macOS 빌드·실행·스모크 테스트를 이
  자리에서 수행하지 못했다**. `packnine.mac.spec`이 실제로 `.app`을 만들어내는지,
  만들어진 앱이 Gatekeeper 경고 이후 정상 실행되는지는 여전히 미검증 상태다.
- `ci.yml`에 추가한 `macos-latest` 매트릭스가 실제로 그린인지도 이 세션에서는 확인할 수
  없다(다음 push/PR에서 GitHub Actions 실행 결과로 확인 필요).

## 5. 기술 부채 후보

- `packnine.mac.spec` 실빌드 미검증 — 다음 macOS 접근 가능 시점에 최우선 검증 필요.
- `.dmg` 배포, 코드 서명/Notarization, Finder Quick Action, `com.apple.quarantine` 기반
  MoTW 등가 기능은 계획대로 전부 후속 트랙 백로그로 유지.

## 6. 후속 작업

1. 이번 변경을 커밋·푸시해 `macos-latest` CI 매트릭스의 실제 통과 여부 확인
2. macOS 머신(로컬 Mac 또는 CI) 확보 후 `pyinstaller packnine.mac.spec --noconfirm` 실행,
   `dist/PackNine.app` 생성 및 implementation.md 6장의 수동 스모크 테스트 절차 수행
3. 스모크 테스트까지 통과하면 GitHub Release에 `PackNine-macOS-arm64.zip` 첨부, plan.md
   Approval Gate 재검토 후 `track_status: approved` 전환
4. 후속 트랙 후보 착수: Finder Quick Action 우클릭 메뉴, `.dmg`/코드 서명, Intel 빌드
