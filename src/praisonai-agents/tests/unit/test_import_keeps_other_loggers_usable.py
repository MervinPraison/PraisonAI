"""R-06: importing the SDK no longer silences other libraries' loggers.

``import praisonaiagents`` set ``httpx``, ``httpcore``, ``openai._base_client``,
``litellm``, ``pydantic`` and others to ``CRITICAL`` with ``propagate=False``,
so an application that configured logging afterwards never saw their
warnings. Now an unset logger gets ``WARNING`` (still quiet by default) and
keeps propagating; a level the application already set is left alone.
"""

import json
import os
import subprocess
import sys
import textwrap

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SCRIPT = textwrap.dedent('''
    import json, logging
    logging.getLogger("pydantic").setLevel(logging.INFO)   # set by the app before import
    import praisonaiagents
    names = ["httpx", "httpcore", "openai._base_client", "litellm", "markdown_it", "pydantic"]
    print(json.dumps({n: [logging.getLogger(n).level, logging.getLogger(n).propagate] for n in names}))
''')


def test_import_leaves_other_loggers_usable(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "LOGLEVEL"}
    env["PYTHONPATH"] = PKG_ROOT
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr[-1500:]
    state = json.loads(proc.stdout.strip().splitlines()[-1])
    for name in ["httpx", "httpcore", "openai._base_client", "litellm", "markdown_it"]:
        assert state[name] == [30, True], (name, state[name])   # WARNING, propagating
    assert state["pydantic"] == [20, True]  # the app's own setting is kept
