[Document Path]
\conductor\tracks\track_20260714_packnine_fundamentals\review.md

---
트랙ID: track_20260714_packnine_fundamentals
문서경로: \conductor\tracks\track_20260714_packnine_fundamentals\review.md
프로젝트명: PackNine
작업일시: 2026-07-14
작성자: Kent
문서유형: Review
세션목적: 압축/해제 기본기 완성도 점검 및 결함 보강 (v0.2.1 기준)
track_status: draft
parent_track: track_20260708_packnine_archiver
depends_on:
  - track_20260708_packnine_archiver
impact_matrix:
  track_20260708_packnine_archiver: Low
---

## 1. 구현 결과 요약

v0.2.1 전체를 E2E로 재검증(압축→목록→해제 라운드트립, 암호, 손상 파일, 우클릭 시나리오)하여
기본기 결함 4건을 발견하고 모두 수정했다. 테스트 204개 → 215개(전부 통과).

| # | 결함 | 수정 |
|---|------|------|
| 1 | 출력 대상 폴더가 없으면 압축이 `FileNotFoundError`로 실패 (해제는 자동 생성하는데 압축만 비대칭) | `CompressService.compress()`가 소스 검증 후 목적지 부모 폴더를 자동 생성 |
| 2 | **ZIP 암호가 조용히 무시됨** — 표준 zipfile은 암호화 쓰기 미지원인데 password를 받고도 평문 zip 생성 | `pyzipper` 도입, WZ_AES(AES-256)로 실제 암호화. 읽기도 pyzipper로 전환해 타 프로그램의 AES zip 해제 가능 |
| 3 | 암호 오류가 라이브러리 예외 그대로 누출 — 7z 틀린 암호는 `TypeError`, zip은 `RuntimeError` | 도메인 예외 `InvalidPasswordError` 신설, zip/7z/rar 어댑터에서 변환. zip은 쓰기 전 사전 검증으로 all-or-nothing 유지 |
| 4 | GUI/우클릭 메뉴에 **암호 입력 수단이 전혀 없음** — 암호 아카이브를 열/풀 방법 부재 | MainWindow에 비밀번호 프롬프트+재시도(`_execute_with_password_retry`), quick_progress에 `run_extract_with_password_retry` 추가, smart-extract GUI 경로 연결 |

부수 수정: 손상 아카이브를 `CorruptedArchiveError`(도메인 예외)로 통일(zip/7z/tar/rar),
CLI에 두 예외의 한글 안내 메시지 추가, README 갱신, `pyproject.toml`에 `pyzipper` 의존성 추가.

## 2. 설계 대비 차이

- 상위 트랙의 "ZIP은 표준 라이브러리 한계로 암호화 제한" 결정을 뒤집은 것이 아니라,
  의존성 1개(pyzipper) 추가로 한계 자체를 제거했다(사용자 기만적 동작 해소가 우선).
- 계층 경계(도메인 예외만 presentation에 노출) 원칙은 그대로 유지.

## 3. 잘된 점

- 모든 수정을 TDD(RED→GREEN)로 진행, 회귀 테스트 11개 추가.
- 틀린 암호 시 zip도 디스크에 아무것도 쓰기 전에 실패(all-or-nothing 일관성).

## 4. 아쉬운 점

- 개발 venv가 다른 사용자 경로(WH_87)를 참조해 깨져 있었음 → Python 3.12.4로 재생성.
  venv는 머신 간 이식 불가하므로 클론 후 `python -m venv .venv` 재생성이 표준 절차.

## 5. 기술 부채 후보

- py7zr의 틀린 암호 예외가 내부 구현(TypeError) 의존 — py7zr 업그레이드 시 매핑 재검토 필요.
- RAR 암호 테스트는 unrar/bsdtar + 암호 fixture 부재로 미커버(매핑 코드만 존재).

## 6. 후속 작업

- 버전 0.3.0 릴리스(암호 zip 지원은 사용자 가시 기능 추가에 해당).
- 설치 프로그램 재빌드 시 pyzipper 포함 여부 확인(정적 import라 PyInstaller 자동 탐지 예상).
