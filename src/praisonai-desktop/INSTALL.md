# Installing the PraisonAI desktop app

Every release attaches one file per platform. Pick yours:

| Platform | Download |
|---|---|
| macOS, Apple silicon (M1–M4) | `PraisonAI-<version>-macos-apple-silicon.dmg` |
| macOS, Intel | `PraisonAI-<version>-macos-intel.dmg` |
| Windows 10/11, 64-bit | `PraisonAI-<version>-windows-x64-setup.exe` |
| Linux, 64-bit (Debian/Ubuntu) | `PraisonAI-<version>-linux-x64.deb` |

There is no universal or cross-platform build. Tauri produces one binary per
architecture, and a wrong-arch download fails when you launch it rather than
when you install it — which is a worse place to find out.

None of these builds is code-signed. That is a deliberate trade: signing needs
an Apple Developer ID on one side and a hardware-backed certificate or a hosted
signing service on the other, and shipping builds you can open past a warning
is better than shipping none. Each platform complains differently, so the exact
wording and the exact click are below.

---

## macOS

Not sure which Mac you have:  → About This Mac. "Chip" means Apple silicon,
"Processor" means Intel.

Gatekeeper refuses an app it cannot verify. The app carries an ad-hoc
signature, which makes the signature *valid* but not *trusted* — so macOS says
it cannot check for malicious software, or that the developer is
unidentified.

1. Drag **PraisonAI** to Applications.
2. **Right-click** it → **Open** → **Open**.

That once is enough; afterwards it launches normally.

If macOS still refuses, clear the quarantine attribute your browser added when
it downloaded the file:

```sh
xattr -dr com.apple.quarantine /Applications/PraisonAI.app
```

### If you see *"PraisonAI is damaged and can't be opened"*

That message means something different, and right-click → Open will **not**
get past it: macOS says "damaged" when a signature is present but *invalid*,
not when one is merely untrusted.

**v4.7.2 shipped in exactly that state.** The bundle was never signed, so the
only signature on it was the one the Rust linker leaves on the executable, and
that signature declares a resource seal an unsigned bundle does not have. Every
Mac rejected it. Use v4.7.3 or later; the release build now refuses to attach a
macOS bundle whose signature does not verify.

## Windows

SmartScreen shows a full-screen *"Windows protected your PC"* with the Run
button hidden.

1. Run the installer.
2. Click **More info**, then **Run anyway**.

It installs for the current user only, into `%LOCALAPPDATA%`, so it never asks
for an administrator password.

If the app needs the WebView2 runtime and it is missing, the installer fetches
it. Windows 11 and up-to-date Windows 10 already have it.

## Linux

```sh
sudo apt install ./PraisonAI-<version>-linux-x64.deb
```

`apt` rather than `dpkg -i`, so the WebKitGTK dependencies are resolved rather
than reported. The package is built on Ubuntu 22.04, so it runs on 22.04,
Debian 12 and anything newer. On an older distribution glibc will refuse it,
and no runtime flag fixes that — build from source instead.

There is no `.rpm` and no AppImage. AppImage in particular needs `libfuse2`,
which Ubuntu 24.04 removed, and renders a blank window on some Wayland and Mesa
combinations; a `.deb` that works is better than an AppImage that half does.

---

## What happens the first time you open it

The app needs a Python environment to run its engine and will offer to build
one: it fetches `uv`, installs a pinned CPython, creates a virtual environment,
and installs `praisonaiagents` into it. Roughly 500 MB, once.

Nothing is installed system-wide, and nothing is written inside the app itself.
The environment and your conversations live together in one folder:

| Platform | Where |
|---|---|
| macOS | `~/Library/Application Support/PraisonAI` |
| Windows | `%APPDATA%\PraisonAI` |
| Linux | `~/.local/share/PraisonAI` (or `$XDG_DATA_HOME/PraisonAI`) |

To remove the app completely, uninstall it and delete that folder.

## If it will not start

The window shows the reason and the engine log. The two common ones:

- **"No usable Python"** — the setup screen offers to build the environment.
  If it fails, the step that failed is named along with what it printed.
- **"Engine did not report ready in time"** — the first import of the ML stack
  is slow on a cold machine. Give it a minute; if it persists, the Engine log
  in the sidebar has the traceback.
