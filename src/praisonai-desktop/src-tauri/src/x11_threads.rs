//! Tell Xlib it is about to be used from more than one thread.
//!
//! GTK3 never calls `XInitThreads()`, so every Xlib lock is a no-op. This
//! process drives X from several threads regardless -- WebKitGTK's compositor,
//! GLib workers, the event loop, the clipboard -- so the request/reply sequence
//! Xlib keeps for its XCB transport can be corrupted by interleaving.
//!
//! The failure is not a clean error. `_XReply` fails to match a reply and calls
//! `_XIOError` while `xcb_connection_has_error()` still reports 0; GDK's IO
//! error handler reports that through `g_debug()` -- dropped unless
//! `G_MESSAGES_DEBUG` happens to name the domain -- and then `_exit(1)`s. The
//! app simply vanishes, with exit code 1 and no output at all, intermittently.
//!
//! Resolved through `dlsym` rather than by linking libX11, deliberately: on a
//! Wayland-only or headless host the symbol is absent and this becomes a no-op,
//! instead of the binary failing to load for want of a library it never needs.

/// Call `XInitThreads()` if this process has Xlib loaded. Safe anywhere.
///
/// Must run before any X connection is opened, which in practice means first
/// in `main()` -- after GTK has connected it is too late to matter.
pub fn init() {
    #[cfg(all(unix, not(target_os = "macos")))]
    unsafe {
        use std::ffi::c_void;

        const RTLD_DEFAULT: *mut c_void = std::ptr::null_mut();
        extern "C" {
            // c_char, not i8: c_char is *unsigned* on aarch64 and arm Linux,
            // so i8 does not compile there. The CI runner is x86_64, where the
            // two happen to agree, so nothing would have caught it.
            fn dlsym(handle: *mut c_void, symbol: *const std::ffi::c_char) -> *mut c_void;
        }
        let name = c"XInitThreads";
        let symbol = dlsym(RTLD_DEFAULT, name.as_ptr());
        if !symbol.is_null() {
            let x_init_threads: extern "C" fn() -> i32 = std::mem::transmute(symbol);
            x_init_threads();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn calling_it_is_safe_on_any_platform() {
        // On macOS and on a host with no Xlib this resolves nothing and does
        // nothing; the point is that it never panics or aborts.
        init();
        init(); // and is idempotent, as XInitThreads itself is
    }
}
