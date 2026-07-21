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

1. ~~이번 변경을 커밋·푸시해 `macos-latest` CI 매트릭스의 실제 통과 여부 확인~~ → 완료
   (7장 참고). `pytest` 매트릭스는 실제로 macOS 러너에서 green 확인됨.
2. ~~macOS 머신(로컬 Mac 또는 CI) 확보 후 `pyinstaller packnine.mac.spec --noconfirm` 실행~~
   → 7장에서 `build-macos` CI 잡으로 자동화. CI 실행 결과로 최종 확인 예정.
3. 빌드·스모크 테스트가 CI에서 그린으로 확인되면 GitHub Release에
   `PackNine-macOS-arm64.zip` 첨부(현재는 CI 아티팩트로만 보관, 릴리스 첨부는 수동),
   plan.md Approval Gate 재검토 후 `track_status: approved` 전환
4. 후속 트랙 후보 착수: Finder Quick Action 우클릭 메뉴, `.dmg`/코드 서명, Intel 빌드,
   태그 푸시 시 GitHub Release 자동 첨부 워크플로

## 7. 후속 세션 업데이트 — 빌드 자동화 (2026-07-21, 같은 날 후속 작업)

당초 implementation.md 3.2에서는 "앱 빌드는 이번 트랙 `ci.yml` 범위에 포함하지 않는다"고
정했으나, 사용자가 실제 빌드 검증까지 자동화하기를 원해 범위를 확장했다.

- `.github/workflows/ci.yml`에 `build-macos` 잡 신규 추가 (`macos-latest`, `test` 잡과
  독립적으로 병렬 실행):
  1. `pip install -e "." pyinstaller`
  2. `pyinstaller packnine.mac.spec --noconfirm` → `dist/PackNine.app` 생성
  3. **스모크 테스트**: 빌드된 바이너리(`Contents/MacOS/PackNine`)로 `--help` 실행,
     실제로 압축(`compress`) → 목록 조회(`list`) → 해제(`extract`) 왕복까지 수행해
     원본과 diff 비교(GUI 없이 CLI 경로만 검증 — Qt를 띄우지 않아 헤드리스 러너에서도
     안정적으로 동작)
  4. `ditto -c -k --sequesterRsrc --keepParent`로 `PackNine-macOS-arm64.zip` 생성
  5. `actions/upload-artifact@v4`로 14일 보관 아티팩트 업로드
- 이로써 "PyInstaller 빌드가 실제로 성공하는가"와 "빌드된 바이너리에 압축 라이브러리가
  정상적으로 번들링되었는가(숨은 import 누락 등)"를 매 push마다 자동으로 검증한다.
- 다만 이 스모크 테스트는 CLI 경로만 검증하며 **GUI(PySide6 윈도우)가 실제로 뜨는지는
  검증하지 않는다**(헤드리스 CI 러너에서 GUI 창 렌더링까지 확인하려면 별도의
  `QT_QPA_PLATFORM=offscreen` 기반 GUI 스모크 테스트가 필요 — 후속 백로그로 남긴다).
- 코드 서명이 없으므로 CI에서 만든 아티팩트를 실제 사용자 Mac에서 실행하려면 여전히
  Gatekeeper "확인 없이 열기" 절차가 필요하다(README 안내 유지).
