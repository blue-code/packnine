[Document Path]
\conductor\tracks\track_20260714_bandizip_parity\review.md

---
트랙ID: track_20260714_bandizip_parity
문서경로: \conductor\tracks\track_20260714_bandizip_parity\review.md
프로젝트명: PackNine
작업일시: 2026-07-14
작성자: Kent
문서유형: Review
세션목적: 반디집 기본 기능 패리티 1차 구현 결과 정리
track_status: draft
parent_track: track_20260714_packnine_fundamentals
depends_on:
  - track_20260714_bandizip_parity (plan.md)
impact_matrix:
  track_20260708_packnine_archiver: Medium
---

## 1. 구현 결과 요약

plan.md의 In 범위 6개 기능을 전부 TDD로 구현했다. 테스트 215개 → 246개(전부 통과).

| 기능 | 구현 위치 | 비고 |
|------|-----------|------|
| ZIP 한글 파일명 자동 감지 | `zip_adapter._decode_legacy_filename` | UTF-8 플래그 없는 엔트리를 cp437 왕복 후 UTF-8 → cp949 순 재판별. 표시명↔내부명 매핑으로 해제 정확성 유지 |
| 단일 파일 .gz/.bz2/.xz 해제 | `singlefile_adapter.py` (신규) | 원본 크기를 알 수 없어 스트리밍 중 압축비 상한(100x, 10MB 하한)으로 폭탄 방어. 쓰기는 미지원(해제 전용) |
| 내부 파일 더블클릭 열기 | `main_window._open_entry_with_default_app` | 임시 해제 후 QDesktopServices로 기본 프로그램 실행. 임시 폴더는 창 닫을 때 일괄 정리 |
| 우클릭 메뉴 확장 | `context_menu.py`, `cli.py --each` | "PackNine으로 열기"(아카이브), "각각 압축하기"(전체 파일). .gz/.bz2/.xz도 메뉴/파일 연결 대상에 포함 |
| 아카이브 편집 | `update_service.py` (신규) + GUI 툴바 | 재작성 방식(해제→변경→재압축→os.replace 원자 교체). 실패 시 원본 무손상, 암호 유지 검증 |
| 목록 정렬 | `main_window._populate_table` | 크기 칼럼 DisplayRole 숫자 저장으로 숫자 정렬 |

## 2. 설계 대비 차이

- gzip ISIZE 힌트로 원본 크기를 표시하려 했으나 `struct.unpack`이 아키텍처 불변식
  (수동 바이너리 파싱 금지, test_architecture_constraints)에 걸려 제거 — 크기 0으로 표시.
  불변식이 실제로 작동함을 확인한 사례.

## 3. 잘된 점

- 정렬 도입 시 "테이블 행 순서 ≠ manifest 순서" 버그를 기존 이미지 뷰어 테스트가
  즉시 잡아냈다(더블클릭을 행 인덱스가 아닌 이름 기반 조회로 수정).

## 4. 아쉬운 점

- 아카이브 편집이 전체 재작성이라 대용량에서 느리다(zip은 append 최적화 여지 있음).

## 5. 기술 부채 후보

- cp949 감지는 UTF-8/cp949 2단계 판별 - 일본어(shift-jis) 등 다국어 확장 여지.
- 단일 파일 해제 진행률이 총량을 모른 채 done==total로 보고됨(불확정 진행 표시 UI 미도입).

## 6. 후속 작업 (plan.md Out 항목 유지)

- 분할 압축(볼륨), EGG/ALZ 해제, 탐색기식 폴더 트리 UI, 코드 서명.
- 릴리스 시 버전 0.4.0 권장(사용자 가시 기능 다수 추가).
