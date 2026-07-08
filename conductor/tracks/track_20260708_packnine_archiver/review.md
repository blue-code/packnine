---
트랙ID: track_20260708_packnine_archiver
문서경로: \conductor\tracks\track_20260708_packnine_archiver\review.md
프로젝트명: PackNine
작업일시: 2026-07-08
작성자: Kent
문서유형: Review
세션목적: v0.1.0 구현 결과 회고 및 후속 작업 정리
track_status: approved
parent_track: (없음, 최초 트랙)
depends_on:
  - track_20260708_packnine_archiver (implementation.md)
impact_matrix: {}
---

## 1. 구현 결과 요약

plan.md의 Phase 1 범위를 전량 구현하고 v0.1.0으로 릴리즈 완료.

- 저장소: https://github.com/blue-code/packnine
- 릴리즈: https://github.com/blue-code/packnine/releases/tag/v0.1.0 (PackNine.exe 첨부)
- CI: Windows/Ubuntu × Python 3.11/3.12 매트릭스 + pip-audit, 전부 그린
- 테스트: 115 passed, 1 skipped(RAR round-trip — 환경에 unrar/bsdtar 미설치로 조건부 스킵)
- 커버리지: domain 100%, application 100%, infrastructure 평균 약 82%(RAR 어댑터는
  스킵된 테스트 영향으로 40%), 전체 77%

## 2. 설계 대비 차이

- **py7zr 버전**: analysis.md 작성 시점에는 버전을 명시하지 않았으나, 구현 완료 후
  `pip-audit`에서 0.22.0에 CVE-2026-23879/55206/55195가 발견되어 1.1.3으로 상향
  (`pyproject.toml` 제약을 `>=0.21,<1` → `>=1.1.3,<2`로 변경). API 호환성 문제는 없었음.
- **ZIP 비밀번호**: 표준 `zipfile`은 쓰기 시 AES 암호화를 지원하지 않아, 계획대로 7Z에서만
  진짜 AES-256을 제공하고 ZIP은 최소 구현(제한적)으로 처리함(설계 의도대로).
- **GUI 배포 형태**: PyInstaller를 `console=False`(windowed)로 빌드해 exe를 더블클릭하면
  콘솔 없이 GUI만 뜨도록 함. CLI가 필요한 사용자는 `pip install` 후 `packnine` 커맨드를
  사용하도록 안내(implementation.md에는 명시되지 않았던 배포 방식 결정).

## 3. 잘된 점

- SecurityPolicy를 도메인 계층의 독립 정책 객체로 분리한 덕분에, 모든 포맷 어댑터가
  동일한 방어 로직을 재사용했고, 인프라 계층 구현 중 별도 보안 버그 없이 통과됨.
- CI를 조기에 붙여 실제로 버그를 잡음: Ubuntu 러너에서 `..\\..\\evil.exe` 형태의
  백슬래시 Zip Slip 패턴이 통과되는 것을 발견. `pathlib`가 POSIX에서 `\`를 구분자로
  취급하지 않아 실행 OS에 따라 방어 여부가 갈리는 실제 보안 결함이었고, 엔트리명을
  `/`로 정규화한 뒤 세그먼트 단위로 `..`를 직접 검사하는 1차 방어를 추가해 해결함.
  → 크로스플랫폼 CI가 아니었다면 Windows 전용 개발/테스트 환경에서는 절대 드러나지
  않았을 결함이라는 점이 특히 값진 교훈.
- 계층 경계(도메인이 인프라를 모름, 표현 계층이 인프라를 모름)를 여러 작업자가 나누어
  구현했음에도 끝까지 위반 없이 유지됨.

## 4. 아쉬운 점

- 전체 테스트 커버리지가 목표(80%)에 약간 못 미치는 77%. GUI(main_window.py 49%,
  compress_dialog.py 74%)와 RAR 어댑터(40%, 환경에 unrar 미설치)가 끌어내림.
  도메인/애플리케이션은 100%로 목표를 초과 달성했으므로 보안·비즈니스 로직 관점의
  위험은 낮다고 판단.
- 빌드된 exe가 코드 서명되지 않아 SmartScreen 경고가 발생함(릴리즈 노트에 안내만 함).
- 탐색기 우클릭 등록은 간이 레지스트리 방식으로, 정식 셸 확장만큼의 아이콘/미리보기
  통합은 제공하지 않음(계획대로의 의도된 축소 범위).

## 5. 기술 부채 후보

- ZIP 쓰기 시 진짜 AES-256을 지원하려면 `pyzipper`로 교체하거나 별도 어댑터 추가 검토 필요.
- GUI 스모크 테스트를 넘어서는 상호작용 테스트(pytest-qt의 실제 클릭 시뮬레이션) 보강.
- 코드 서명 인증서 도입 검토(비용 발생, 사용자 확인 필요).

## 6. 후속 작업

- `.github/ISSUE_TEMPLATE/backlog_phase2.md` 기준으로 Phase 2 항목을 실제 GitHub Issue로
  등록(미리보기, 알집 변환, 정식 셸 확장 등).
- RAR 해제 환경 의존성(unrar/bsdtar) 안내를 README 상단으로 좀 더 눈에 띄게 이동 검토.
