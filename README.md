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
- **해제**: 위 포맷 전체 + RAR + 단일 파일 압축(.gz/.bz2/.xz) (해제 전용)
- **한글 파일명 자동 복원**: 알집 등 구형 도구가 만든 zip의 깨진 한글 파일명(cp949)을
  자동 감지해 올바르게 표시·해제 (반디집 "코드 페이지 자동 감지" 대응)
- **아카이브 편집**: 열려 있는 아카이브에 파일 추가/선택 삭제 (전 포맷 공통, 실패 시
  원본 무손상 보장)
- **내부 파일 바로 열기**: 아카이브 안의 문서를 더블클릭하면 기본 연결 프로그램으로
  즉시 열기 (이미지는 내장 뷰어)
- **암호 설정**: ZIP/7Z 아카이브에 진짜 AES-256 암호화 적용(ZIP은 pyzipper 기반
  WinZip AES 방식으로 반디집/7-Zip/WinRAR과 호환). 비밀번호가 틀리면 디스크에 쓰기 전에
  차단하고, GUI/우클릭 메뉴에서는 비밀번호 입력 다이얼로그로 재시도할 수 있음
- **압축률 선택**: 저장/빠름/보통/최대 등 압축 레벨 선택
- **분할 압축**: ZIP/7Z를 지정한 크기(MB)의 볼륨(`이름.7z.001`, `.002` …)으로 나눠 저장.
  옵션 창에 네이버 메일(일반 10MB/대용량 2GB), 다음 메일(일반 25MB/대용량 4GB), Gmail(25MB)
  첨부 한도 프리셋이 있고, 결과가 한 조각이면 `.001` 없이 일반 파일로 저장. 첫 볼륨(`.001`)을
  열거나 우클릭 "알아서 풀기"로 해제 (zip 분할은 7-Zip 방식 `.zip.001`이라 반디집·7-Zip·
  알집에서 열리며 Windows 탐색기 기본 풀기로는 열리지 않음)
- **알아서 압축 / 알아서 압축풀기**: 목적지 경로·파일명을 다이얼로그 없이 자동으로 정해
  바로 처리 (`smart-compress`/`smart-extract`)
- **멀티코어 각각 압축**: "각각 압축하기"는 항목들을 CPU 코어 수에 맞춰 동시에 압축한다
  (6개 항목 기준 3.7배 단축). `-j/--jobs`로 동시 실행 개수를 조절할 수 있음
- **중복 파일 처리 선택**: 해제 시 같은 이름의 파일이 있으면 덮어쓰기 / 건너뛰기 /
  둘 다 남기기(`_2` 접미사)를 고를 수 있음. GUI는 충돌이 있을 때만 물어보고, CLI는
  `--on-conflict overwrite|skip|rename`로 지정 (기본값은 기존 동작인 덮어쓰기)
- **드래그 아웃**: 아카이브를 연 상태에서 파일·폴더를 탐색기로 끌어내면 그대로 복사됨
  (임시 폴더에 꺼낸 뒤 넘기며, 원본 아카이브의 MoTW 표시를 함께 물려줌)
- **탐색기 우클릭 메뉴**: 설치 프로그램 또는 `packnine register-context-menu`로 등록하면
  "PackNine" 하위 메뉴 하나로 묶여 표시 (다중 선택 지원, 관리자 권한 불필요)
  - 파일: PackNine으로 압축하기...(옵션 창: 포맷·강도·비밀번호·분할) · 압축하기(즉시)
  - 폴더: PackNine으로 압축하기...(옵션 창) · 압축하기(즉시) · 각각 압축하기
  - 압축 파일(분할 첫 볼륨 `.001` 포함): 알아서 풀기 · 여기에 풀기 · 열기 · 압축하기
- **내장 이미지 뷰어**: 아카이브를 열고 이미지 파일을 더블클릭하면 바로 미리보기
  (이전/다음 탐색 지원)
- **내부 파일 미리보기**: 목록에서 파일을 고르면 압축을 풀지 않고 바로 내용을 확인.
  이미지는 그림으로, 텍스트(txt/md/csv/json/log/소스코드 등)는 앞부분을 읽어 보여준다
  (UTF-8·cp949 자동 판별, 큰 파일은 앞부분만 읽어 멈추지 않음)
- **아카이브 안에서 찾기**: `Ctrl+F`로 이름 검색. 현재 폴더가 아니라 아카이브 전체를
  훑어 전체 경로와 함께 보여준다
- **선택 항목만 풀기**: 필요한 파일·폴더만 골라 지정한 폴더에 해제 (전체 해제와 별개)
- **최근 연 압축 파일**: 파일 메뉴에서 최근 연 아카이브 10개를 바로 다시 열기
  (사라진 파일은 자동으로 목록에서 제외)
- **GUI**: 드래그 앤 드롭, 파일 목록 테이블 뷰, 압축 다이얼로그, 진행률 표시
- **CLI**: GUI 없이 스크립트/배치 작업으로 압축·해제 가능
- **보안 특징**
  - Zip Slip(경로 탈출) 방지 — 모든 엔트리 경로를 목적지 루트 하위인지 검증
  - 압축 폭탄(Decompression Bomb) 및 대량 엔트리를 이용한 자원 고갈(DoS) 방지
  - 심볼릭 링크/하드링크/절대경로/NTFS ADS(콜론 포함 이름) 엔트리 기본 거부
  - 압축 해제 후 원본 아카이브의 MoTW(Mark of the Web) 정보를 해제된 파일에 전파해
    SmartScreen 등 Windows 보호 기제가 계속 작동하도록 함
  - RAR은 자체 네이티브 파서를 구현하지 않고 `rarfile` + 신뢰할 수 있는 시스템
    `unrar`/`bsdtar` 바이너리에 위임

자세한 보안 설계는 [SECURITY.md](./SECURITY.md)를 참고하세요.

## 설치 방법

### 설치 프로그램 사용 (권장)

GitHub Release에서 `PackNine-Setup.exe`를 내려받아 실행하면 관리자 권한 없이
`%LOCALAPPDATA%\Programs\PackNine`에 설치되고, 시작메뉴/바탕화면 바로가기와 탐색기
우클릭 메뉴가 자동으로 등록됩니다.

https://github.com/blue-code/packnine/releases

### 포터블 실행 파일

설치 없이 바로 쓰고 싶다면 같은 Release 페이지의 `PackNine.exe`(단일 실행 파일)를
내려받아 원하는 위치에서 실행하면 됩니다. 우클릭 메뉴를 쓰려면
`PackNine.exe register-context-menu`를 한 번 실행해주세요.

### macOS (베타, Apple Silicon 전용)

GitHub Release에서 `PackNine-macOS-arm64.zip`을 내려받아 압축을 풀면 `PackNine.app`이
나옵니다. Apple Silicon(M1 이상, macOS 11 이상)만 지원하며, 아직 Apple 개발자 서명이
적용되지 않아 최초 실행 시 Gatekeeper가 "확인되지 않은 개발자" 경고를 띄웁니다.

1. `PackNine.app`을 더블클릭했을 때 경고가 뜨면 **시스템 설정 > 개인정보 보호 및 보안**으로
   이동해 "PackNine을(를) 열기 위해 확인이 취소되었습니다" 항목 옆의 **[확인 없이 열기]**를
   누릅니다.
2. RAR 해제를 사용하려면 시스템에 `unrar` 또는 `bsdtar`가 필요합니다. 터미널에서
   `brew install unrar` 또는 `brew install libarchive`로 설치하세요.
3. 탐색기 우클릭 메뉴, MoTW(다운로드 표시) 전파 기능은 Windows 전용이며 macOS에서는
   아직 지원하지 않습니다(GUI/CLI 압축·해제 기능은 Windows와 동일하게 동작합니다).

### 개발 환경으로 설치

```powershell
pip install -e ".[dev]"
```

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
# 압축 (확장자로 포맷을 자동 판별)
packnine compress file1.txt file2.txt folder -o output.zip

# 암호를 지정하여 압축 (ZIP/7Z 모두 진짜 AES-256 적용)
packnine compress folder -o output.zip --password "안전한암호"
packnine compress folder -o output.7z --password "안전한암호"

# 분할 압축: 볼륨 하나를 25MB로 제한 (결과: big.7z.001, big.7z.002 ... / 한 조각이면 big.7z)
packnine compress big_folder -o big.7z --volume-size 25

# 해제
packnine extract output.zip -d .\extracted

# 분할 파일 해제: 첫 볼륨(.001)을 지정하면 나머지 볼륨은 같은 폴더에서 자동으로 찾는다
packnine extract big.7z.001 -d .\extracted

# RAR 해제 (시스템에 unrar 또는 bsdtar 필요)
packnine extract archive.rar -d .\extracted

# 알아서 압축: 목적지를 스스로 정해 바로 압축(단일 항목이면 그 이름, 여러 개면 폴더명 기준)
packnine smart-compress file1.txt file2.txt

# 각각 압축하기: 여러 항목을 하나로 묶지 않고 항목별 zip으로 압축
packnine smart-compress --each file1.txt file2.txt

# 압축 옵션 창 띄우기: 포맷/압축 강도/비밀번호/출력 경로를 고른 뒤 압축
# (우클릭 "PackNine으로 압축하기..."가 호출하는 명령. --no-collect는 다중 선택 병합 생략)
packnine compress-dialog --no-collect file1.txt file2.txt

# 각각 압축하기를 4개씩 동시에(멀티코어)
packnine smart-compress --each -j 4 file1.txt file2.txt file3.txt file4.txt

# 알아서 압축풀기: 아카이브 안에 루트 항목이 하나뿐이면 바로, 여러 개면 새 폴더에 풀기
packnine smart-extract output.zip

# 같은 이름의 파일이 있을 때: 건너뛰기 / 둘 다 남기기
packnine extract output.zip -d .\extracted --on-conflict skip
packnine extract output.zip -d .\extracted --on-conflict rename

# 아카이브 내용 목록 조회
packnine list output.zip

# 탐색기 우클릭 메뉴 등록/해제 (관리자 권한 불필요, HKCU에만 기록)
packnine register-context-menu
packnine register-context-menu --unregister
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
│   ├── value_objects.py   # ArchivePath, CompressionLevel, PasswordPolicy, VolumeSize/SPLIT_PRESETS
│   ├── security_policy.py # ArchiveSecurityPolicy (Zip Slip/폭탄/심링크 방어)
│   └── interfaces.py      # ArchiveReader/ArchiveWriter Protocol
├── application/           # 유스케이스 오케스트레이션
│   ├── compress_service.py
│   ├── extract_service.py
│   ├── inspect_service.py
│   ├── smart_naming.py    # "알아서 압축/압축풀기" 목적지 자동 결정
│   └── context_menu_service.py
├── infrastructure/        # 포맷별 어댑터 (외부 라이브러리 의존)
│   ├── zip_adapter.py
│   ├── sevenzip_adapter.py
│   ├── tar_adapter.py
│   ├── rar_adapter.py     # 해제 전용
│   ├── format_registry.py
│   ├── volume_io.py        # 분할 압축 볼륨(.001/.002 ...) 입출력
│   ├── motw.py             # MoTW(Zone.Identifier) 전파
│   └── context_menu.py     # 탐색기 우클릭 메뉴 등록/해제(winreg)
├── presentation/
│   ├── gui/                # PySide6 (main_window, compress_dialog, image_viewer)
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
