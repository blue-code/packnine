//! 우클릭 "미리보기"가 띄우는 가벼운 목록 창.
//!
//! 왜 별도 창인가: PackNine.exe를 띄우면 "열기"와 다를 게 없고, PyInstaller 단일 exe라
//! 실행마다 임시 폴더에 풀려서 수 초가 걸린다. 미리보기는 "지금 바로" 보여야 의미가
//! 있으므로, DLL이 직접 창을 만들어 즉시 목록을 그린다. 프로세스를 새로 띄우지 않으니
//! 체감 지연이 없다.
//!
//! 목록 문자열은 미리보기 창 핸들러(preview.rs)와 같은 함수를 쓴다. 표시 방식만 다를 뿐
//! 내용은 동일해야 하기 때문이다.
//!
//! 창은 별도 스레드에서 만들고 그 스레드가 메시지 루프를 돈다. 탐색기 스레드를 붙잡으면
//! 우클릭 메뉴가 멈춘 것처럼 보이기 때문이다. 창이 살아 있는 동안에는 DLL이 내려가지
//! 않도록 객체 수를 올려둔다.

use std::path::PathBuf;

use windows::core::*;
use windows::Win32::Foundation::*;
use windows::Win32::Graphics::Gdi::*;
use windows::Win32::UI::Input::KeyboardAndMouse::VK_ESCAPE;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::WindowsAndMessaging::*;

use crate::preview::preview_text;

const WINDOW_CLASS: PCWSTR = w!("PackNinePreviewPopup");
const EDIT_ID: isize = 1001;

/// 압축 파일 목록을 보여주는 창을 띄운다. 호출 즉시 반환한다(창은 별도 스레드가 돌린다).
pub fn show_preview_window(path: PathBuf) {
    crate::object_added();
    std::thread::spawn(move || {
        run_window(path);
        crate::object_removed();
    });
}

fn register_class(instance: HINSTANCE) {
    // 같은 이름으로 두 번 등록하면 실패하지만, 실패해도 CreateWindow는 기존 클래스를 쓴다.
    let class = WNDCLASSW {
        lpfnWndProc: Some(window_proc),
        hInstance: instance,
        lpszClassName: WINDOW_CLASS,
        hCursor: unsafe { LoadCursorW(None, IDC_ARROW).unwrap_or_default() },
        hbrBackground: HBRUSH((COLOR_WINDOW.0 + 1) as isize as *mut _),
        ..Default::default()
    };
    unsafe { RegisterClassW(&class) };
}

fn run_window(path: PathBuf) {
    let body = preview_text(&path);
    let title: Vec<u16> = format!(
        "{} - PackNine 미리보기",
        path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default()
    )
    .encode_utf16()
    .chain(std::iter::once(0))
    .collect();

    let Ok(module) = (unsafe { GetModuleHandleW(None) }) else {
        return;
    };
    let instance = HINSTANCE(module.0);
    register_class(instance);

    // 화면 가운데에 띄운다. 작업 표시줄을 제외한 영역 기준.
    let (width, height) = (720, 560);
    let screen_w = unsafe { GetSystemMetrics(SM_CXSCREEN) };
    let screen_h = unsafe { GetSystemMetrics(SM_CYSCREEN) };
    let x = (screen_w - width) / 2;
    let y = (screen_h - height) / 2;

    let window = unsafe {
        CreateWindowExW(
            WS_EX_APPWINDOW,
            WINDOW_CLASS,
            PCWSTR(title.as_ptr()),
            WS_OVERLAPPEDWINDOW,
            x,
            y,
            width,
            height,
            None,
            None,
            instance,
            None,
        )
    };
    let Ok(window) = window else {
        return;
    };

    // 목록을 담을 읽기 전용 EDIT. 스크롤·선택·복사를 셸이 처리해준다.
    let mut text: Vec<u16> = body.encode_utf16().collect();
    text.push(0);
    let edit = unsafe {
        CreateWindowExW(
            WINDOW_EX_STYLE(0),
            w!("EDIT"),
            PCWSTR(text.as_ptr()),
            WS_CHILD
                | WS_VISIBLE
                | WS_VSCROLL
                | WS_HSCROLL
                | WINDOW_STYLE(ES_MULTILINE as u32)
                | WINDOW_STYLE(ES_READONLY as u32),
            0,
            0,
            width,
            height,
            window,
            HMENU(EDIT_ID as *mut _),
            instance,
            None,
        )
    };

    if let Ok(edit) = edit {
        // 기본 글꼴은 옛 비트맵 글꼴이라 한글이 보기 나쁘다. 시스템 UI 글꼴로 바꾼다.
        let font = unsafe { GetStockObject(DEFAULT_GUI_FONT) };
        unsafe {
            SendMessageW(
                edit,
                WM_SETFONT,
                WPARAM(font.0 as usize),
                LPARAM(1),
            )
        };
    }

    unsafe {
        let _ = ShowWindow(window, SW_SHOWNORMAL);
        let _ = SetForegroundWindow(window);
    }

    let mut message = MSG::default();
    while unsafe { GetMessageW(&mut message, None, 0, 0) }.as_bool() {
        unsafe {
            let _ = TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }
}

extern "system" fn window_proc(
    window: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match message {
        WM_SIZE => {
            // 창 크기에 맞춰 목록도 늘린다.
            let edit = unsafe { GetDlgItem(window, EDIT_ID as i32) };
            if let Ok(edit) = edit {
                let width = (lparam.0 & 0xFFFF) as i32;
                let height = ((lparam.0 >> 16) & 0xFFFF) as i32;
                unsafe { let _ = MoveWindow(edit, 0, 0, width, height, TRUE); }
            }
            LRESULT(0)
        }
        WM_KEYDOWN if wparam.0 == VK_ESCAPE.0 as usize => {
            // Esc로 닫히는 편이 미리보기답다.
            unsafe { let _ = DestroyWindow(window); }
            LRESULT(0)
        }
        WM_DESTROY => {
            unsafe { PostQuitMessage(0) };
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(window, message, wparam, lparam) },
    }
}
