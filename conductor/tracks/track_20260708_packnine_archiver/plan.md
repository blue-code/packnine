---
트랙ID: track_20260708_packnine_archiver
문서경로: \conductor\tracks\track_20260708_packnine_archiver\plan.md
프로젝트명: PackNine
작업일시: 2026-07-08
작성자: Kent
문서유형: Plan
세션목적: 반디집(Bandizip) 대체 오리지널 압축/해제 프로그램(PackNine) 신규 개발
track_status: approved
parent_track: (없음, 최초 트랙)
depends_on: []
impact_matrix: {}
---

## 1. 기획 배경

사용자가 반디집(Bandizip, https://kr.bandisoft.com/bandizip/screenshots/) 과 유사한 수준의
Windows용 압축/해제 프로그램을 직접 개발하여 GitHub에 공개하고자 함. 반디집은 상용/상표
보호 대상이므로 이름·로고·UI 디자인을 그대로 복제하지 않고, **핵심 기능(압축·해제·미리보기·
편의 기능)을 오리지널 구현으로 재해석**한 프로그램 "PackNine"을 만든다.

## 2. 문제 정의

- 대부분의 오픈소스 압축 프로그램은 UX가 낙후되었거나(7-Zip 기본 UI), 유지보수가 중단됨.
- 압축 해제 시 Zip Slip, 압축 폭탄(Decompression Bomb), 경로 탐색(Path Traversal) 등
  알려진 보안 취약점을 제대로 방어하지 않는 도구가 많음.
- RAR 해제용 구형 라이브러리(UnACEV2.dll 등)에서 발견된 CVE(CVE-2018-20250 계열)처럼,
  오래된 네이티브 파서를 그대로 쓰면 취약점을 그대로 물려받는 문제가 있음.

## 3. 목표

1. ZIP/7Z/TAR 계열(GZ/BZ2/XZ)/RAR(해제 전용) 등 주요 포맷을 지원하는 GUI 압축 프로그램 제작
2. DDD(도메인 계층 분리) + TDD(테스트 선행) + SDD(인터페이스/스키마 선행 설계) 방법론 적용
3. 알려진 압축 라이브러리 보안 이슈(Zip Slip, 압축 폭탄, 심볼릭 링크 탈출, 구버전 CVE)를
   설계 단계에서부터 방어
4. GitHub Public 저장소에 소스 공개, Windows 실행파일(exe) 릴리즈 배포

## 4. 범위 (In / Out)

### In Scope — Phase 1 (v0.1.0, 이번 세션 목표)
- 압축: ZIP, 7Z, TAR/TAR.GZ/TAR.BZ2/TAR.XZ 생성
- 해제: 위 포맷 전체 + RAR(해제 전용, `rarfile` + 시스템 `unrar`/`bsdtar` 의존)
- 암호 설정(AES-256, ZIP/7Z), 압축률 선택
- PySide6 기반 GUI: 파일 목록(트리/테이블), 드래그 앤 드롭, 툴바(추가/추출/테스트/삭제),
  압축 다이얼로그, 진행률 표시
- 보안: Zip Slip 방지, 경로 정규화 검증, 압축 해제 시 압축비 상한(폭탄 방지),
  심볼릭 링크/절대경로 항목 거부
- CLI 겸용 진입점 (GUI 없이 배치 압축/해제 가능)
- 자동화 테스트(pytest, TDD로 선행 작성), CI(GitHub Actions)
- Windows 우클릭 탐색기 연동은 **레지스트리 기반 간이 등록**(셸 확장 DLL 없이 exe 인자 호출)
  방식으로 한정

### Out of Scope — Phase 2+ (백로그, 이번 세션 이후 GitHub Issue로 관리)
- 압축파일 내부 이미지 뷰어/미리보기 슬라이드쇼
- 알집(.alz) 자동 변환, 클라우드 연동(구글드라이브 업로드 등)
- 정식 Windows Shell Extension(탐색기 컨텍스트 메뉴 완전 통합, COM 기반)
- RAR **압축**(포맷이 비공개/상용 라이선스이므로 지원하지 않음, 해제만 지원)
- macOS/Linux GUI 정식 지원 (코드 구조는 크로스플랫폼 지향하되 검증은 Windows만)

## 5. 사용자 시나리오

1. 사용자가 파일 여러 개를 PackNine 창에 드래그 앤 드롭 → 압축 다이얼로그에서 포맷/암호/
   압축률 선택 → `.zip` 또는 `.7z` 생성
2. 사용자가 `.zip`/`.7z`/`.tar.gz`/`.rar` 파일을 더블클릭 → PackNine이 내부 목록을 보여주고
   "전체 압축해제" 또는 개별 항목 추출 가능
3. 손상되었거나 악의적으로 조작된 아카이브(Zip Slip 시도, 과도한 압축비)를 열었을 때
   프로그램이 안전하게 거부하고 사용자에게 경고

## 6. 성공 기준

- [ ] pytest 전체 테스트 그린 (도메인/인프라 계층 커버리지 80% 이상)
- [ ] Zip Slip / 경로 탈출 / 압축 폭탄 방어 테스트가 실제로 악의적 아카이브를 차단함을 검증
- [ ] GUI로 실제 압축·해제 왕복(round-trip) 수동 검증 완료
- [ ] GitHub Public 저장소 생성 및 최초 커밋 푸시 완료
- [ ] PyInstaller로 빌드한 Windows exe를 GitHub Release(v0.1.0)에 첨부

## 7. 리스크 및 가정

- **가정**: 개발/빌드 환경에 Python 3.12, PySide6, 관련 패키지 설치가 가능하다.
- **리스크**: RAR 해제는 외부 `unrar`/`bsdtar` 바이너리 유무에 따라 동작이 달라질 수 있음
  → 미설치 시 명확한 에러 메시지와 설치 안내로 대응.
- **리스크**: PyInstaller 빌드 exe가 Windows Defender/SmartScreen에 의해 오탐될 수 있음
  → README에 안내 문구 추가, 코드 서명은 이번 범위에서 제외(비용/인증서 필요).
- **리스크**: "반디집 수준 풀 기능"은 범위가 매우 넓어 1세션 내 100% 재현이 불가능함
  → Phase 1(핵심 MVP + 편의기능)까지 완성해 v0.1.0으로 릴리즈하고, 나머지는 GitHub Issue
  백로그로 문서화하여 로드맵을 투명하게 공개한다.
