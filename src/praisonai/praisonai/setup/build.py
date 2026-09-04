"""Build hook shim.

No install-time network side-effects: browser binaries are provisioned on
demand, not downloaded during install. See ``post_install.py``.
"""


def build(setup_kwargs):
    return setup_kwargs


if __name__ == "__main__":
    build({})
