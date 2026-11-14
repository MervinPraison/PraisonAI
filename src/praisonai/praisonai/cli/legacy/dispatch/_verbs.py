"""Authoritative legacy CLI verb registry (no imports, never fails to load).

Both the legacy argparse builder and the unified dispatcher
(``praisonai.__main__``) consult this list: a token that is one of these is an
*implemented* verb and must reach its handler, never be reclassified as free
text and billed to an LLM (#4327). Keep this module dependency-free.
"""

LEGACY_SPECIAL_COMMANDS = [
    'chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research',
    'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools',
    'todo', 'docs', 'mcp', 'commit', 'serve', 'schedule', 'skills', 'profile',
    'eval', 'agents', 'run', 'thinking', 'compaction', 'output', 'deploy',
    'templates', 'recipe', 'endpoints', 'audio', 'embed', 'embedding',
    'images', 'moderate', 'files', 'batches', 'vector-stores', 'rerank', 'ocr',
    'assistants', 'fine-tuning', 'completions', 'messages', 'guardrails',
    'rag', 'videos', 'a2a', 'containers', 'passthrough', 'responses', 'search',
    'realtime-api', 'doctor', 'registry', 'package', 'install', 'uninstall',
    'acp', 'debug', 'lsp', 'diag', 'browser', 'replay', 'bot', 'gateway',
    'sandbox', 'wizard', 'migrate', 'security', 'persistence', 'paths', 'claw',
    'github', 'managed', 'flow', 'dashboard', 'backends', 'audit',
]
