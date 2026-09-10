"""
Tests for the memory consolidation protocol and result contract.

The heavy consolidation implementation (an LLM pass) and its scheduling live in
a lifecycle plugin (PraisonAI-Plugins). Core only exposes the protocol/contract
plus the loss-guard, so these tests exercise only that lightweight surface.
"""

import pytest


class TestConsolidationResult:
    """Tests for the ConsolidationResult loss-guard contract."""

    def test_import(self):
        from praisonaiagents.memory import ConsolidationResult
        assert ConsolidationResult is not None

    def test_defaults(self):
        from praisonaiagents.memory import ConsolidationResult

        r = ConsolidationResult()
        assert r.entries_before == 0
        assert r.entries_after == 0
        assert r.merged == 0
        assert r.promoted == 0
        assert r.pruned == 0
        assert r.rejected is False
        assert r.reason is None
        assert r.context == {}

    def test_loss_fraction(self):
        from praisonaiagents.memory import ConsolidationResult

        r = ConsolidationResult(entries_before=100, entries_after=60)
        assert r.loss_fraction == pytest.approx(0.4)

    def test_loss_fraction_empty_store(self):
        from praisonaiagents.memory import ConsolidationResult

        # No division-by-zero; empty store means zero loss.
        assert ConsolidationResult().loss_fraction == 0.0

    def test_loss_fraction_growth_is_not_negative(self):
        from praisonaiagents.memory import ConsolidationResult

        # A pass that adds entries should never report negative loss.
        r = ConsolidationResult(entries_before=10, entries_after=15)
        assert r.loss_fraction == 0.0

    def test_exceeds_loss_guard(self):
        from praisonaiagents.memory import ConsolidationResult

        r = ConsolidationResult(entries_before=100, entries_after=60)
        assert r.exceeds_loss(0.25) is True
        assert r.exceeds_loss(0.4) is False
        assert r.exceeds_loss(0.5) is False


class TestConsolidationProtocol:
    """Tests for the MemoryConsolidationProtocol structural typing."""

    def test_import(self):
        from praisonaiagents.memory import (
            MemoryConsolidationProtocol,
            AsyncMemoryConsolidationProtocol,
        )
        assert MemoryConsolidationProtocol is not None
        assert AsyncMemoryConsolidationProtocol is not None

    def test_sync_isinstance(self):
        from praisonaiagents.memory import (
            MemoryConsolidationProtocol,
            ConsolidationResult,
        )

        class Consolidator:
            def consolidate(self, memory, *, max_loss_fraction=0.25):
                return ConsolidationResult()

        assert isinstance(Consolidator(), MemoryConsolidationProtocol)

    def test_async_isinstance(self):
        from praisonaiagents.memory import (
            AsyncMemoryConsolidationProtocol,
            ConsolidationResult,
        )

        class AsyncConsolidator:
            async def aconsolidate(self, memory, *, max_loss_fraction=0.25):
                return ConsolidationResult()

        assert isinstance(AsyncConsolidator(), AsyncMemoryConsolidationProtocol)

    def test_non_conforming_is_not_instance(self):
        from praisonaiagents.memory import MemoryConsolidationProtocol

        class NotAConsolidator:
            pass

        assert not isinstance(NotAConsolidator(), MemoryConsolidationProtocol)

    def test_loss_guard_rejects_lossy_rewrite(self):
        """A conforming consolidator refuses a rewrite over the loss bound."""
        from praisonaiagents.memory import (
            MemoryConsolidationProtocol,
            ConsolidationResult,
        )

        class LossGuardedConsolidator:
            def consolidate(self, memory, *, max_loss_fraction=0.25):
                before = memory.get_all_memories()
                # Simulate a catastrophic rewrite dropping almost everything.
                entries_after = 1
                result = ConsolidationResult(
                    entries_before=len(before),
                    entries_after=entries_after,
                )
                if result.exceeds_loss(max_loss_fraction):
                    result.rejected = True
                    result.reason = "loss guard tripped"
                    result.entries_after = result.entries_before
                return result

        class FakeMemory:
            def get_all_memories(self, **kwargs):
                return [{"text": f"m{i}"} for i in range(100)]

        consolidator = LossGuardedConsolidator()
        assert isinstance(consolidator, MemoryConsolidationProtocol)

        result = consolidator.consolidate(FakeMemory(), max_loss_fraction=0.25)
        assert result.rejected is True
        assert result.reason == "loss guard tripped"
        # Store left untouched: reported after-count equals before-count.
        assert result.entries_after == result.entries_before
