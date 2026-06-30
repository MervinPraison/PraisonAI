"""Unit tests for the gateway restart-intent exit-code protocol (Issue #2437).

Covers the pure, core-side constants, the FatalConfigError type, and the
classify_exit_reason() classifier that the wrapper CLI and runtime entry
point share to tell a process supervisor whether restarting is worthwhile.
"""

from praisonaiagents.gateway import (
    GATEWAY_FATAL_CONFIG_EXIT_CODE,
    GATEWAY_OK_EXIT_CODE,
    GATEWAY_RESTART_EXIT_CODE,
    FatalConfigError,
    classify_exit_reason,
)


def test_constants_follow_sysexits():
    # EX_OK / EX_TEMPFAIL / EX_CONFIG from sysexits.h.
    assert GATEWAY_OK_EXIT_CODE == 0
    assert GATEWAY_RESTART_EXIT_CODE == 75
    assert GATEWAY_FATAL_CONFIG_EXIT_CODE == 78


def test_fatal_config_error_is_exception():
    assert issubclass(FatalConfigError, Exception)


def test_none_is_clean_exit():
    assert classify_exit_reason(None) == GATEWAY_OK_EXIT_CODE


def test_keyboard_interrupt_is_clean_exit():
    assert classify_exit_reason(KeyboardInterrupt()) == GATEWAY_OK_EXIT_CODE


def test_system_exit_zero_is_clean():
    assert classify_exit_reason(SystemExit(0)) == GATEWAY_OK_EXIT_CODE
    assert classify_exit_reason(SystemExit(None)) == GATEWAY_OK_EXIT_CODE


def test_system_exit_preserves_explicit_int_code():
    assert classify_exit_reason(SystemExit(3)) == 3


def test_system_exit_non_int_is_restartable():
    assert classify_exit_reason(SystemExit("boom")) == GATEWAY_RESTART_EXIT_CODE


def test_fatal_config_error_maps_to_config_code():
    assert (
        classify_exit_reason(FatalConfigError("duplicate token"))
        == GATEWAY_FATAL_CONFIG_EXIT_CODE
    )


def test_transient_errors_map_to_restart_code():
    for exc in (ConnectionError("503"), TimeoutError(), RuntimeError("blip")):
        assert classify_exit_reason(exc) == GATEWAY_RESTART_EXIT_CODE


def test_fatal_and_transient_codes_are_distinct():
    # The whole point of #2437: a misconfig must not look like a blip.
    assert GATEWAY_FATAL_CONFIG_EXIT_CODE != GATEWAY_RESTART_EXIT_CODE
