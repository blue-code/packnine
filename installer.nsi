; PackNine Windows 설치 프로그램(NSIS 스크립트)
; 관리자 권한 없이(RequestExecutionLevel user) 사용자 프로필 아래에 설치한다.
; 컴파일: "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi

Unicode true

!include "MUI2.nsh"

Name "PackNine"
OutFile "dist\PackNine-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\PackNine"
InstallDirRegKey HKCU "Software\PackNine" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ICON "packnine\presentation\gui\assets\icon.ico"
!define MUI_UNICON "packnine\presentation\gui\assets\icon.ico"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Korean"

;--------------------------------
; 필수 설치 섹션

Section "PackNine 프로그램 (필수)" SecCore
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "dist\PackNine.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\PackNine"
  CreateShortcut "$SMPROGRAMS\PackNine\PackNine.lnk" "$INSTDIR\PackNine.exe"
  CreateShortcut "$SMPROGRAMS\PackNine\PackNine 제거.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\PackNine" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "DisplayName" "PackNine"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "DisplayIcon" "$INSTDIR\PackNine.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "Publisher" "PackNine Contributors"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "DisplayVersion" "0.6.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine" "NoRepair" 1
SectionEnd

Section "바탕화면 바로가기" SecDesktop
  CreateShortcut "$DESKTOP\PackNine.lnk" "$INSTDIR\PackNine.exe"
SectionEnd

Section "탐색기 우클릭 메뉴 등록 (압축/압축해제)" SecContextMenu
  ; HKCU에만 키를 쓰므로 관리자 권한이 필요 없다. 실패해도 설치 자체는 계속 진행한다.
  ExecWait '"$INSTDIR\PackNine.exe" register-context-menu'
SectionEnd

;--------------------------------
; 섹션 설명 (컴포넌트 페이지에 표시)

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} "PackNine 실행 파일을 설치합니다. (필수)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "바탕화면에 PackNine 바로가기를 만듭니다."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecContextMenu} "탐색기에서 파일을 우클릭해 바로 압축/압축해제할 수 있게 합니다."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; 제거 섹션

Section "Uninstall"
  ; 등록했던 우클릭 메뉴를 먼저 해제한다 (실패해도 나머지 제거는 계속 진행).
  ExecWait '"$INSTDIR\PackNine.exe" register-context-menu --unregister'

  Delete "$INSTDIR\PackNine.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\PackNine\PackNine.lnk"
  Delete "$SMPROGRAMS\PackNine\PackNine 제거.lnk"
  RMDir "$SMPROGRAMS\PackNine"
  Delete "$DESKTOP\PackNine.lnk"

  DeleteRegKey HKCU "Software\PackNine"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\PackNine"
SectionEnd
