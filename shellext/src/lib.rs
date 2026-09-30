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
//! 하는 일은 하나뿐이다: 선택된 경로들을 모아 `PackNine.exe compress-dialog`를 실행한다.
//! 압축 로직은 전부 파이썬 쪽에 있고, 여기서는 아무 파일도 읽거나 쓰지 않는다 - 탐색기
//! 프로세스 안에서 도는 코드이므로 최대한 얇게 유지해 장애 지점을 줄인다.

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
struct CompressCommand;

impl CompressCommand {
    fn new() -> Self {
        OBJECT_COUNT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        Self
    }
}

impl Drop for CompressCommand {
    fn drop(&mut self) {
        OBJECT_COUNT.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
    }
}

impl IExplorerCommand_Impl for CompressCommand_Impl {
    fn GetTitle(&self, _items: Option<&IShellItemArray>) -> Result<PWSTR> {
        // 반환 문자열은 탐색기가 CoTaskMemFree로 해제하므로 SHStrDupW로 할당해야 한다.
        unsafe { SHStrDupW(w!("PackNine으로 압축하기")) }
    }

    fn GetIcon(&self, _items: Option<&IShellItemArray>) -> Result<PWSTR> {
        // 아이콘은 exe에 내장된 첫 번째 것을 쓴다.
        let Some(exe) = packnine_exe() else {
            return Err(Error::empty());
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
        // 실제 경로가 하나도 없으면(가상 폴더 등) 메뉴를 숨긴다.
        if selected_paths(items).is_empty() {
            Ok(ECS_HIDDEN.0 as u32)
        } else {
            Ok(ECS_ENABLED.0 as u32)
        }
    }

    fn Invoke(&self, items: Option<&IShellItemArray>, _ctx: Option<&IBindCtx>) -> Result<()> {
        let paths = selected_paths(items);
        if paths.is_empty() {
            return Ok(());
        }
        let Some(exe) = packnine_exe() else {
            return Err(Error::from(E_FAIL));
        };

        // 탐색기 프로세스를 붙잡지 않도록 띄우기만 하고 기다리지 않는다.
        // compress-dialog는 인자로 받은 경로 전부를 한 창에 담는다(다중 선택도 창 하나).
        std::process::Command::new(exe)
            .arg("compress-dialog")
            .arg("--no-collect")
            .args(&paths)
            .spawn()
            .map_err(|_| Error::from(E_FAIL))?;
        Ok(())
    }

    fn GetFlags(&self) -> Result<u32> {
        Ok(ECF_DEFAULT.0 as u32)
    }

    fn EnumSubCommands(&self) -> Result<IEnumExplorerCommand> {
        // 하위 메뉴 없음.
        Err(Error::from(E_NOTIMPL))
    }
}

#[implement(IClassFactory)]
struct CommandFactory;

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
        let command: IExplorerCommand = CompressCommand::new().into();
        unsafe { command.query(iid, object).ok() }
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
    if *clsid != CLSID_PACKNINE_COMPRESS {
        return CLASS_E_CLASSNOTAVAILABLE;
    }
    let factory: IClassFactory = CommandFactory.into();
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
pub extern "system" fn DllMain(module: HMODULE, reason: u32, _reserved: *mut core::ffi::c_void) -> BOOL {
    const DLL_PROCESS_ATTACH: u32 = 1;
    if reason == DLL_PROCESS_ATTACH {
        unsafe { DLL_MODULE = module };
    }
    TRUE
}
