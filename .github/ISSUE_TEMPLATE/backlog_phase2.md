---
name: Phase 2 백로그
about: Phase 1(v0.1.0) 범위 밖으로 미룬 기능을 추적하기 위한 백로그 이슈
title: "[Phase 2] "
labels: backlog, phase2
assignees: ""
---

## 개요

이 이슈는 PackNine Phase 1(v0.1.0)의 In Scope에서 제외된 기능(Out of Scope)을 Phase 2
이후 로드맵으로 추적하기 위한 템플릿입니다. 아래 체크리스트 중 이 이슈에서 다룰 항목만
남기고 나머지는 지워주세요.

## Phase 2 후보 항목

- [ ] 아카이브 내부 이미지 뷰어/미리보기 슬라이드쇼
- [ ] 알집(.alz) 자동 변환
- [ ] 클라우드 연동 (구글 드라이브 업로드 등)
- [ ] 정식 Windows Shell Extension (탐색기 컨텍스트 메뉴 완전 통합, COM 기반)
- [ ] macOS/Linux GUI 정식 지원 (현재는 코드 구조만 크로스플랫폼 지향, 검증은 Windows만)
- [ ] 멀티스레드 압축 (대용량 폴더 성능 개선)
- [ ] 코드 서명 인증서 적용 (SmartScreen 경고 제거)

> 참고: RAR **압축**은 포맷이 비공개/상용 라이선스이므로 Phase 2 이후에도 지원하지 않습니다
> (해제 전용 정책은 변경되지 않습니다).

## 배경

- 관련 Track 문서: `conductor/tracks/track_20260708_packnine_archiver/plan.md`,
  `conductor/tracks/track_20260708_packnine_archiver/analysis.md`

## 추가 설명

(선택 사항: 이 항목이 왜 필요한지, 우선순위 근거 등을 자유롭게 작성해주세요)
