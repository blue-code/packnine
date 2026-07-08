---
트랙ID: track_20260708_packnine_archiver
문서경로: \conductor\tracks\track_20260708_packnine_archiver\implementation.md
프로젝트명: PackNine
작업일시: 2026-07-08
작성자: Kent
문서유형: Implementation
세션목적: DDD 계층 설계 및 TDD/SDD 적용 전략 확정
track_status: approved
parent_track: (없음, 최초 트랙)
depends_on:
  - track_20260708_packnine_archiver (analysis.md)
impact_matrix: {}
---

## 1. 구현 전략

SDD → TDD → 구현 순서를 엄격히 따른다.
1. **SDD**: `domain/` 계층에 값객체(dataclass)·인터페이스(Protocol/ABC)를 먼저 정의
2. **TDD**: 각 서비스에 대한 실패하는 테스트를 `tests/`에 먼저 작성
3. **구현**: 테스트를 통과시키는 최소 구현 → 리팩터링

## 2. 아키텍처 (DDD 계층)

```
packnine/
├── domain/                # 순수 비즈니스 로직, 외부 의존성 없음
│   ├── entities.py        # ArchiveEntry, ArchiveManifest
│   ├── value_objects.py   # ArchivePath, CompressionLevel, PasswordPolicy
│   ├── security_policy.py # ArchiveSecurityPolicy (Zip Slip/폭탄/심링크 방어)
│   └── interfaces.py      # ArchiveReader/ArchiveWriter Protocol
├── application/           # 유스케이스 오케스트레이션
│   ├── compress_service.py
│   ├── extract_service.py
│   └── inspect_service.py
├── infrastructure/        # 포맷별 어댑터 (외부 라이브러리 의존)
│   ├── zip_adapter.py
│   ├── sevenzip_adapter.py
│   ├── tar_adapter.py
│   ├── rar_adapter.py     # 해제 전용
│   └── format_registry.py
├── presentation/
│   ├── gui/                # PySide6
│   │   ├── main_window.py
│   │   ├── compress_dialog.py
│   │   └── widgets/
│   └── cli.py               # argparse 기반 CLI 진입점
└── main.py
tests/
├── domain/
├── application/
├── infrastructure/
└── fixtures/
```

## 3. 컴포넌트 설계

- `ArchiveSecurityPolicy.validate_entry(entry, destination_root)`:
  경로 정규화 → 목적지 루트 이탈 여부, 절대경로/드라이브 문자, 심볼릭 링크,
  개별/누적 압축비 초과 여부를 검사하고 위반 시 `UnsafeArchiveEntryError` 발생
- `ArchiveReader` / `ArchiveWriter` Protocol: 포맷 어댑터가 구현해야 하는 최소 인터페이스
  (`list_entries`, `extract_all`, `extract_one`, `add_files`, `close`)
- `CompressService` / `ExtractService`: 어댑터를 조합해 유스케이스 실행, 진행률 콜백 지원
- GUI는 애플리케이션 서비스만 호출하고 어댑터를 직접 참조하지 않음 (계층 경계 유지)

## 4. 데이터 흐름

1. GUI/CLI → `CompressService.compress(files, dest, options)` 호출
2. 서비스가 `format_registry`에서 확장자에 맞는 Writer 어댑터 획득
3. 각 파일에 대해 `SecurityPolicy` 사전 검사(입력 파일 존재/심볼릭릭 여부) 후 어댑터에 위임
4. 어댑터가 실제 압축 라이브러리 호출, 진행률을 콜백으로 상위에 보고
5. 해제 시에는 어댑터가 엔트리 목록을 먼저 나열 → `SecurityPolicy.validate_entry`를
   전체 통과한 뒤에만 실제 디스크 쓰기 수행 (all-or-nothing 사전 검증)

## 5. 예외 처리

- `UnsafeArchiveEntryError`: 악성 엔트리 발견 시 사용자에게 구체적 사유와 함께 중단
- `UnsupportedFormatError`: 확장자/매직바이트로 포맷을 판별할 수 없을 때
- `ExternalToolMissingError`: RAR 해제용 `unrar`/`bsdtar` 미설치 시 설치 안내 메시지 포함
- 모든 GUI 액션은 최상위에서 예외를 잡아 모달 대화상자로 표시(애플리케이션 크래시 방지)

## 6. 테스트 전략 (TDD)

- 도메인 계층: 순수 함수/값객체 단위 테스트(외부 I/O 없음, 가장 빠르고 많은 비중)
- 보안 정책: Zip Slip 시도 경로(`../../etc/passwd`), 절대경로, 과도한 압축비(zip bomb
  fixture) 등 악의적 케이스를 표 기반(`pytest.mark.parametrize`)으로 검증
- 인프라 어댑터: `tmp_path`를 이용한 실제 파일 생성 → 압축 → 해제 round-trip 검증
- GUI: `pytest-qt`로 스모크 테스트(주요 액션 클릭 시 서비스 호출 여부) — 전체 커버리지는
  도메인/인프라 대비 낮게 유지(GUI 테스트는 비용 대비 효율이 낮음)
- CI: GitHub Actions에서 Windows + Ubuntu 매트릭스로 pytest 실행, `pip-audit`으로 의존성
  취약점 스캔 병행

## 7. 개선 포인트 (Phase 2 이후 후보)

- 정식 Windows Shell Extension(컨텍스트 메뉴 아이콘 포함) 도입
- 아카이브 내부 이미지/텍스트 미리보기 패널
- 멀티스레드 압축(대용량 폴더 성능 개선)
- 코드 서명 인증서 적용으로 SmartScreen 경고 제거
