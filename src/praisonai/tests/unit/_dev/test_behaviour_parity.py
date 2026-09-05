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


# The surfaces the TypeScript code iterates. read_ledger cross-checks the parse
# against these, so every fixture repo carries them.
CALL_SITES = (
    "const a = unhonouredFor('Agent.__init__');\n"
    "const t = unhonouredFor('Task.__init__');\n"
)


def _repo(
    tmp_path: Path,
    ledger: str = LEDGER,
    extra: str = '',
    call_sites: str = CALL_SITES,
) -> Path:
    src = tmp_path / 'src' / 'praisonai-ts' / 'src' / 'utils'
    src.mkdir(parents=True)
    (src / 'parity-notice.ts').write_text(ledger)
    if extra:
        (src.parent / 'agent.ts').write_text(extra)
    if call_sites:
        (src.parent / 'call-sites.ts').write_text(call_sites)
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


# ---------------------------------------------------------------------------
# A partial parse failure must never read as progress.
#
# The first version matched entries with a line-anchored regex that required a
# trailing comma after the closing bracket. Putting one entry on a single line
# without that comma dropped the whole surface: 48 -> 40, reported as "8
# option(s) closed", and --write made it the new floor with the TypeScript
# unchanged. A surface disappearing is a parse error, never a win.
# ---------------------------------------------------------------------------

ONE_LINE_LEDGER = textwrap.dedent('''
    export const UNHONOURED_OPTIONS: Readonly<Record<string, readonly string[]>> = {
      'Agent.__init__': ['auth', 'sandbox'],
      'Task.__init__': ['images']
    } as const;
''')


class TestReformatCannotCloseOptions:
    def test_a_one_line_entry_without_a_trailing_comma_is_still_counted(self, tmp_path):
        b = B.read_ledger(_repo(tmp_path, ledger=ONE_LINE_LEDGER))
        assert b.surfaces == {'Agent.__init__': ['auth', 'sandbox'], 'Task.__init__': ['images']}
        assert b.total == 3, 'whitespace changed; the number of ignored options did not'

    def test_reformatting_does_not_lower_the_total(self, tmp_path, capsys):
        repo = _repo(tmp_path)
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        (repo / 'src/praisonai-ts/src/utils/parity-notice.ts').write_text(ONE_LINE_LEDGER)
        assert B.main(['--check', '--repo-root', str(repo)]) == 0
        out = capsys.readouterr().out
        assert 'closed since the last commit' not in out

    def test_trailing_commas_and_comments_are_both_tolerated(self, tmp_path):
        ledger = textwrap.dedent('''
            export const UNHONOURED_OPTIONS: Readonly<Record<string, readonly string[]>> = {
              // 'Ghost': ['notAKey'],
              /* 'AlsoGhost': ['notAKey'] */
              'Agent.__init__': [
                'auth',   // still ignored
                'sandbox',
              ],
              'Task.__init__': ['images'],
            } as const;
        ''')
        b = B.read_ledger(_repo(tmp_path, ledger=ledger))
        assert sorted(b.surfaces) == ['Agent.__init__', 'Task.__init__']
        assert b.total == 3

    def test_a_surface_the_code_iterates_but_the_parse_lost_is_an_error(self):
        """The guard itself: a key in the ledger text, gone from the parse."""
        body = "'Agent.__init__': ['auth'],\n'Handoff': ['maxDepth'],\n"
        with pytest.raises(B.LedgerError, match='Handoff'):
            B._verify_parse(body, {'Agent.__init__': ['auth']}, ['Agent.__init__', 'Handoff'])

    def test_a_surface_absent_from_the_ledger_is_closed_not_lost(self, tmp_path):
        """Control: code may iterate a surface whose entry was legitimately deleted."""
        b = B.read_ledger(_repo(
            tmp_path,
            call_sites=CALL_SITES + "const h = unhonouredFor('Handoff');\n",
        ))
        assert 'Handoff' not in b.surfaces
        assert b.total == 3

    def test_the_independent_key_count_must_agree_with_the_parse(self):
        body = "'Agent.__init__': ['auth'],\n'Task.__init__': ['images'],\n"
        with pytest.raises(B.LedgerError, match='Task.__init__'):
            B._verify_parse(body, {'Agent.__init__': ['auth']}, [])

    def test_an_entry_whose_value_is_not_a_list_is_an_error(self, tmp_path):
        ledger = LEDGER.replace("'Task.__init__': [\n    'images',\n  ],", "'Task.__init__': someExpr,")
        assert 'someExpr' in ledger
        with pytest.raises(B.LedgerError, match='not a list'):
            B.read_ledger(_repo(tmp_path, ledger=ledger))

    def test_a_duplicate_surface_key_is_an_error(self, tmp_path):
        ledger = LEDGER.replace("'Task.__init__'", "'Agent.__init__'")
        with pytest.raises(B.LedgerError, match='twice'):
            B.read_ledger(_repo(tmp_path, ledger=ledger))


# ---------------------------------------------------------------------------
# --write must not launder a ratchet rise.
# ---------------------------------------------------------------------------

class TestWriteRespectsTheRatchet:
    @staticmethod
    def _grow(repo: Path) -> None:
        (repo / 'src/praisonai-ts/src/utils/parity-notice.ts').write_text(
            LEDGER.replace("'auth', 'sandbox',", "'auth', 'sandbox', 'newlyIgnored',")
        )

    def test_write_refuses_to_raise_the_committed_total(self, tmp_path, capsys):
        repo = _repo(tmp_path)
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        self._grow(repo)
        assert B.main(['--write', '--repo-root', str(repo)]) == 1
        assert B.committed_total(repo) == 3, 'the committed floor must not have moved'
        assert '--allow-growth' in capsys.readouterr().err

    def test_allow_growth_banks_the_rise(self, tmp_path):
        repo = _repo(tmp_path)
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        self._grow(repo)
        assert B.main(['--write', '--allow-growth', '--repo-root', str(repo)]) == 0
        assert B.committed_total(repo) == 4

    def test_write_may_always_lower_the_total(self, tmp_path):
        """Control: closing an option needs no flag."""
        repo = _repo(tmp_path)
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        (repo / 'src/praisonai-ts/src/utils/parity-notice.ts').write_text(
            LEDGER.replace("'auth', 'sandbox',", "'auth',")
        )
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        assert B.committed_total(repo) == 2

    def test_the_first_write_has_no_floor_to_break(self, tmp_path):
        """Control: no committed report yet is not growth."""
        assert B.main(['--write', '--repo-root', str(_repo(tmp_path))]) == 0

    def test_write_names_the_options_it_claims_closed(self, tmp_path, capsys):
        repo = _repo(tmp_path)
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        (repo / 'src/praisonai-ts/src/utils/parity-notice.ts').write_text(
            LEDGER.replace("'auth', 'sandbox',", "'auth',")
        )
        assert B.main(['--write', '--repo-root', str(repo)]) == 0
        out = capsys.readouterr().out
        assert 'Agent.__init__.sandbox' in out


# ---------------------------------------------------------------------------
# The gate must run on the files that carry the baseline.
# ---------------------------------------------------------------------------

def _real_repo_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / 'src' / 'praisonai-ts').is_dir() and (parent / '.github').is_dir():
            return parent
    return None


class TestGateWatchesTheReport:
    def test_the_pull_request_filter_covers_the_behaviour_baseline(self):
        root = _real_repo_root()
        if root is None:
            pytest.skip('not running inside a checkout with .github/workflows')
        yaml = pytest.importorskip('yaml')
        data = yaml.safe_load((root / '.github/workflows/parity-gate.yml').read_text())
        # PyYAML reads the bare key `on` as the boolean True (YAML 1.1).
        triggers = data.get('on', data.get(True))
        paths = triggers['pull_request']['paths']
        for required in (
            'src/praisonai-ts/BEHAVIOUR_PARITY.md',
            'src/praisonai-ts/behaviour-parity.json',
            'src/praisonai/scripts/**',
        ):
            assert required in paths, f'{required} can change without the gate running'


class TestQuotingCannotHideASurface:
    """JavaScript takes ' " and `; a style the parser missed dropped a surface."""

    def test_a_double_quoted_key_is_still_a_surface(self, tmp_path):
        ledger = LEDGER.replace("'Task.__init__':", '"Task.__init__":')
        b = B.read_ledger(_repo(tmp_path, ledger=ledger))
        assert b.surfaces['Task.__init__'] == ['images']
        assert b.total == 3

    def test_a_double_quoted_option_is_still_counted(self, tmp_path):
        ledger = LEDGER.replace("'sandbox',", '"sandbox",')
        b = B.read_ledger(_repo(tmp_path, ledger=ledger))
        assert b.surfaces['Agent.__init__'] == ['auth', 'sandbox']

    def test_an_option_name_that_is_not_an_identifier_is_an_error(self, tmp_path):
        """Control: a name the option regex cannot read must not vanish quietly."""
        ledger = LEDGER.replace("'images',", "'output-file',")
        with pytest.raises(B.LedgerError, match='not a plain identifier'):
            B.read_ledger(_repo(tmp_path, ledger=ledger))
