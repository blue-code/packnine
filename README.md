# PackNine

**PackNine — ZIP/7Z/TAR/RAR을 지원하는 오리지널 오픈소스 Windows 압축 프로그램**

> ⚠️ 이 프로젝트는 Bandisoft社의 반디집(Bandizip)과 무관한 독립적인 오픈소스 프로젝트입니다.
> 이름·로고·UI를 포함해 반디집의 상표 및 디자인을 복제하지 않으며, "반디집과 유사한 사용
> 경험을 제공하는 완전히 새로운 구현체"를 목표로 합니다.

## 소개

PackNine은 Python 3.12와 PySide6로 작성된 Windows용 압축/해제 데스크톱 프로그램입니다.
ZIP, 7Z, TAR 계열(GZ/BZ2/XZ) 압축·해제와 RAR 해제를 지원하며, 설계 단계에서부터 Zip Slip·
압축 폭탄과 같은 알려진 압축 관련 보안 취약점을 방어하도록 만들어졌습니다.

## 주요 기능

- **압축**: ZIP, 7Z, TAR, TAR.GZ, TAR.BZ2, TAR.XZ
- **해제**: 위 포맷 전체 + RAR(해제 전용)
- **암호 설정**: ZIP/7Z 아카이브에 AES-256 암호화 적용
- **압축률 선택**: 저장/빠름/보통/최대 등 압축 레벨 선택
- **GUI**: 드래그 앤 드롭, 파일 목록 트리/테이블 뷰, 압축 다이얼로그, 진행률 표시
- **CLI**: GUI 없이 스크립트/배치 작업으로 압축·해제 가능
- **보안 특징**
  - Zip Slip(경로 탈출) 방지 — 모든 엔트리 경로를 목적지 루트 하위인지 검증
  - 압축 폭탄(Decompression Bomb) 방지 — 엔트리별/전체 압축비 및 총 용량 상한 검사
  - 심볼릭 링크/절대경로 엔트리 기본 거부
  - RAR은 자체 네이티브 파서를 구현하지 않고 `rarfile` + 신뢰할 수 있는 시스템
    `unrar`/`bsdtar` 바이너리에 위임

자세한 보안 설계는 [SECURITY.md](./SECURITY.md)를 참고하세요.

## 설치 방법

### 개발 환경으로 설치

```powershell
pip install -e ".[dev]"
```

### 릴리즈 실행 파일 다운로드

Windows용 빌드된 실행 파일(exe)은 GitHub Release 페이지에서 내려받을 수 있습니다.

(릴리즈 페이지 링크는 추후 추가)

## 사용법

### GUI 실행

```powershell
python -m packnine.main
```

또는 설치 후 제공되는 커맨드로 실행할 수 있습니다.

```powershell
packnine
```

### CLI 사용 예시

```powershell
# 압축
packnine compress --format zip -o output.zip file1.txt file2.txt folder\

# 암호를 지정하여 7z로 압축
packnine compress --format 7z --password "안전한암호" -o output.7z folder\

# 해제
packnine extract output.zip --dest .\extracted

# RAR 해제 (시스템에 unrar 또는 bsdtar 필요)
packnine extract archive.rar --dest .\extracted
```

> CLI 하위 명령/옵션은 개발 진행에 따라 변경될 수 있습니다. 최신 사용법은 `packnine --help`로
> 확인해주세요.

## 개발 방법론

본 프로젝트는 **SDD(Spec-Driven Development) → TDD(Test-Driven Development) → DDD
(Domain-Driven Design)** 순서를 따르는 개발 방법론을 채택합니다.

1. **SDD**: 구현 전 `domain/` 계층에 값객체(dataclass)와 인터페이스(Protocol/ABC)를 먼저
   정의하여 스펙을 확정합니다.
2. **TDD**: 각 서비스에 대한 실패하는 테스트를 `tests/`에 먼저 작성한 뒤, 이를 통과시키는
   최소 구현을 추가하고 리팩터링합니다.
3. **DDD**: 도메인/애플리케이션/인프라/표현 계층의 책임 경계를 명확히 분리합니다.

### 프로젝트 구조

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
│   └── cli.py               # argparse 기반 CLI 진입점
└── main.py
tests/
├── domain/
├── application/
├── infrastructure/
└── fixtures/
```

## 테스트 실행

```powershell
pytest
```

도메인 계층과 보안 정책(Zip Slip, 압축 폭탄, 심볼릭 링크 등 악의적 케이스)을 중심으로
`pytest.mark.parametrize` 기반 테이블 테스트가 구성되어 있으며, 인프라 어댑터는
`tmp_path`를 이용한 압축→해제 왕복(round-trip) 검증을 포함합니다.

## RAR 해제 관련 안내

RAR 아카이브 해제를 위해서는 시스템에 **unrar** 또는 **bsdtar**가 설치되어 있어야 합니다.
PackNine은 RAR 파일 헤더 파싱에 `rarfile` 라이브러리를 사용하지만, 실제 압축 해제는 검증된
외부 바이너리에 위임합니다(자체 네이티브 RAR 파서를 구현하지 않는 이유는
[SECURITY.md](./SECURITY.md)를 참고하세요).

- Windows: [unrar](https://www.rarlab.com/rar_add.htm) 실행 파일을 PATH에 추가하거나,
  `bsdtar`(libarchive)를 설치합니다.
- unrar/bsdtar가 설치되어 있지 않으면 RAR 해제 시 안내 메시지와 함께 오류가 발생합니다.

## 라이선스

이 프로젝트는 [MIT 라이선스](./LICENSE)를 따릅니다.

PackNine은 Bandisoft社의 반디집(Bandizip)과 무관한 독립적인 오픈소스 프로젝트이며, 반디집의
상표·이름·로고·디자인을 사용하지 않습니다.
