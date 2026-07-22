"""
Tests for inbound media-album coalescing (Issue #3298).

An album of N photos/files arrives as N separate updates sharing one
``media_group_id``. The AlbumCoalescer buffers their parts and flushes
them as a single multimodal turn so the agent reasons over the whole set.
"""

import asyncio
import pytest


def _make_coalescer(window_ms=200, max_items=10):
    from praisonai_bot.bots._album import AlbumCoalescer
    return AlbumCoalescer(window_ms=window_ms, max_items=max_items)


class TestAlbumCoalescer:
    @pytest.mark.asyncio
    async def test_standalone_message_returns_immediately(self):
        """No group key -> the update's own parts are returned at once."""
        coalescer = _make_coalescer(window_ms=1000)
        merged = await coalescer.collect(None, ["/tmp/a.jpg"], "hello")
        assert merged is not None
        assert merged.attachments == ["/tmp/a.jpg"]
        assert merged.caption == "hello"

    @pytest.mark.asyncio
    async def test_disabled_window_returns_immediately(self):
        """window_ms == 0 disables coalescing even with a group key."""
        coalescer = _make_coalescer(window_ms=0)
        merged = await coalescer.collect("grp1", ["/tmp/a.jpg"], "")
        assert merged is not None
        assert merged.attachments == ["/tmp/a.jpg"]

    @pytest.mark.asyncio
    async def test_album_parts_merged_into_one_turn(self):
        """Three updates in one group flush as a single merged album."""
        coalescer = _make_coalescer(window_ms=200)

        t1 = asyncio.create_task(
            coalescer.collect("grp1", ["/tmp/1.jpg"], "compare these")
        )
        await asyncio.sleep(0.02)
        t2 = asyncio.create_task(coalescer.collect("grp1", ["/tmp/2.jpg"], ""))
        await asyncio.sleep(0.02)
        t3 = asyncio.create_task(coalescer.collect("grp1", ["/tmp/3.jpg"], ""))

        results = await asyncio.gather(t1, t2, t3)

        # Exactly one caller owns the merged turn; siblings get None.
        owners = [r for r in results if r is not None]
        assert len(owners) == 1
        merged = owners[0]
        assert merged.attachments == ["/tmp/1.jpg", "/tmp/2.jpg", "/tmp/3.jpg"]
        # First non-empty caption is kept as the album prompt.
        assert merged.caption == "compare these"

    @pytest.mark.asyncio
    async def test_max_items_forces_immediate_flush(self):
        """Reaching max_items flushes without waiting for the window."""
        coalescer = _make_coalescer(window_ms=10_000, max_items=2)

        t1 = asyncio.create_task(coalescer.collect("grp1", ["/tmp/1.jpg"], "x"))
        await asyncio.sleep(0.02)
        t2 = asyncio.create_task(coalescer.collect("grp1", ["/tmp/2.jpg"], ""))

        # Should resolve quickly despite the 10s window because max_items=2.
        results = await asyncio.wait_for(asyncio.gather(t1, t2), timeout=1.0)
        owners = [r for r in results if r is not None]
        assert len(owners) == 1
        assert owners[0].attachments == ["/tmp/1.jpg", "/tmp/2.jpg"]

    @pytest.mark.asyncio
    async def test_separate_groups_do_not_mix(self):
        """Different media_group_ids flush independently."""
        coalescer = _make_coalescer(window_ms=150)
        a = asyncio.create_task(coalescer.collect("grpA", ["/tmp/a.jpg"], "A"))
        b = asyncio.create_task(coalescer.collect("grpB", ["/tmp/b.jpg"], "B"))
        ra, rb = await asyncio.gather(a, b)
        assert ra.attachments == ["/tmp/a.jpg"]
        assert rb.attachments == ["/tmp/b.jpg"]


    @pytest.mark.asyncio
    async def test_cancelled_owner_reclaims_album_on_window_flush(self):
        """Owner cancelled mid-wait -> the window flush reclaims buffered files."""
        reclaimed = []
        from praisonai_bot.bots._album import AlbumCoalescer

        coalescer = AlbumCoalescer(
            window_ms=80, max_items=10, on_orphan=reclaimed.extend
        )

        owner = asyncio.create_task(
            coalescer.collect("grp1", ["/tmp/1.jpg"], "x")
        )
        await asyncio.sleep(0.01)
        sibling = asyncio.create_task(coalescer.collect("grp1", ["/tmp/2.jpg"], ""))
        await asyncio.sleep(0.01)

        # Sibling folds in and returns None.
        assert await sibling is None

        # Cancel the owner while it is still awaiting the window flush.
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner

        # The silence-window flush fires next; with no live owner it reclaims
        # the whole merged album so no temp files leak.
        await asyncio.sleep(0.1)
        assert reclaimed == ["/tmp/1.jpg", "/tmp/2.jpg"]

    @pytest.mark.asyncio
    async def test_cancel_all_reclaims_orphan_when_no_owner(self):
        """Shutdown flush of an abandoned group reclaims its temp files."""
        reclaimed = []
        from praisonai_bot.bots._album import AlbumCoalescer

        coalescer = AlbumCoalescer(
            window_ms=10_000, max_items=10, on_orphan=reclaimed.extend
        )

        owner = asyncio.create_task(coalescer.collect("grp1", ["/tmp/1.jpg"], "x"))
        await asyncio.sleep(0.01)
        # Owner abandons its await before any flush.
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner

        # Shutdown flush: no live owner is awaiting -> files are reclaimed.
        coalescer.cancel_all()
        assert reclaimed == ["/tmp/1.jpg"]


class TestResolvers:
    def test_window_and_max_from_metadata(self):
        from praisonai_bot.bots._album import (
            resolve_album_window_ms,
            resolve_album_max_items,
        )

        class Cfg:
            metadata = {"media_group_window_ms": 1500, "media_group_max": 5}

        assert resolve_album_window_ms(Cfg()) == 1500
        assert resolve_album_max_items(Cfg()) == 5

    def test_defaults_when_unset(self):
        from praisonai_bot.bots._album import (
            resolve_album_window_ms,
            resolve_album_max_items,
        )

        class Cfg:
            metadata = {}

        assert resolve_album_window_ms(Cfg()) == 0
        assert resolve_album_max_items(Cfg()) == 10
