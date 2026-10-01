//! PackNine Windows 11 탐색기 컨텍스트 메뉴 핸들러.
//!
//! 왜 네이티브 DLL인가: Windows 11의 기본(모던) 우클릭 메뉴는 레지스트리 verb를 읽지 않고
//! `IExplorerCommand`를 구현한 COM 핸들러만 노출한다. 레거시 verb는 "추가 옵션 표시" 안쪽으로
//! 밀려나므로, 기본 메뉴에 올리려면 이 DLL이 반드시 필요하다.
//!
//! 이 DLL은 MSIX 패키지 안에 함께 들어가고, 매니페스트의
//! `desktop4:FileExplorerContextMenus`가 아래 CLSID를 가리킨다. 패키지 서명은
//! 마이크로소프트가 스토어 제출 시 수행하므로 별도 인증서가 필요 없다.
//!
//! 메뉴 구조: 반디집처럼 "PackNine" 하나로 묶고 그 아래에 동작을 둔다. 루트 명령이
//! `ECF_HASSUBCOMMANDS`를 돌려주고 `EnumSubCommands`로 하위 항목을 넘기는 방식이다.
//! 레거시 레지스트리 캐스케이드는 과거(v0.5.x) 일부 탐색기 경로에서 명령이 실행되지 않아
//! 되돌린 적이 있지만, `IExplorerCommand`의 하위 명령은 셸이 공식 지원하는 구조라
//! 그 문제가 없다.
//!
//! 하는 일은 하나뿐이다: 선택된 경로들을 모아 PackNine.exe를 적절한 인자로 실행한다.
//! 압축 로직은 전부 파이썬 쪽에 있고, 여기서는 아무 파일도 읽거나 쓰지 않는다 - 탐색기
//! 프로세스 안에서 도는 코드이므로 최대한 얇게 유지해 장애 지점을 줄인다.

mod popup;
mod preview;

use std::cell::Cell;
use std::ffi::OsString;
use std::os::windows::ffi::OsStringExt;
use std::path::PathBuf;

use windows::core::*;
use windows::Win32::Foundation::*;
use windows::Win32::System::Com::*;
use windows::Win32::System::LibraryLoader::GetModuleFileNameW;
use windows::Win32::UI::Shell::*;

/// 이 핸들러의 CLSID. 매니페스트(AppxManifest.xml)의 값과 반드시 일치해야 한다.
pub const CLSID_PACKNINE_COMPRESS: GUID = GUID::from_u128(0xd1c9c67d_cf0a_494e_9e84_4fedb96d2272);

/// DLL 자신의 모듈 핸들. DllMain에서 받아 exe 경로를 계산할 때 쓴다.
static mut DLL_MODULE: HMODULE = HMODULE(std::ptr::null_mut());

/// 살아 있는 COM 객체 수. 0이 되어야 탐색기가 DLL을 내려도 안전하다.
static OBJECT_COUNT: std::sync::atomic::AtomicIsize = std::sync::atomic::AtomicIsize::new(0);

pub(crate) fn object_added() {
    OBJECT_COUNT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
}

pub(crate) fn object_removed() {
    OBJECT_COUNT.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
}

/// 압축 파일로 취급할 확장자. 파이썬 쪽 _ARCHIVE_EXTENSIONS와 같은 목록이다.
const ARCHIVE_EXTENSIONS: [&str; 9] = [
    "zip", "7z", "rar", "tar", "tgz", "gz", "bz2", "xz", "001",
];

fn is_archive(path: &str) -> bool {
    let lowered = path.to_ascii_lowercase();
    match lowered.rsplit_once('.') {
        Some((_, ext)) => ARCHIVE_EXTENSIONS.contains(&ext),
        None => false,
    }
}

/// 메뉴에 올라가는 명령 종류. 루트 하나와 그 아래 동작들로 나뉜다.
#[derive(Clone, Copy, PartialEq)]
enum CommandKind {
    /// "PackNine" - 하위 메뉴를 갖는 묶음 항목.
    Root,
    /// 압축 파일을 PackNine으로 열어 내용을 본다.
    Preview,
    /// 내용에 맞춰 알아서 풀기.
    ExtractSmart,
    /// 현재 폴더에 바로 풀기.
    ExtractHere,
    /// 옵션 창을 띄워 포맷·강도·비밀번호·제외 패턴을 고른 뒤 압축.
    CompressWithOptions,
    /// 묻지 않고 바로 zip으로 압축.
    CompressNow,
    /// 선택 항목을 하나로 묶지 않고 항목별로 각각 압축.
    CompressEach,
}

/// 선택 내용에 따라 이 항목을 메뉴에 띄울지 정한다.
///
/// 레지스트리 verb로는 "선택 개수"나 "확장자 조합"을 조건으로 걸 수 없어서, 파일 하나를
/// 골라도 "각각 압축하기"가 뜨고 압축 파일을 골라도 압축 메뉴만 뜨는 문제가 있었다.
/// IExplorerCommand는 선택 목록을 그대로 받으므로 여기서 걸러낼 수 있다.
fn should_show(kind: CommandKind, paths: &[String]) -> bool {
    if paths.is_empty() {
        return false;
    }
    let all_archives = paths.iter().all(|p| is_archive(p));
    match kind {
        CommandKind::Root => true,
        // 풀기/보기 계열은 고른 것이 전부 압축 파일일 때만 의미가 있다.
        // 미리보기는 창을 띄우므로 여러 개를 고르면 창이 쏟아진다 - 하나일 때만.
        CommandKind::Preview => all_archives && paths.len() == 1,
        CommandKind::ExtractSmart | CommandKind::ExtractHere => all_archives,
        // 압축 계열은 언제나 가능하다(압축 파일을 다시 압축할 수도 있다).
        CommandKind::CompressWithOptions | CommandKind::CompressNow => true,
        // "각각"은 2개 이상일 때만 의미가 있다 - 하나면 바로 압축하기와 결과가 같다.
        CommandKind::CompressEach => paths.len() >= 2,
    }
}

impl CommandKind {
    fn title(self) -> PCWSTR {
        match self {
            CommandKind::Root => w!("PackNine"),
            CommandKind::Preview => w!("미리보기"),
            CommandKind::ExtractSmart => w!("알아서 풀기"),
            CommandKind::ExtractHere => w!("여기에 풀기"),
            CommandKind::CompressWithOptions => w!("압축하기..."),
            CommandKind::CompressNow => w!("바로 압축하기"),
            CommandKind::CompressEach => w!("각각 압축하기"),
        }
    }

    /// PackNine.exe에 넘길 인자. 선택 경로는 호출부가 뒤에 덧붙인다.
    fn arguments(self) -> &'static [&'static str] {
        match self {
            // 루트는 직접 실행되지 않지만, 혹시 눌렸을 때를 대비해 옵션 창과 같게 둔다.
            CommandKind::Root | CommandKind::CompressWithOptions => {
                &["compress-dialog", "--no-collect"]
            }
            CommandKind::Preview => &["open"],
            CommandKind::ExtractSmart => &["smart-extract"],
            CommandKind::ExtractHere => &["smart-extract", "--here"],
            CommandKind::CompressNow => &["smart-compress"],
            CommandKind::CompressEach => &["smart-compress", "--each"],
        }
    }

    fn has_subcommands(self) -> bool {
        matches!(self, CommandKind::Root)
    }
}

/// 하위 메뉴에 들어갈 순서. 압축 파일을 골랐을 때 가장 자주 쓰는 동작이 위로 오도록
/// 풀기 계열을 앞에 둔다(해당 없는 항목은 should_show가 숨긴다).
const SUB_COMMANDS: [CommandKind; 6] = [
    CommandKind::Preview,
    CommandKind::ExtractSmart,
    CommandKind::ExtractHere,
    CommandKind::CompressWithOptions,
    CommandKind::CompressNow,
    CommandKind::CompressEach,
];

fn module_dir() -> Option<PathBuf> {
    let mut buffer = [0u16; 32768];
    let length = unsafe { GetModuleFileNameW(DLL_MODULE, &mut buffer) } as usize;
    if length == 0 {
        return None;
    }
    let path = PathBuf::from(OsString::from_wide(&buffer[..length]));
    path.parent().map(|p| p.to_path_buf())
}

/// 패키지 안의 PackNine.exe 경로. DLL과 같은 폴더에 있다.
fn packnine_exe() -> Option<PathBuf> {
    let candidate = module_dir()?.join("PackNine.exe");
    candidate.is_file().then_some(candidate)
}

/// 선택된 항목들의 파일 시스템 경로를 모은다.
fn selected_paths(items: Option<&IShellItemArray>) -> Vec<String> {
    let Some(items) = items else {
        return Vec::new();
    };
    let mut paths = Vec::new();
    unsafe {
        let Ok(count) = items.GetCount() else {
            return paths;
        };
        for index in 0..count {
            let Ok(item) = items.GetItemAt(index) else {
                continue;
            };
            // SIGDN_FILESYSPATH는 실제 디스크 경로만 돌려준다(가상 항목은 실패 → 건너뜀).
            let Ok(wide) = item.GetDisplayName(SIGDN_FILESYSPATH) else {
                continue;
            };
            if let Ok(text) = wide.to_string() {
                paths.push(text);
            }
            CoTaskMemFree(Some(wide.0 as *const core::ffi::c_void));
        }
    }
    paths
}

#[implement(IExplorerCommand)]
struct PackNineCommand(CommandKind);

impl PackNineCommand {
    fn new(kind: CommandKind) -> Self {
        OBJECT_COUNT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        Self(kind)
    }
}

impl Drop for PackNineCommand {
    fn drop(&mut self) {
        OBJECT_COUNT.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
    }
}

impl IExplorerCommand_Impl for PackNineCommand_Impl {
    fn GetTitle(&self, _items: Option<&IShellItemArray>) -> Result<PWSTR> {
        // 반환 문자열은 탐색기가 CoTaskMemFree로 해제하므로 SHStrDupW로 할당해야 한다.
        unsafe { SHStrDupW(self.0.title()) }
    }

    fn GetIcon(&self, _items: Option<&IShellItemArray>) -> Result<PWSTR> {
        // 아이콘은 exe에 내장된 첫 번째 것을 쓴다(묶음과 하위 항목 모두 동일).
        let Some(exe) = packnine_exe() else {
            return Err(Error::from(E_NOTIMPL));
        };
        let spec: Vec<u16> = format!("{},0", exe.display())
            .encode_utf16()
            .chain(std::iter::once(0))
            .collect();
        unsafe { SHStrDupW(PCWSTR(spec.as_ptr())) }
    }

    fn GetToolTip(&self, _items: Option<&IShellItemArray>) -> Result<PWSTR> {
        // 툴팁 없음. E_NOTIMPL을 주면 탐색기가 알아서 생략한다.
        Err(Error::from(E_NOTIMPL))
    }

    fn GetCanonicalName(&self) -> Result<GUID> {
        Ok(CLSID_PACKNINE_COMPRESS)
    }

    fn GetState(&self, items: Option<&IShellItemArray>, _slow: BOOL) -> Result<u32> {
        // 실제 경로가 없거나(가상 폴더 등) 선택 내용에 맞지 않는 항목은 숨긴다.
        if should_show(self.0, &selected_paths(items)) {
            Ok(ECS_ENABLED.0 as u32)
        } else {
            Ok(ECS_HIDDEN.0 as u32)
        }
    }

    fn Invoke(&self, items: Option<&IShellItemArray>, _ctx: Option<&IBindCtx>) -> Result<()> {
        let paths = selected_paths(items);
        if paths.is_empty() {
            return Ok(());
        }
        // 미리보기는 프로그램을 띄우지 않고 DLL이 직접 가벼운 창을 연다.
        // PackNine.exe를 실행하면 "열기"와 다를 게 없고, 단일 exe라 실행마다
        // 임시 폴더에 풀리느라 수 초가 걸려 "미리"보기가 되지 않는다.
        if self.0 == CommandKind::Preview {
            for path in &paths {
                popup::show_preview_window(std::path::PathBuf::from(path));
            }
            return Ok(());
        }

        let Some(exe) = packnine_exe() else {
            return Err(Error::from(E_FAIL));
        };

        // 탐색기 프로세스를 붙잡지 않도록 띄우기만 하고 기다리지 않는다.
        std::process::Command::new(exe)
            .args(self.0.arguments())
            .args(&paths)
            .spawn()
            .map_err(|_| Error::from(E_FAIL))?;
        Ok(())
    }

    fn GetFlags(&self) -> Result<u32> {
        if self.0.has_subcommands() {
            Ok(ECF_HASSUBCOMMANDS.0 as u32)
        } else {
            Ok(ECF_DEFAULT.0 as u32)
        }
    }

    fn EnumSubCommands(&self) -> Result<IEnumExplorerCommand> {
        if !self.0.has_subcommands() {
            return Err(Error::from(E_NOTIMPL));
        }
        let commands: Vec<IExplorerCommand> = SUB_COMMANDS
            .iter()
            .map(|kind| PackNineCommand::new(*kind).into())
            .collect();
        Ok(SubCommandEnum::new(commands).into())
    }
}

#[implement(IEnumExplorerCommand)]
struct SubCommandEnum {
    commands: Vec<IExplorerCommand>,
    position: Cell<usize>,
}

impl SubCommandEnum {
    fn new(commands: Vec<IExplorerCommand>) -> Self {
        OBJECT_COUNT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        Self {
            commands,
            position: Cell::new(0),
        }
    }
}

impl Drop for SubCommandEnum {
    fn drop(&mut self) {
        OBJECT_COUNT.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
    }
}

impl IEnumExplorerCommand_Impl for SubCommandEnum_Impl {
    fn Next(
        &self,
        celt: u32,
        pucelt: *mut Option<IExplorerCommand>,
        pceltfetched: *mut u32,
    ) -> HRESULT {
        let mut fetched = 0u32;
        let start = self.position.get();
        for offset in 0..celt as usize {
            let Some(command) = self.commands.get(start + offset) else {
                break;
            };
            unsafe { *pucelt.add(offset) = Some(command.clone()) };
            fetched += 1;
        }
        self.position.set(start + fetched as usize);
        if !pceltfetched.is_null() {
            unsafe { *pceltfetched = fetched };
        }
        if fetched == celt {
            S_OK
        } else {
            S_FALSE
        }
    }

    fn Skip(&self, celt: u32) -> Result<()> {
        self.position.set(self.position.get() + celt as usize);
        Ok(())
    }

    fn Reset(&self) -> Result<()> {
        self.position.set(0);
        Ok(())
    }

    fn Clone(&self) -> Result<IEnumExplorerCommand> {
        // 현재 위치까지 함께 복제해야 열거 상태가 어긋나지 않는다.
        let copy = SubCommandEnum::new(self.commands.clone());
        copy.position.set(self.position.get());
        Ok(copy.into())
    }
}

/// 이 팩토리가 만들어 줄 객체 종류.
#[derive(Clone, Copy)]
enum FactoryKind {
    /// 우클릭 메뉴 핸들러.
    ContextMenu,
    /// 탐색기 미리보기 창 핸들러.
    Preview,
}

#[implement(IClassFactory)]
struct CommandFactory(FactoryKind);

impl IClassFactory_Impl for CommandFactory_Impl {
    fn CreateInstance(
        &self,
        outer: Option<&IUnknown>,
        iid: *const GUID,
        object: *mut *mut core::ffi::c_void,
    ) -> Result<()> {
        if outer.is_some() {
            return Err(Error::from(CLASS_E_NOAGGREGATION));
        }
        match self.0 {
            FactoryKind::ContextMenu => {
                // 탐색기가 만드는 것은 언제나 묶음(루트)이고, 하위 항목은 EnumSubCommands가 준다.
                let command: IExplorerCommand = PackNineCommand::new(CommandKind::Root).into();
                unsafe { command.query(iid, object).ok() }
            }
            FactoryKind::Preview => {
                let handler: IPreviewHandler = preview::ArchivePreviewHandler::new().into();
                unsafe { handler.query(iid, object).ok() }
            }
        }
    }

    fn LockServer(&self, lock: BOOL) -> Result<()> {
        if lock.as_bool() {
            OBJECT_COUNT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        } else {
            OBJECT_COUNT.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
        }
        Ok(())
    }
}

/// COM 런타임이 클래스 팩토리를 요청할 때 호출한다.
#[no_mangle]
pub unsafe extern "system" fn DllGetClassObject(
    clsid: *const GUID,
    iid: *const GUID,
    object: *mut *mut core::ffi::c_void,
) -> HRESULT {
    if clsid.is_null() || iid.is_null() || object.is_null() {
        return E_INVALIDARG;
    }
    let kind = if *clsid == CLSID_PACKNINE_COMPRESS {
        FactoryKind::ContextMenu
    } else if *clsid == preview::CLSID_PACKNINE_PREVIEW {
        FactoryKind::Preview
    } else {
        return CLASS_E_CLASSNOTAVAILABLE;
    };
    let factory: IClassFactory = CommandFactory(kind).into();
    factory.query(iid, object)
}

/// 살아 있는 객체가 없으면 탐색기가 DLL을 내려도 된다고 알린다.
#[no_mangle]
pub extern "system" fn DllCanUnloadNow() -> HRESULT {
    if OBJECT_COUNT.load(std::sync::atomic::Ordering::Relaxed) == 0 {
        S_OK
    } else {
        S_FALSE
    }
}

#[no_mangle]
pub extern "system" fn DllMain(
    module: HMODULE,
    reason: u32,
    _reserved: *mut core::ffi::c_void,
) -> BOOL {
    const DLL_PROCESS_ATTACH: u32 = 1;
    if reason == DLL_PROCESS_ATTACH {
        unsafe { DLL_MODULE = module };
    }
    TRUE
}

#[cfg(test)]
mod menu_tests {
    use super::*;

    fn paths(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn archive_detection_by_extension() {
        assert!(is_archive(r"C:\a\b.zip"));
        assert!(is_archive(r"C:\a\b.7z"));
        assert!(is_archive(r"C:\a\b.ZIP"));
        // 분할 압축 첫 볼륨도 압축 파일로 본다.
        assert!(is_archive(r"C:\a\b.zip.001"));
        assert!(!is_archive(r"C:\a\b.txt"));
        assert!(!is_archive(r"C:\a\확장자없음"));
    }

    #[test]
    fn each_compress_hidden_for_single_selection() {
        // 하나만 고르면 "각각 압축하기"는 "바로 압축하기"와 결과가 같아 혼란만 준다.
        assert!(!should_show(CommandKind::CompressEach, &paths(&[r"C:\a\only.txt"])));
        assert!(should_show(
            CommandKind::CompressEach,
            &paths(&[r"C:\a\one.txt", r"C:\a\two.txt"])
        ));
    }

    #[test]
    fn extract_commands_only_for_archives() {
        let archive = paths(&[r"C:\a\pack.zip"]);
        let document = paths(&[r"C:\a\memo.txt"]);

        for kind in [CommandKind::Preview, CommandKind::ExtractSmart, CommandKind::ExtractHere] {
            assert!(should_show(kind, &archive));
            assert!(!should_show(kind, &document));
        }
    }

    #[test]
    fn extract_hidden_when_selection_is_mixed() {
        // 압축 파일과 일반 파일을 섞어 고르면 "풀기"가 무엇을 뜻하는지 모호하다.
        let mixed = paths(&[r"C:\a\pack.zip", r"C:\a\memo.txt"]);

        assert!(!should_show(CommandKind::ExtractSmart, &mixed));
        // 반면 압축은 섞여 있어도 말이 된다.
        assert!(should_show(CommandKind::CompressWithOptions, &mixed));
    }

    #[test]
    fn compress_available_even_for_archives() {
        // 압축 파일을 다시 압축하는 것도 정상적인 요구다.
        let archive = paths(&[r"C:\a\pack.zip"]);

        assert!(should_show(CommandKind::CompressWithOptions, &archive));
        assert!(should_show(CommandKind::CompressNow, &archive));
    }

    #[test]
    fn nothing_shows_without_real_paths() {
        for kind in [
            CommandKind::Root,
            CommandKind::Preview,
            CommandKind::CompressNow,
            CommandKind::CompressEach,
        ] {
            assert!(!should_show(kind, &[]));
        }
    }
}
