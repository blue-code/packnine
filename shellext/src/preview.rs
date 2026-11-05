//! 탐색기 미리보기 창에 압축 파일 내용을 보여주는 핸들러(IPreviewHandler).
//!
//! 탐색기에서 zip 파일을 고르면 오른쪽 미리보기 창에 안에 든 파일 목록이 뜬다.
//! 미리보기 핸들러는 탐색기가 아니라 별도 호스트 프로세스(prevhost.exe)에서 돌아가므로,
//! 여기서 죽어도 탐색기는 영향을 받지 않는다. 그래도 목록 읽기 실패는 전부 잡아서
//! 안내 문구로 바꾼다 - 빈 창보다 이유를 보여주는 편이 낫다.
//!
//! 목록은 zip 크레이트로 읽는다. 포맷을 직접 파싱하지 않고 검증된 구현에 맡긴다는
//! 원칙(SECURITY.md 6번)은 Rust 쪽에도 그대로 적용한다. 7z/rar/tar는 이 DLL에서
//! 읽지 않고 "PackNine에서 열어보세요" 안내만 띄운다 - 미리보기 하나를 위해 압축 포맷
//! 구현을 파이썬과 Rust 양쪽에 늘리지 않기 위한 선택이다.
//!
//! 그리기는 직접 하지 않고 읽기 전용 EDIT 컨트롤에 텍스트를 넣는다. 스크롤과 글꼴
//! 처리를 셸에 맡길 수 있어 코드가 훨씬 적고 장애 지점도 적다.

use std::cell::{Cell, RefCell};
use std::fs::File;
use std::path::{Path, PathBuf};

use windows::core::*;
use windows::Win32::Foundation::*;
use windows::Win32::System::Ole::{IObjectWithSite, IObjectWithSite_Impl};
use windows::Win32::UI::Input::KeyboardAndMouse::{GetFocus, SetFocus as SetWindowFocus};
use windows::Win32::UI::Shell::PropertiesSystem::*;
use windows::Win32::UI::Shell::*;
use windows::Win32::UI::WindowsAndMessaging::*;

/// 미리보기 핸들러의 CLSID. 매니페스트의 DesktopPreviewHandler 값과 일치해야 한다.
pub const CLSID_PACKNINE_PREVIEW: GUID = GUID::from_u128(0xd400f75f_2a57_4259_b4fc_9af59272afe8);

/// 목록에 표시할 최대 항목 수. 수만 개짜리 아카이브에서 미리보기가 느려지지 않게 한다.
const MAX_ENTRIES: usize = 500;

fn format_size(bytes: u64) -> String {
    const UNITS: [&str; 4] = ["B", "KB", "MB", "GB"];
    let mut value = bytes as f64;
    let mut unit = 0;
    while value >= 1024.0 && unit < UNITS.len() - 1 {
        value /= 1024.0;
        unit += 1;
    }
    if unit == 0 {
        format!("{} {}", bytes, UNITS[0])
    } else {
        format!("{:.1} {}", value, UNITS[unit])
    }
}

/// zip 파일의 내용을 사람이 읽을 수 있는 목록 문자열로 만든다.
fn zip_listing(path: &Path) -> std::result::Result<String, String> {
    let file = File::open(path).map_err(|e| format!("파일을 열 수 없습니다: {e}"))?;
    let mut archive =
        zip::ZipArchive::new(file).map_err(|e| format!("압축 파일을 읽을 수 없습니다: {e}"))?;

    let total = archive.len();
    let mut text = String::new();
    let mut total_size = 0u64;
    let mut shown = 0usize;

    for index in 0..total {
        let Ok(entry) = archive.by_index(index) else {
            continue;
        };
        if entry.is_dir() {
            continue;
        }
        total_size += entry.size();
        if shown < MAX_ENTRIES {
            text.push_str(&format!("{}\r\n    {}\r\n", entry.name(), format_size(entry.size())));
            shown += 1;
        }
    }

    let mut header = format!(
        "{}\r\n파일 {}개 · 원본 크기 {}\r\n{}\r\n\r\n",
        path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(),
        shown,
        format_size(total_size),
        "-".repeat(40),
    );
    header.push_str(&text);
    if shown >= MAX_ENTRIES {
        header.push_str("\r\n… 이하 생략 — 전체 목록은 PackNine에서 열어 확인하세요\r\n");
    }
    Ok(header)
}

/// 우클릭 메뉴를 그리는 동안 목록 읽기에 쓸 수 있는 최대 시간.
///
/// 탐색기는 하위 메뉴를 만드는 동안 사용자를 세워 놓는다. 여기서 오래 끌면 메뉴가
/// "로드하는 중"에서 영영 돌아오지 않는다.
///
/// 실제로 겪은 사례: 7.29GB짜리 ZIP64 아카이브 하나에서 목록 읽기에 200초가 걸렸다.
/// 원인은 zip 크레이트의 엄격한 검사와 그 뒤의 되감기다. 그 파일의 ZIP64 EOCD는
/// version_made_by=20, version_needed_to_extract=45로 적혀 있는데(이렇게 쓰는 도구가
/// 흔하다), 크레이트는 "만든 버전보다 높은 버전을 요구한다"며 거절한다. 그러면
/// get_metadata가 EOCD 후보를 다시 찾겠다고 파일 끝에서 앞쪽으로 7.29GB 전체를
/// 훑어 내려간다. 우리가 고칠 수 있는 건 크레이트의 판단이 아니라 "메뉴를 그리다
/// 말고 무한정 기다리는 구조" 쪽이다.
///
/// 미리보기는 어디까지나 덤이다. 제때 못 읽으면 조용히 접고 동작 항목만 보여주는
/// 편이, 메뉴 전체를 못 쓰게 만드는 것보다 낫다.
const LISTING_BUDGET: std::time::Duration = std::time::Duration::from_millis(120);

/// 탐색기 미리보기 창에서 목록 읽기에 허용할 최대 시간.
/// 메뉴와 달리 사용자가 클릭해서 들어온 자리라 조금 더 기다려도 되지만, 무한정은 아니다.
const PREVIEW_BUDGET: std::time::Duration = std::time::Duration::from_secs(3);

/// 제한 시간을 넘겨 미리보기를 접은 아카이브들. 같은 파일을 다시 우클릭할 때
/// 또 몇 분짜리 읽기를 시작하지 않도록 기억해 둔다(읽던 스레드는 백그라운드에서
/// 알아서 끝나지만, 우클릭할 때마다 새로 띄우면 디스크만 계속 긁는다).
static SLOW_ARCHIVES: std::sync::Mutex<Option<Vec<PathBuf>>> = std::sync::Mutex::new(None);

fn is_known_slow(path: &Path) -> bool {
    match SLOW_ARCHIVES.lock() {
        Ok(guard) => guard
            .as_ref()
            .is_some_and(|list| list.iter().any(|known| known.as_path() == path)),
        Err(_) => false,
    }
}

fn remember_slow(path: &Path) {
    if let Ok(mut guard) = SLOW_ARCHIVES.lock() {
        let list = guard.get_or_insert_with(Vec::new);
        if !list.iter().any(|known| known.as_path() == path) {
            // 메뉴 한 번에 기억할 양은 적다. 무한히 쌓이지 않게 앞쪽부터 버린다.
            if list.len() >= 32 {
                list.remove(0);
            }
            list.push(path.to_path_buf());
        }
    }
}

/// 아카이브 안의 파일 목록을 (내부 경로, 크기)로 돌려준다. 메뉴에 올릴 때 쓴다.
///
/// 제한 시간 안에 못 읽으면 None을 돌려준다. 호출부는 None을 "미리보기 없음"으로
/// 받아들이고 메뉴를 즉시 완성해야 한다.
pub(crate) fn zip_entries(path: &Path, limit: usize) -> Option<Vec<(String, u64)>> {
    if !path.extension().is_some_and(|e| e.eq_ignore_ascii_case("zip")) {
        return None;
    }
    if is_known_slow(path) {
        return None;
    }

    // 읽기는 따로 떼어 보내고 제한 시간만 기다린다. 늦게 끝나는 스레드는 결과를
    // 버리고 조용히 사라진다(셸은 이미 메뉴를 다 그린 뒤다).
    let (sender, receiver) = std::sync::mpsc::channel();
    let target = path.to_path_buf();
    std::thread::spawn(move || {
        let _ = sender.send(read_entries(&target, limit));
    });

    match receiver.recv_timeout(LISTING_BUDGET) {
        Ok(entries) => entries,
        Err(_) => {
            remember_slow(path);
            None
        }
    }
}

fn read_entries(path: &Path, limit: usize) -> Option<Vec<(String, u64)>> {
    let file = File::open(path).ok()?;
    let mut archive = zip::ZipArchive::new(file).ok()?;
    let mut entries = Vec::new();
    for index in 0..archive.len() {
        // raw로 읽는 이유: by_index는 암호가 걸린 엔트리에서 실패해 암호 zip은
        // 목록이 통째로 비어 버린다. 메뉴에 필요한 이름·크기는 중앙 디렉터리에
        // 평문으로 적혀 있으므로 복호화 없이 읽는 쪽이 맞고 더 빠르다.
        let Ok(entry) = archive.by_index_raw(index) else {
            continue;
        };
        if entry.is_dir() {
            continue;
        }
        entries.push((entry.name().to_string(), entry.size()));
        if entries.len() >= limit {
            break;
        }
    }
    Some(entries)
}

/// 아카이브 안의 파일 하나를 임시 폴더에 꺼내고 그 경로를 돌려준다.
pub(crate) fn extract_one(archive: &Path, name: &str) -> Option<PathBuf> {
    let file = File::open(archive).ok()?;
    let mut zip = zip::ZipArchive::new(file).ok()?;
    let mut entry = zip.by_name(name).ok()?;

    let target_dir = std::env::temp_dir().join("PackNinePreview");
    std::fs::create_dir_all(&target_dir).ok()?;
    // 내부 폴더 구조는 버리고 파일 이름만 쓴다(경로 탈출 위험을 원천 차단).
    let file_name = Path::new(name).file_name()?;
    let target = target_dir.join(file_name);
    let mut out = File::create(&target).ok()?;
    std::io::copy(&mut entry, &mut out).ok()?;
    Some(target)
}

pub(crate) fn format_entry_size(bytes: u64) -> String {
    format_size(bytes)
}

/// 미리보기 창에 넣을 본문을 만든다. 실패해도 문자열을 돌려준다(빈 창 방지).
pub(crate) fn preview_text(path: &Path) -> String {
    let extension = path
        .extension()
        .map(|e| e.to_string_lossy().to_ascii_lowercase())
        .unwrap_or_default();

    if extension != "zip" {
        return format!(
            "{}\r\n\r\n이 형식은 미리보기를 지원하지 않습니다.\r\n\
             PackNine에서 열면 내용을 볼 수 있습니다.\r\n",
            path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(),
        );
    }

    // 미리보기 창은 별도 프로세스(prevhost.exe)에서 돌지만, 여기서 몇 분씩 붙잡히면
    // 탐색기의 미리보기 칸이 그대로 굳는다. 메뉴보다는 여유를 주되 상한은 둔다.
    let (sender, receiver) = std::sync::mpsc::channel();
    let target = path.to_path_buf();
    std::thread::spawn(move || {
        let _ = sender.send(zip_listing(&target));
    });

    match receiver.recv_timeout(PREVIEW_BUDGET) {
        Ok(Ok(text)) => text,
        Ok(Err(message)) => format!("{message}\r\n"),
        Err(_) => format!(
            "{}\r\n\r\n목록을 읽는 데 너무 오래 걸려 미리보기를 건너뛰었습니다.\r\n\
             PackNine에서 열면 내용을 볼 수 있습니다.\r\n",
            path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(),
        ),
    }
}

#[implement(IPreviewHandler, IInitializeWithFile, IObjectWithSite, IPreviewHandlerVisuals)]
pub struct ArchivePreviewHandler {
    path: RefCell<Option<PathBuf>>,
    parent: Cell<isize>,
    child: Cell<isize>,
    rect: RefCell<RECT>,
    site: RefCell<Option<IUnknown>>,
    background: Cell<u32>,
    text_color: Cell<u32>,
}

impl ArchivePreviewHandler {
    pub fn new() -> Self {
        crate::object_added();
        Self {
            path: RefCell::new(None),
            parent: Cell::new(0),
            child: Cell::new(0),
            rect: RefCell::new(RECT::default()),
            site: RefCell::new(None),
            // 기본값은 시스템 창 색. SetBackgroundColor가 오면 덮어쓴다.
            background: Cell::new(0x00FFFFFF),
            text_color: Cell::new(0x00000000),
        }
    }

    fn destroy_child(&self) {
        let child = self.child.get();
        if child != 0 {
            unsafe { let _ = DestroyWindow(HWND(child as *mut _)); }
            self.child.set(0);
        }
    }
}

impl Drop for ArchivePreviewHandler {
    fn drop(&mut self) {
        self.destroy_child();
        crate::object_removed();
    }
}

impl IInitializeWithFile_Impl for ArchivePreviewHandler_Impl {
    fn Initialize(&self, file_path: &PCWSTR, _mode: u32) -> Result<()> {
        let text = unsafe { file_path.to_string() }.map_err(|_| Error::from(E_INVALIDARG))?;
        *self.path.borrow_mut() = Some(PathBuf::from(text));
        Ok(())
    }
}

impl IObjectWithSite_Impl for ArchivePreviewHandler_Impl {
    fn SetSite(&self, site: Option<&IUnknown>) -> Result<()> {
        *self.site.borrow_mut() = site.cloned();
        Ok(())
    }

    fn GetSite(&self, iid: *const GUID, object: *mut *mut core::ffi::c_void) -> Result<()> {
        let site = self.site.borrow();
        match site.as_ref() {
            Some(unknown) => unsafe { unknown.query(iid, object).ok() },
            None => Err(Error::from(E_FAIL)),
        }
    }
}

impl IPreviewHandlerVisuals_Impl for ArchivePreviewHandler_Impl {
    fn SetBackgroundColor(&self, color: COLORREF) -> Result<()> {
        self.background.set(color.0);
        Ok(())
    }

    fn SetFont(&self, _font: *const windows::Win32::Graphics::Gdi::LOGFONTW) -> Result<()> {
        // 글꼴은 EDIT 컨트롤 기본값을 쓴다.
        Ok(())
    }

    fn SetTextColor(&self, color: COLORREF) -> Result<()> {
        self.text_color.set(color.0);
        Ok(())
    }
}

impl IPreviewHandler_Impl for ArchivePreviewHandler_Impl {
    fn SetWindow(&self, hwnd: HWND, rect: *const RECT) -> Result<()> {
        self.parent.set(hwnd.0 as isize);
        if !rect.is_null() {
            *self.rect.borrow_mut() = unsafe { *rect };
        }
        let child = self.child.get();
        if child != 0 {
            let r = *self.rect.borrow();
            unsafe {
                let _ = SetParent(HWND(child as *mut _), hwnd);
                let _ = MoveWindow(
                    HWND(child as *mut _),
                    r.left,
                    r.top,
                    r.right - r.left,
                    r.bottom - r.top,
                    TRUE,
                );
            }
        }
        Ok(())
    }

    fn SetRect(&self, rect: *const RECT) -> Result<()> {
        if rect.is_null() {
            return Err(Error::from(E_INVALIDARG));
        }
        *self.rect.borrow_mut() = unsafe { *rect };
        let child = self.child.get();
        if child != 0 {
            let r = *self.rect.borrow();
            unsafe {
                let _ = MoveWindow(
                    HWND(child as *mut _),
                    r.left,
                    r.top,
                    r.right - r.left,
                    r.bottom - r.top,
                    TRUE,
                );
            }
        }
        Ok(())
    }

    fn DoPreview(&self) -> Result<()> {
        let parent = self.parent.get();
        if parent == 0 {
            return Err(Error::from(E_FAIL));
        }
        self.destroy_child();

        let path = self.path.borrow().clone();
        let body = match path.as_deref() {
            Some(p) => preview_text(p),
            None => "미리볼 파일이 지정되지 않았습니다.\r\n".to_string(),
        };

        let mut wide: Vec<u16> = body.encode_utf16().collect();
        wide.push(0);
        let rect = *self.rect.borrow();

        // 읽기 전용 EDIT 컨트롤에 맡기면 스크롤·선택·글꼴을 셸이 알아서 처리한다.
        let child = unsafe {
            CreateWindowExW(
                WINDOW_EX_STYLE(0),
                w!("EDIT"),
                PCWSTR(wide.as_ptr()),
                WS_CHILD
                    | WS_VISIBLE
                    | WS_VSCROLL
                    | WINDOW_STYLE(ES_MULTILINE as u32)
                    | WINDOW_STYLE(ES_READONLY as u32),
                rect.left,
                rect.top,
                rect.right - rect.left,
                rect.bottom - rect.top,
                HWND(parent as *mut _),
                None,
                None,
                None,
            )
        }
        .map_err(|_| Error::from(E_FAIL))?;

        self.child.set(child.0 as isize);
        Ok(())
    }

    fn Unload(&self) -> Result<()> {
        self.destroy_child();
        *self.path.borrow_mut() = None;
        Ok(())
    }

    fn SetFocus(&self) -> Result<()> {
        let child = self.child.get();
        if child != 0 {
            unsafe { let _ = SetWindowFocus(HWND(child as *mut _)); }
        }
        Ok(())
    }

    fn QueryFocus(&self) -> Result<HWND> {
        let focused = unsafe { GetFocus() };
        Ok(focused)
    }

    fn TranslateAccelerator(&self, _msg: *const MSG) -> Result<()> {
        // 단축키를 가로채지 않는다. S_FALSE를 돌려주면 호스트가 알아서 처리한다.
        Err(Error::from(S_FALSE))
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    /// 테스트용 zip을 임시 폴더에 만든다.
    fn make_zip(name: &str, entries: &[(&str, usize)]) -> PathBuf {
        let path = std::env::temp_dir().join(name);
        let file = File::create(&path).unwrap();
        let mut writer = zip::ZipWriter::new(file);
        let options: zip::write::FileOptions<'_, ()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (entry_name, size) in entries {
            writer.start_file(*entry_name, options).unwrap();
            writer.write_all(&vec![b'A'; *size]).unwrap();
        }
        writer.finish().unwrap();
        path
    }

    #[test]
    fn entries_are_listed_within_the_menu_budget() {
        // 평범한 zip은 제한 시간 안에 읽혀야 한다(제한 시간 장치가 정상 동작까지
        // 막아 버리면 미리보기가 통째로 사라진다).
        let path = make_zip(
            "packnine_test_budget.zip",
            &[("문서/기획안.txt", 1200), ("읽어보기.txt", 20)],
        );
        let started = std::time::Instant::now();
        let entries = zip_entries(&path, 5).expect("제한 시간 안에 읽혔어야 한다");

        assert_eq!(entries.len(), 2);
        assert!(started.elapsed() < LISTING_BUDGET * 4, "{:?}", started.elapsed());
    }

    #[test]
    fn slow_archive_is_skipped_on_the_next_right_click() {
        // 한 번 시간을 넘긴 아카이브는 다시 읽지 않는다. 우클릭할 때마다 몇 분짜리
        // 읽기를 새로 띄우면 디스크만 계속 긁는다.
        let path = make_zip("packnine_test_slow_memo.zip", &[("a.txt", 10)]);
        assert!(!is_known_slow(&path));
        assert!(zip_entries(&path, 5).is_some());

        remember_slow(&path);

        assert!(is_known_slow(&path));
        assert!(zip_entries(&path, 5).is_none(), "기억해 둔 아카이브는 즉시 건너뛴다");
    }

    #[test]
    fn encrypted_entries_still_appear_in_the_listing() {
        // 암호가 걸린 엔트리는 복호화에 실패하지만 이름과 크기는 중앙 디렉터리에
        // 평문으로 있다. 목록이 통째로 비면 안 된다.
        use zip::unstable::write::FileOptionsExt;

        let path = std::env::temp_dir().join("packnine_test_encrypted.zip");
        let file = File::create(&path).unwrap();
        let mut writer = zip::ZipWriter::new(file);
        let options: zip::write::FileOptions<'_, ()> = zip::write::FileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .with_deprecated_encryption(b"pw123");
        writer.start_file("비밀.txt", options).unwrap();
        writer.write_all(&vec![b'A'; 64]).unwrap();
        writer.finish().unwrap();

        let entries = zip_entries(&path, 5).expect("목록은 읽혀야 한다");
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].0, "비밀.txt");
    }

    #[test]
    fn lists_entries_with_sizes() {
        let path = make_zip("packnine_test_list.zip", &[("문서/기획안.txt", 1200), ("읽어보기.txt", 20)]);
        let text = preview_text(&path);

        assert!(text.contains("문서/기획안.txt"), "{text}");
        assert!(text.contains("읽어보기.txt"), "{text}");
        // 사람이 읽는 크기 표기로 바꿔야 한다.
        assert!(text.contains("1.2 KB"), "{text}");
        assert!(text.contains("파일 2개"), "{text}");
    }

    #[test]
    fn non_zip_extension_explains_instead_of_failing() {
        // 빈 창 대신 이유를 보여줘야 한다.
        let path = PathBuf::from("어딘가/자료.7z");
        let text = preview_text(&path);

        assert!(text.contains("미리보기를 지원하지 않습니다"), "{text}");
        assert!(text.contains("자료.7z"), "{text}");
    }

    #[test]
    fn broken_zip_reports_reason() {
        let path = std::env::temp_dir().join("packnine_test_broken.zip");
        std::fs::write(&path, b"this is not a zip").unwrap();

        let text = preview_text(&path);

        assert!(text.contains("읽을 수 없습니다"), "{text}");
    }

    #[test]
    fn missing_file_reports_reason() {
        let text = preview_text(&std::env::temp_dir().join("packnine_없는파일.zip"));

        assert!(text.contains("열 수 없습니다"), "{text}");
    }

    #[test]
    fn size_formatting_switches_units() {
        assert_eq!(format_size(512), "512 B");
        assert_eq!(format_size(1536), "1.5 KB");
        assert_eq!(format_size(5 * 1024 * 1024), "5.0 MB");
    }

    #[test]
    fn huge_archive_is_truncated() {
        let entries: Vec<(String, usize)> =
            (0..MAX_ENTRIES + 50).map(|i| (format!("f{i}.txt"), 10)).collect();
        let refs: Vec<(&str, usize)> =
            entries.iter().map(|(n, s)| (n.as_str(), *s)).collect();
        let path = make_zip("packnine_test_huge.zip", &refs);

        let text = preview_text(&path);

        // 수만 개짜리 아카이브에서 미리보기가 멈추지 않도록 상한을 둔다.
        assert!(text.contains("이하 생략"), "{text}");
        assert!(!text.contains("f600.txt"), "{text}");
    }
}
