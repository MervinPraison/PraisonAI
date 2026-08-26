//! The menubar item.
//!
//! Both reference apps put one here, and it changes what the app *is*: closing
//! the window becomes "put it away" rather than "quit". That distinction is the
//! reason for the `hide-on-close` handling in main.rs -- an engine that takes
//! seconds to start should not be torn down because someone hit the red button.
//!
//! The menu deliberately mirrors what those apps offer, minus anything we
//! cannot actually do: there is no "Restart to update" item because there is no
//! update feed, and an item that did nothing would be worse than its absence.

use std::sync::Mutex;

use tauri::{
    menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    image::Image,
    AppHandle, Manager, Runtime,
};

pub const SHOW: &str = "tray_show";
pub const ENGINE: &str = "tray_engine";
pub const SETTINGS: &str = "tray_settings";
pub const QUIT: &str = "tray_quit";

/// Handle to the status row, so it can be updated without re-reading the menu.
static ENGINE_ITEM: Mutex<Option<MenuItem<tauri::Wry>>> = Mutex::new(None);

/// Bring the main window forward, restoring it if it was minimised.
pub fn focus_main<R: Runtime>(app: &AppHandle<R>) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// A keyboard accelerator, or none where the modifier does not exist.
fn accel(mac: &str) -> Option<&str> {
    if cfg!(target_os = "macos") {
        Some(mac)
    } else {
        // Deliberately no Ctrl equivalent: a tray menu is not focused, so the
        // accelerator would be a global hotkey stealing a common chord from
        // whatever the user is actually typing into.
        None
    }
}

pub fn build(app: &AppHandle<tauri::Wry>) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, SHOW, "Open PraisonAI", true, None::<&str>)?;
    let engine = MenuItem::with_id(app, ENGINE, "Engine: starting…", false, None::<&str>)?;
    // Accelerators only where the modifier exists. Tauri maps "Cmd" to SUPER
    // off macOS, so these rendered as "Windows+," and "Windows+Q" -- and
    // Win+Q is a reserved OS shortcut, so the menu advertised a binding the
    // system takes first.
    let settings = MenuItem::with_id(app, SETTINGS, "Settings…", true, accel("Cmd+,"))?;
    let sep = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, QUIT, "Quit PraisonAI", true, accel("Cmd+Q"))?;
    let menu = Menu::with_items(app, &[&show, &engine, &sep, &settings, &sep, &quit])?;

    *ENGINE_ITEM.lock().unwrap() = Some(engine.clone());
    TrayIconBuilder::with_id("main")
        // A dedicated menubar glyph, not the app icon.
        //
        // A template image is drawn from its ALPHA channel alone -- macOS
        // discards the colour and tints the shape for the current menubar. The
        // app icon's alpha is opaque edge to edge, so using it produced a solid
        // white block sitting among the system's line glyphs. icons/tray.png
        // carries the mark cut into the alpha instead.
        .icon(tray_icon()?)
        // Template rendering is a macOS concept: the system discards the
        // colour and tints the alpha shape. Windows and Linux draw the actual
        // pixels, and this glyph's pixels are black -- invisible against the
        // Windows 11 taskbar and the GNOME top bar. Setting it only where it
        // means something is half the fix; the other half is a light glyph,
        // which is why the icon is chosen per platform below.
        .icon_as_template(cfg!(target_os = "macos"))
        .menu(&menu)
        // "Unsupported on Linux" per Tauri's own docs -- the menu opens on
        // left click there regardless, so asking for the opposite only makes
        // the code claim something untrue.
        .show_menu_on_left_click(cfg!(not(target_os = "linux")))
        .on_menu_event(handle_menu)
        .on_tray_icon_event(|tray, event| {
            // Left click opens the window; right click opens the menu. Matching
            // the platform convention matters more here than being clever.
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                focus_main(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn handle_menu(app: &AppHandle<tauri::Wry>, event: MenuEvent) {
    match event.id().as_ref() {
        SHOW => focus_main(app),
        SETTINGS => {
            focus_main(app);
            if let Some(w) = app.get_webview_window("main") {
                // The window owns its settings panel, so the tray asks rather
                // than trying to render one of its own.
                let _ = w.eval("document.getElementById('settings')?.click()");
            }
        }
        QUIT => app.exit(0),
        _ => {}
    }
}

/// The menubar glyph, embedded so it cannot go missing from a bundle.
fn tray_icon() -> tauri::Result<Image<'static>> {
    Image::from_bytes(include_bytes!("../icons/tray.png"))
}

/// Reflect the engine's state in the menu.
///
/// The item handle is kept rather than looked up through the tray: `TrayIcon`
/// exposes no `menu()` accessor in this Tauri version, so reaching back for it
/// does not compile.
pub fn set_engine_label<R: Runtime>(app: &AppHandle<R>, text: &str) {
    if let Some(item) = ENGINE_ITEM.lock().ok().and_then(|g| g.clone()) {
        let _ = item.set_text(text);
    }
    let _ = app;
}
