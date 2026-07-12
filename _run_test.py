import os, tempfile
os.environ['PRAISONAI_ALLOW_LOCAL_TOOLS'] = 'true'
src = '''
def public_fn(x):
    return x

def _private_fn(x):
    return x

class Callable1:
    def __call__(self):
        return 1

instance = Callable1()
'''
p = os.path.join(tempfile.gettempdir(), '_tools_test_2935.py')
with open(p, 'w') as f:
    f.write(src)
from praisonai_code.tool_resolver import ToolResolver
r = ToolResolver()
cli = r.load_functions_from_module(p, functions_only=True, skip_private=True)
print('CLI (functions_only+skip_private):', sorted(cli.keys()))
default = r.load_functions_from_module(p)
print('default:', sorted(default.keys()))
assert sorted(cli.keys()) == ['public_fn'], cli.keys()
assert 'instance' in default and 'public_fn' in default, default.keys()
os.remove(p)
print('OK')
