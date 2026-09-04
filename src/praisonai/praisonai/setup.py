from setuptools import setup

# NOTE: No PostInstallCommand / cmdclass override.
# `pip install praisonai` must have NO network side-effects: browsers are
# provisioned on demand (e.g. `praisonai browser` prints an actionable
# `playwright install chromium` hint the first time a browser tool is used),
# not force-downloaded at install time. This keeps the default install lean
# and offline/CI-friendly.
setup()
