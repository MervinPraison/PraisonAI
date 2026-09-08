"""Regression tests for per-context observability run-stack isolation (#4945).

The run stack lives in a ``ContextVar`` whose value is treated as *immutable*
(copy-on-write). A child context (``asyncio.create_task``/``copy_context``) must
not be able to mutate its parent's stack — otherwise a spawned task's
``finalize_observability`` could pop and tear down a sibling/parent run.
"""
import asyncio
import contextvars
import unittest

from praisonai.observability import hooks


class TestRunStackIsolation(unittest.TestCase):
    def setUp(self):
        # Start each test from a clean, empty stack in this context.
        hooks._run_stack.set(None)

    def test_push_does_not_mutate_a_copied_context(self):
        """A run pushed in a copied context is invisible to the origin context."""
        run_a = hooks.ObservabilityRun()
        hooks._push_run(run_a)
        self.assertEqual(hooks._get_run_stack(), [run_a])

        # copy_context() snapshots the current stack; pushing inside the copy
        # must not leak back into this (parent) context.
        ctx = contextvars.copy_context()

        def _child_push():
            hooks._push_run(hooks.ObservabilityRun())
            # Child sees both runs...
            return len(hooks._get_run_stack())

        child_len = ctx.run(_child_push)
        self.assertEqual(child_len, 2)
        # ...parent still sees only its own run.
        self.assertEqual(hooks._get_run_stack(), [run_a])

    def test_pop_in_copied_context_leaves_parent_intact(self):
        run_a = hooks.ObservabilityRun()
        hooks._push_run(run_a)

        ctx = contextvars.copy_context()

        def _child_pop():
            return hooks._pop_run()

        popped = ctx.run(_child_pop)
        # The child popped *its inherited copy* of run_a...
        self.assertIs(popped, run_a)
        # ...but the parent's stack is untouched.
        self.assertEqual(hooks._get_run_stack(), [run_a])

    def test_get_run_stack_returns_a_copy_not_the_live_list(self):
        run_a = hooks.ObservabilityRun()
        hooks._push_run(run_a)
        snapshot = hooks._get_run_stack()
        snapshot.append(hooks.ObservabilityRun())  # mutate the returned copy
        # The internal stack is unaffected by mutating the snapshot.
        self.assertEqual(hooks._get_run_stack(), [run_a])

    def test_concurrent_tasks_get_isolated_stacks(self):
        """Two asyncio tasks on one thread must not share a run stack."""

        async def _worker(run):
            hooks._push_run(run)
            await asyncio.sleep(0)  # yield so tasks interleave
            stack = hooks._get_run_stack()
            # Each task sees exactly its own run, never the sibling's.
            assert stack == [run], stack
            popped = hooks._pop_run()
            assert popped is run
            return True

        async def _main():
            hooks._run_stack.set(None)
            run1 = hooks.ObservabilityRun()
            run2 = hooks.ObservabilityRun()
            results = await asyncio.gather(_worker(run1), _worker(run2))
            return results

        self.assertEqual(asyncio.run(_main()), [True, True])

    def test_remove_run_is_copy_on_write(self):
        run_a = hooks.ObservabilityRun()
        run_b = hooks.ObservabilityRun()
        hooks._push_run(run_a)
        hooks._push_run(run_b)

        ctx = contextvars.copy_context()
        ctx.run(hooks._remove_run, run_a)

        # Parent context is unaffected by the removal inside the copied context.
        self.assertEqual(hooks._get_run_stack(), [run_a, run_b])


if __name__ == "__main__":
    unittest.main()
