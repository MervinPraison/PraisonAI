# Installing the PraisonAI Mac app

Every release attaches two disk images. Pick the one for your Mac:

| Your Mac | Download |
|---|---|
| Apple silicon (M1–M4) | `PraisonAI-<version>-macos-apple-silicon.dmg` |
| Intel | `PraisonAI-<version>-macos-intel.dmg` |

Not sure which you have:  → About This Mac. "Chip" means Apple silicon,
"Processor" means Intel.

There is no universal build. Tauri produces one binary per architecture, and a
wrong-arch download fails when you launch it rather than when you install it —
which is a worse place to find out.

## First launch

The build is **not signed with an Apple Developer ID**, so Gatekeeper will
refuse it on a double-click with *"PraisonAI is damaged and can't be opened"* —
which is misleading. Nothing is damaged; the app simply has no signature.

1. Drag **PraisonAI** to Applications.
2. **Right-click** it → **Open** → **Open**.

That once is enough; afterwards it launches normally.

If macOS still refuses, clear the quarantine attribute it added when your
browser downloaded the file:

```sh
xattr -dr com.apple.quarantine /Applications/PraisonAI.app
```

## What happens the first time you open it

The app needs a Python environment to run its engine and will offer to build
one: it fetches `uv`, installs a pinned CPython, creates a virtual environment
under `~/Library/Application Support/PraisonAI/venv`, and installs
`praisonaiagents` into it. Roughly 500 MB, once.

Nothing is installed system-wide, and nothing is written inside the app bundle.
To remove it completely, delete `/Applications/PraisonAI.app` and
`~/Library/Application Support/PraisonAI`.

## If it will not start

The window shows the reason and the engine log. The two common ones:

- **"No usable Python"** — the setup screen offers to build the environment.
  If it fails, the step that failed is named along with what it printed.
- **"Engine did not report ready in time"** — the first import of the ML stack
  is slow on a cold machine. Give it a minute; if it persists, the Engine log
  in the sidebar has the traceback.
