"""Autonomous skill self-improvement loop.

Closes the loop on the existing skill subsystem: after a task finishes, an
opt-in *guarded* review pass runs a short, isolated turn restricted to the
``skill_manage`` tool and asks the agent whether the session revealed a
reusable technique worth persisting as a skill.

Design guarantees (see issue #2231):
- Off by default — only runs when ``self_improve`` is enabled.
- Never runs with the full toolset — the review turn is restricted to the
  single skill-mutation tool.
- Re-entrancy guarded — the review turn itself cannot trigger another review.
- Best-effort — any failure is swallowed so it never breaks the main task.

This logic lives in its own mixin so ``agent.py`` stays lean.
"""

import logging

logger = logging.getLogger(__name__)


class SkillReviewMixin:
    """Mixin providing the guarded skill-review pass for ``Agent``."""

    def _skill_review_policy(self):
        """Return the active review policy, building the default lazily."""
        policy = getattr(self, "_self_improve_policy", None)
        if policy is not None:
            return policy
        from ..skills import DefaultSkillReviewPolicy
        policy = DefaultSkillReviewPolicy()
        self._self_improve_policy = policy
        return policy

    def _build_skill_review_tool(self):
        """Return the restricted toolset for the review turn (skill_manage only)."""
        try:
            from ..tools.skill_tools import create_skill_tools
            skill_tools = create_skill_tools()
            return [skill_tools.skill_manage]
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Could not build skill review tool: %s", e, exc_info=True)
            return []

    def _skill_review_log_context(self):
        """Return (agent_name, session_id) for swallowed-failure warnings."""
        return (
            getattr(self, "name", None),
            getattr(self, "_session_id", None),
        )

    def _prepare_skill_review(self, prompt, response, tools_used=None):
        """Gate + build the review turn. Returns (review_prompt, review_tools) or None.

        Shared by the sync and async paths so they stay in lock-step. Applies
        the opt-in switch, the re-entrancy guard, the policy decision, and the
        restricted-toolset build.
        """
        # Opt-in only.
        if not getattr(self, "_self_improve", False):
            return None
        # Re-entrancy guard: never review a review.
        if getattr(self, "_in_skill_review", False):
            return None

        trajectory = {
            "prompt": prompt if isinstance(prompt, str) else str(prompt),
            "response": response or "",
            "tools_used": list(tools_used or []),
        }

        try:
            policy = self._skill_review_policy()
            if not policy.should_review(trajectory):
                return None
            review_prompt = policy.review_prompt(trajectory)
        except Exception as e:
            name, session_id = self._skill_review_log_context()
            logger.warning(
                "Skill review policy failed for agent=%s session_id=%s: %s",
                name, session_id, e, exc_info=True,
            )
            return None

        review_tools = self._build_skill_review_tool()
        if not review_tools:
            logger.debug("Skill review skipped: skill_manage tool unavailable")
            return None

        return review_prompt, review_tools

    def _snapshot_chat_history_len(self):
        """Return the current chat_history length, or None if unavailable."""
        history = getattr(self, "chat_history", None)
        return len(history) if isinstance(history, list) else None

    def _restore_chat_history(self, snapshot_len):
        """Trim chat_history back to ``snapshot_len`` so the review turn is isolated.

        The review turn is internal: any user/assistant messages it appended to
        the shared, persistent chat_history must not leak into subsequent turns
        of a reused agent (chatbot, REPL, agentic loop).
        """
        if snapshot_len is None:
            return
        history = getattr(self, "chat_history", None)
        if isinstance(history, list) and len(history) > snapshot_len:
            del history[snapshot_len:]

    def _run_skill_review(self, prompt, response, tools_used=None):
        """Run the guarded skill-review pass.

        Args:
            prompt: The original user prompt for the finished task.
            response: The final response produced for the task.
            tools_used: Names of tools used during the task (if known).
        """
        prepared = self._prepare_skill_review(prompt, response, tools_used)
        if prepared is None:
            return
        review_prompt, review_tools = prepared

        self._in_skill_review = True
        history_len = self._snapshot_chat_history_len()
        try:
            if getattr(self, "verbose", False):
                logger.info("Agent %s running guarded skill-review pass", self.name)
            # Restricted turn: only skill_manage is exposed via the tools= arg.
            self.chat(review_prompt, tools=review_tools)
        except Exception as e:
            name, session_id = self._skill_review_log_context()
            logger.warning(
                "Skill review pass failed for agent=%s session_id=%s: %s",
                name, session_id, e, exc_info=True,
            )
        finally:
            self._restore_chat_history(history_len)
            self._in_skill_review = False

    async def _arun_skill_review(self, prompt, response, tools_used=None):
        """Async variant of :meth:`_run_skill_review`."""
        prepared = self._prepare_skill_review(prompt, response, tools_used)
        if prepared is None:
            return
        review_prompt, review_tools = prepared

        self._in_skill_review = True
        history_len = self._snapshot_chat_history_len()
        try:
            if getattr(self, "verbose", False):
                logger.info("Agent %s running guarded skill-review pass", self.name)
            await self.achat(review_prompt, tools=review_tools)
        except Exception as e:
            name, session_id = self._skill_review_log_context()
            logger.warning(
                "Skill review pass failed for agent=%s session_id=%s: %s",
                name, session_id, e, exc_info=True,
            )
        finally:
            self._restore_chat_history(history_len)
            self._in_skill_review = False

    def _schedule_self_improvement(self, run_review):
        """Enqueue the guarded skill-review pass on the core background runner.

        The reply has already been returned to the caller by the time this is
        called; the review turn (a full extra LLM round-trip) runs off the hot
        path on the shared :class:`BackgroundJobManager` so a long-lived
        gateway/bot agent never pays its latency on the user-visible path
        (issue #2985). Best-effort: if the runner cannot be reached the review
        falls back to running inline so behaviour is never silently dropped.

        Args:
            run_review: A zero-arg callable that performs the guarded review
                (already bound to the captured trajectory).
        """
        try:
            from ..background.job_manager import get_job_manager
            name, session_id = self._skill_review_log_context()
            get_job_manager().start_job(
                run_review,
                job_id=f"self-improve:{session_id or name or 'default'}",
            )
        except Exception as e:  # pragma: no cover - defensive fallback
            logger.debug(
                "Backgrounding skill review failed (%s); running inline", e,
                exc_info=True,
            )
            run_review()
