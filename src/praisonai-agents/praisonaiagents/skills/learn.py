"""Grounded skill-authoring prompt builder for the "learn from sources" flow.

This module hosts :func:`build_learn_prompt`, a curated authoring directive that
turns a user request like *"read ./my-repo and the docs in ./docs/*.pdf and make
a 'deploy-flow' skill"* into a single-turn instruction. The agent then gathers
the named sources with the tools it already has (file read, fetch, PDF read) and
authors **one grounded SKILL.md** via the existing ``skill_manage`` tool.

It is intentionally prompt-only (no heavy imports, no new engine) so it stays in
the core SDK alongside the skills subsystem.
"""

from __future__ import annotations


_LEARN_HOUSE_STYLE = """You are authoring a single, reusable Agent Skill by learning from real source material.

The user's request describes the sources to learn from and the skill to produce:
<request>
{request}
</request>

Follow this procedure exactly:

1. GATHER the named sources using the tools you already have:
   - Read local files and directories of code, configs, or notes.
   - Read PDFs/manuals if PDF reading is available.
   - Fetch API docs / URLs if a fetch tool is available.
   - If the request says "what we just did" or "this chat", use the conversation so far as the source.
   Only use sources the user actually named. Do not browse unrelated material.

2. DISTIL one grounded SKILL.md. House-style rules that keep it trustworthy:
   - Use ONLY flags, paths, commands, environment variables, and API names that appear
     VERBATIM in the gathered sources. Never invent or guess names that are not in the source.
   - If something is not present in the source, omit it rather than fabricating it.
   - Keep SKILL.md tight: roughly 100-200 lines. Move long reference material
     (large code, full API tables, transcripts) into supporting files and reference
     them by RELATIVE path from SKILL.md.
   - Include a YAML frontmatter block with at least `name` and `description`.
   - Write a clear, procedural body: when to use the skill, the concrete steps,
     and any commands/scripts the user runs, drawn from the real sources.

3. WRITE the skill with the skill_manage tool in a single create call:
   skill_manage(action="create", name="<kebab-case-name>", content="<full SKILL.md>")
   - Derive the skill name from the request (kebab-case). If the request names one
     explicitly (e.g. a 'deploy-flow' skill), use that name.
   - For any supporting files, use skill_manage(action="write_file", name=..., file_path=..., file_content=...).

4. Do not perform any work beyond gathering the sources and authoring this one skill.
   When the skill is created, briefly summarize the skill name and what it covers.
"""


def build_learn_prompt(request: str) -> str:
    """Build a grounded skill-authoring directive from a user request.

    This is the **skill authoring** path: distil a reusable ``SKILL.md`` from
    real sources. It is complementary to — and distinct from — the memory
    ``learn=`` recall path (conversation→memory extraction) and the automatic
    ``self_improve`` loop.

    Args:
        request: A natural-language description of the sources to learn from and
            the skill to produce, e.g. ``"Read ./my-repo and the docs in
            ./docs/*.pdf and make a 'deploy-flow' skill"``.

    Returns:
        A prompt string that instructs an agent to gather the named sources with
        its existing tools and author one grounded ``SKILL.md`` via
        ``skill_manage``.
    """
    request = (request or "").strip()
    return _LEARN_HOUSE_STYLE.replace("{request}", request)
