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

    def _run_skill_review(self, prompt, response, tools_used=None):
        """Run the guarded skill-review pass.

        Args:
            prompt: The original user prompt for the finished task.
            response: The final response produced for the task.
            tools_used: Names of tools used during the task (if known).
        """
        # Opt-in only.
        if not getattr(self, "_self_improve", False):
            return
        # Re-entrancy guard: never review a review.
        if getattr(self, "_in_skill_review", False):
            return

        trajectory = {
            "prompt": prompt if isinstance(prompt, str) else str(prompt),
            "response": response or "",
            "tools_used": list(tools_used or []),
        }

        try:
            policy = self._skill_review_policy()
            if not policy.should_review(trajectory):
                return
            review_prompt = policy.review_prompt(trajectory)
        except Exception as e:
            logger.warning("Skill review policy failed: %s", e, exc_info=True)
            return

        review_tools = self._build_skill_review_tool()
        if not review_tools:
            logger.debug("Skill review skipped: skill_manage tool unavailable")
            return

        self._in_skill_review = True
        try:
            if getattr(self, "verbose", False):
                logger.info("Agent %s running guarded skill-review pass", self.name)
            # Restricted turn: only skill_manage is exposed via the tools= arg.
            self.chat(review_prompt, tools=review_tools)
        except Exception as e:
            logger.warning("Skill review pass failed: %s", e, exc_info=True)
        finally:
            self._in_skill_review = False

    async def _arun_skill_review(self, prompt, response, tools_used=None):
        """Async variant of :meth:`_run_skill_review`."""
        if not getattr(self, "_self_improve", False):
            return
        if getattr(self, "_in_skill_review", False):
            return

        trajectory = {
            "prompt": prompt if isinstance(prompt, str) else str(prompt),
            "response": response or "",
            "tools_used": list(tools_used or []),
        }

        try:
            policy = self._skill_review_policy()
            if not policy.should_review(trajectory):
                return
            review_prompt = policy.review_prompt(trajectory)
        except Exception as e:
            logger.warning("Skill review policy failed: %s", e, exc_info=True)
            return

        review_tools = self._build_skill_review_tool()
        if not review_tools:
            logger.debug("Skill review skipped: skill_manage tool unavailable")
            return

        self._in_skill_review = True
        try:
            if getattr(self, "verbose", False):
                logger.info("Agent %s running guarded skill-review pass", self.name)
            await self.achat(review_prompt, tools=review_tools)
        except Exception as e:
            logger.warning("Skill review pass failed: %s", e, exc_info=True)
        finally:
            self._in_skill_review = False
