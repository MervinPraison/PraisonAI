"""The ship/steward never-merge guard.

The agent behind ``praisonai ship`` / ``praisonai steward`` must never merge,
approve, enable auto-merge or force-push. The guard is a before_tool hook, so
it holds even when an earlier "always" approval allows ``bash:gh pr *``.
"""

import pytest

from praisonaiagents.hooks import BeforeToolInput, HookEvent, HookRegistry, HookRunner

from praisonai_code.ship.guard import forbidden_reason, never_merge_hook, register_never_merge


FORBIDDEN = [
    "gh pr merge 12",
    "gh pr merge --auto --squash",
    "gh  pr   merge",
    "gh -R owner/repo pr merge 3",
    "gh pr review 12 --approve",
    "gh pr review -a",
    "gh api -X PUT repos/o/r/pulls/1/merge",
    "gh api repos/o/r/pulls/1/merge --method PUT",
    "gh api repos/o/r/pulls/1/reviews -f event=APPROVE",
    "gh api graphql -f query='mutation{mergePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}'",
    "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input:{pullRequestId:\"x\"}) { clientMutationId } }'",
    "gh api graphql -f query='mutation{addPullRequestReview(input:{pullRequestId:\"x\",event:APPROVE}){clientMutationId}}'",
    "gh api graphql -F query=@merge.graphql",
    "gh api graphql --input merge.json",
    "git push --force",
    "git push -f origin feat",
    "git push -uf origin feat",
    "git push --force-with-lease origin feat",
    "git -C /tmp/x push origin +feat",
    "git push origin +HEAD:main",
    "cd repo && gh pr merge 5",
    "echo ok; git push -f",
    "bash -c 'gh pr merge 5'",
    "/usr/bin/gh pr merge 5",
]

ALLOWED = [
    "gh pr create --draft --fill",
    "gh pr view 12 --json statusCheckRollup",
    "gh pr review 12 --comment -b 'looks fine'",
    "gh pr checks 12",
    "gh api repos/o/r/pulls/1/comments",
    "gh api repos/o/r/pulls/1/reviews -f event=COMMENT -f body=done",
    "gh api graphql -f query='mutation{resolveReviewThread(input:{threadId:\"t\"}){thread{id}}}'",
    "gh api graphql -f query='{viewer{login}}'",
    "git push origin feat",
    "git push -u origin feat",
    "git merge origin/main",
    "git commit -m 'merge base in'",
    "ls -la",
    "",
]


@pytest.mark.parametrize("command", FORBIDDEN)
def test_forbidden_commands_are_refused(command):
    assert forbidden_reason(command)


@pytest.mark.parametrize("command", ALLOWED)
def test_normal_pr_work_is_allowed(command):
    assert forbidden_reason(command) is None


def _input(tool_name, tool_input):
    return BeforeToolInput(
        session_id="s",
        cwd=".",
        event_name=HookEvent.BEFORE_TOOL,
        timestamp="0",
        agent_name="ship",
        tool_name=tool_name,
        tool_input=tool_input,
    )


def test_hook_denies_a_merge_through_any_shell_tool():
    result = never_merge_hook(_input("execute_command", {"command": "gh pr merge 7 --squash"}))
    assert result.is_denied()
    assert "merge" in result.reason


def test_hook_allows_other_tools_and_commands():
    assert never_merge_hook(_input("execute_command", {"command": "gh pr create --draft"})).is_allowed()
    assert never_merge_hook(_input("write_file", {"path": "a.md", "content": "gh pr merge"})).is_allowed()


@pytest.mark.asyncio
async def test_registered_hook_blocks_the_tool_call():
    registry = HookRegistry()
    register_never_merge(registry)
    results = await HookRunner(registry).execute(
        HookEvent.BEFORE_TOOL, _input("run_shell_command", {"cmd": "git push -f"})
    )
    assert HookRunner.is_blocked(results)


def test_agent_tool_call_to_merge_is_blocked():
    """An Agent wired with the guard cannot run a merge, even with the tool allowed."""
    from praisonaiagents import Agent

    ran = []

    def gh_cli(command: str) -> str:
        """Run a shell command."""
        ran.append(command)
        return "ok"

    registry = HookRegistry()
    register_never_merge(registry)
    agent = Agent(name="ship", tools=[gh_cli], hooks=registry)

    blocked = agent.execute_tool("gh_cli", {"command": "gh pr merge 9 --auto"})
    assert "blocked" in str(blocked)
    assert ran == []

    agent.execute_tool("gh_cli", {"command": "gh pr view 9"})
    assert ran == ["gh pr view 9"]
