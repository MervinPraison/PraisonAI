"""Post-installation hook.

Intentionally a no-op: `pip install praisonai` must NOT download browser
binaries (or perform any other network step) at install time. Fetching all
Playwright browser engines on install breaks offline/air-gapped/CI/sandboxed
environments and bloats the default footprint.

Browser provisioning is on-demand instead: the browser tool path prints an
actionable one-line hint (`playwright install chromium`) the first time a
browser tool is actually used. Install the full stack with
`pip install "praisonai[browser]"` (or `praisonai[all]`).
"""


def main():
    """No-op post-install: no network side-effects."""
    return


if __name__ == "__main__":
    main()
