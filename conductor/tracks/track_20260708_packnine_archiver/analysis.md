---
트랙ID: track_20260708_packnine_archiver
문서경로: \conductor\tracks\track_20260708_packnine_archiver\analysis.md
프로젝트명: PackNine
작업일시: 2026-07-08
작성자: Kent
문서유형: Analysis
세션목적: 기술 스택 및 보안 대응 방안 분석
track_status: approved
parent_track: (없음, 최초 트랙)
depends_on:
  - track_20260708_packnine_archiver (plan.md)
impact_matrix: {}
---

## 1. 요구사항

- Windows 10/11에서 동작하는 데스크톱 GUI 압축 프로그램
- ZIP/7Z/TAR 계열 생성 및 해제, RAR 해제
- 비밀번호(AES-256) 설정 압축
- DDD 계층 분리, TDD(테스트 선행), SDD(인터페이스 선행 설계)
- 최신 보안 취약점 대응

## 2. 제약 사항

- RAR은 포맷 자체가 비공개/상용이므로 순수 오픈소스로 "압축"까지 구현하는 것은 불가
  (WinRAR 라이선스 문제) → 해제만 지원
- PySide6(LGPL)는 상용 배포 시에도 소스 공개 의무 없이 사용 가능(동적 링크 준수 시)
- 코드 서명 인증서 미보유 → 빌드 exe는 SmartScreen 경고가 뜰 수 있음(범위 외)
- 정식 탐색기 셸 확장(Context Menu Handler)은 COM in-process 서버 등록이 필요해
  구현 난이도·검증 비용이 큼 → Phase 1에서는 레지스트리 `shell\` 서브메뉴 명령 등록으로 대체

## 3. 기존 구조 분석

`C:\DEV\PYTHON_PROJECT`는 다수의 독립 프로젝트 폴더가 모여 있는 워크스페이스이며 최상위는
git 저장소가 아님. 따라서 `PackNine/` 하위 디렉터리를 별도 git 저장소 루트로 사용한다.

## 4. 대안 비교 — 압축 라이브러리

| 포맷 | 후보 | 선택 | 이유 |
|---|---|---|---|
| ZIP | 표준 `zipfile` | 채택 | 표준 라이브러리, 보안 패치가 CPython 릴리즈와 함께 관리됨 |
| 7Z | `py7zr` | 채택 | 순수 Python 구현(네이티브 DLL 파싱 취약점 노출면 적음), 활발히 유지보수 |
| TAR/GZ/BZ2/XZ | 표준 `tarfile` | 채택 | 표준 라이브러리. Python 3.12+ `tarfile.data_filter` 로 Zip Slip류 기본 방어(PEP 706) |
| RAR(해제) | `rarfile` + 외부 `unrar`/`bsdtar` | 채택 | 파이썬 코드 자체는 헤더 파싱만 하고 실제 압축해제는 검증된 외부 바이너리에 위임 → 자체 구현 취약점 최소화 |
| RAR(해제) 대안 | `unrardll`(구 UnACEV2 계열) | 기각 | CVE-2018-20250 등 과거 심각한 원격 코드 실행 취약점 이력 → 사용 금지 |

## 5. 선택 이유 — GUI 프레임워크

- **PySide6(Qt6) 채택**: 네이티브에 가까운 위젯, 파일트리/테이블 뷰 컴포넌트 성숙,
  Python 표준 스택과 통합 용이, TDD를 위한 로직/뷰 분리(MVVM 유사 구조)가 쉬움.
- Electron 대비 대용량 파일 처리 시 메모리 오버헤드가 적음.
- WPF/C# 대비 기존 프로젝트 워크스페이스가 전부 Python 기반이라 스택 일관성 유지.

## 6. 기술적 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| Zip Slip (`../../evil.exe` 형태 경로) | 압축 해제 전 모든 엔트리 경로를 정규화 후 목적지 루트 하위인지 검증. `tarfile`은 `filter='data'` 강제 |
| 압축 폭탄(Decompression Bomb) | 엔트리별/전체 압축비 상한(예: 100:1) 및 총 해제 용량 상한 검사 후 초과 시 거부 |
| 심볼릭 링크/디바이스 파일 엔트리 | TAR 엔트리 타입이 symlink/hardlink/device인 경우 기본 거부(옵션으로만 허용) |
| 절대 경로 엔트리(`C:\Windows\...`) | 경로가 절대경로이거나 드라이브 문자를 포함하면 거부 |
| 구버전 라이브러리 CVE | `py7zr`, `rarfile` 등은 최신 안정 버전으로 고정(pin)하고 `pip-audit`을 CI에 추가해 지속 점검 |
| 압축 파일 자체의 손상/파싱 예외 | 모든 아카이브 파싱을 try/except로 감싸 애플리케이션 크래시 대신 사용자 경고로 변환 |

## 7. 결론

Python 3.12 + PySide6 + 표준 라이브러리(zipfile/tarfile) + py7zr + rarfile 조합으로
Phase 1을 구현한다. 보안 검증 로직은 인프라 어댑터가 아닌 **도메인 계층의 정책 객체**
(`ArchiveSecurityPolicy`)로 분리하여 모든 포맷 어댑터가 공통으로 재사용하도록 SDD 원칙에
따라 인터페이스를 먼저 정의한다.
