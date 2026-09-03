"""Tests for the behaviour-parity ratchet.

Each positive is paired with a control, because a ratchet that cannot fail is
the thing it was built to prevent.
"""

import json
import textwrap
from pathlib import Path

import pytest

from praisonai._dev.parity import behaviour as B

LEDGER = textwrap.dedent('''
    export const UNHONOURED_OPTIONS: Readonly<Record<string, readonly string[]>> = {
      'Agent.__init__': [
        'auth', 'sandbox',
      ],
      'Task.__init__': [
        'images',
      ],
    } as const;
''')


def _repo(tmp_path: Path, ledger: str = LEDGER, extra: str = '') -> Path:
    src = tmp_path / 'src' / 'praisonai-ts' / 'src' / 'utils'
    src.mkdir(parents=True)
    (src / 'parity-notice.ts').write_text(ledger)
    if extra:
        (src.parent / 'agent.ts').write_text(extra)
    return tmp_path


class TestReadLedger:
    def test_counts_every_surface(self, tmp_path):
        b = B.read_ledger(_repo(tmp_path))
        assert b.surfaces == {'Agent.__init__': ['auth', 'sandbox'], 'Task.__init__': ['images']}
        assert b.total == 3

    def test_partial_cases_are_collected_separately(self, tmp_path):
        repo = _repo(tmp_path, extra="notYetHonoured('Agent', 'memory', 'presets are not ported');")
        b = B.read_ledger(repo)
        assert b.total == 3, 'a partial case is not a wholly unhonoured option'
        assert b.partial == [{'surface': 'Agent', 'option': 'memory', 'file': 'src/praisonai-ts/src/agent.ts'}]

    def test_a_renamed_ledger_fails_loudly(self, tmp_path):
        """Control: an unreadable ledger must never read as zero outstanding."""
        repo = _repo(tmp_path, ledger=LEDGER.replace('UNHONOURED_OPTIONS', 'SOMETHING_ELSE'))
        with pytest.raises(B.LedgerError, match='no longer declares'):
            B.read_ledger(repo)

    def test_an_empty_ledger_fails_rather_than_reporting_zero(self, tmp_path):
        empty = 'export const UNHONOURED_OPTIONS: Readonly<Record<string, readonly string[]>> = {\n} as const;\n'
        with pytest.raises(B.LedgerError, match='no surfaces parsed'):
            B.read_ledger(_repo(tmp_path, ledger=empty))


class TestRatchet:
    @staticmethod
    def _write(repo: Path) -> int:
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        return B.committed_total(repo)

    def test_unchanged_total_passes(self, tmp_path):
        repo = _repo(tmp_path)
        assert self._write(repo) == 3
        assert B.main(['--check', '--repo-root', str(repo)]) == 0

    def test_a_grown_total_fails(self, tmp_path, capsys):
        repo = _repo(tmp_path)
        self._write(repo)
        ledger = repo / 'src/praisonai-ts/src/utils/parity-notice.ts'
        ledger.write_text(LEDGER.replace("'auth', 'sandbox',", "'auth', 'sandbox', 'newlyIgnored',"))
        assert B.main(['--check', '--repo-root', str(repo)]) == 1
        assert 'up from 3' in capsys.readouterr().out

    def test_closing_one_reports_the_improvement(self, tmp_path, capsys):
        repo = _repo(tmp_path)
        self._write(repo)
        ledger = repo / 'src/praisonai-ts/src/utils/parity-notice.ts'
        ledger.write_text(LEDGER.replace("'auth', 'sandbox',", "'auth',"))
        # Still exit 1: the committed report must be regenerated to bank it.
        assert B.main(['--check', '--repo-root', str(repo)]) == 1
        out = capsys.readouterr().out
        assert '1 option(s) closed' in out and '3 -> 2' in out
        assert 'up from' not in out, 'closing an option must not read as a regression'

    def test_a_missing_report_fails(self, tmp_path):
        """Control: no committed baseline is a failure, not a free pass."""
        assert B.main(['--check', '--repo-root', str(_repo(tmp_path))]) == 1

    def test_an_unreadable_ledger_exits_two_not_zero(self, tmp_path, capsys):
        repo = _repo(tmp_path, ledger=LEDGER.replace('UNHONOURED_OPTIONS', 'GONE'))
        assert B.main(['--check', '--repo-root', str(repo)]) == 2
        assert 'cannot read the ledger' in capsys.readouterr().err

    def test_written_json_carries_the_total_and_surfaces(self, tmp_path):
        repo = _repo(tmp_path)
        self._write(repo)
        data = json.loads((repo / B.JSON_OUTPUT).read_text())
        assert data['total'] == 3
        assert data['surfaces']['Agent.__init__'] == ['auth', 'sandbox']
