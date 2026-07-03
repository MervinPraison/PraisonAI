"""Regression tests for durable delivery module wiring."""

import pytest


@pytest.mark.parametrize(
    "attr",
    ["DurableDelivery", "deliver_with_retry", "deliver_chunked", "DurableAdapterMixin"],
)
def test_bots_package_exports_delivery_symbols(attr):
    """PR #2054 removed _delivery.py while exports still referenced it."""
    import praisonai_bot.bots as bots

    assert hasattr(bots, attr)
    assert getattr(bots, attr) is not None


def test_durable_adapter_imports_delivery_class():
    from praisonai_bot.bots._durable_adapter import DurableAdapterMixin
    from praisonai_bot.bots._delivery import DurableDelivery

    mixin = DurableAdapterMixin()
    mixin.setup_durable_delivery(outbox_path=None, platform="test")
    assert mixin.durable_delivery is None

    assert DurableDelivery is not None
