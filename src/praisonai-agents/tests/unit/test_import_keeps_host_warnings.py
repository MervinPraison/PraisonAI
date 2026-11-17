"""X-09: importing the SDK does not hide the host's own pydantic warnings.

``_warning_patch`` installed ``filterwarnings("ignore", category=UserWarning,
module="pydantic.*")``, which hid every pydantic UserWarning in the process,
including ones about the host application's own models. An SDK run on both
routes raises no pydantic UserWarning without it; the narrow message filters
for known dependency noise stay.
"""

import json
import os
import subprocess
import sys
import textwrap

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SCRIPT = textwrap.dedent('''
    import json, warnings
    import praisonaiagents
    with warnings.catch_warnings(record=True) as caught:
        warnings.warn_explicit("Field name shadows an attribute", UserWarning, "pydantic/main.py", 1,
                               module="pydantic.main")
        warnings.warn_explicit("Pydantic serializer warnings: noise", UserWarning, "x.py", 1, module="litellm")
    print(json.dumps([str(w.message) for w in caught]))
''')


def test_host_pydantic_warning_is_shown_and_known_noise_stays_hidden(tmp_path):
    env = dict(os.environ, PYTHONPATH=PKG_ROOT)
    env.pop("PYTHONWARNINGS", None)
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == ["Field name shadows an attribute"]
