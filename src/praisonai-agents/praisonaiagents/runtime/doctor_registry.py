"""
Doctor rules registry with lazy plugin discovery.

Manages built-in and plugin-provided migration rules.
"""

import copy
import warnings
from typing import Any, Dict, List, Optional
from .doctor_protocol import (
    DoctorContractProtocol,
    Finding,
    ConfigDiff,
    RepairPlan,
)
from .builtin_rules import CliBackendMigrationRule


class DoctorRulesRegistry:
    """Registry for doctor migration rules with lazy plugin discovery."""
    
    def __init__(self):
        self._rules: List[DoctorContractProtocol] = []
        self._plugins_loaded = False
    
    def register_rule(self, rule: DoctorContractProtocol) -> None:
        """Register a migration rule."""
        if not isinstance(rule, DoctorContractProtocol):
            raise TypeError("Rule must implement DoctorContractProtocol")
        
        # Check for duplicate rule IDs
        for existing_rule in self._rules:
            if existing_rule.rule_id == rule.rule_id:
                warnings.warn(f"Duplicate rule ID '{rule.rule_id}' - replacing existing rule")
                self._rules.remove(existing_rule)
                break
        
        self._rules.append(rule)
    
    def get_rules(self) -> List[DoctorContractProtocol]:
        """Get all registered rules, loading plugins if not already loaded."""
        if not self._plugins_loaded:
            self._load_builtin_rules()
            self._load_plugin_rules()
            self._plugins_loaded = True
        
        return self._rules.copy()
    
    def get_rule(self, rule_id: str) -> Optional[DoctorContractProtocol]:
        """Get a specific rule by ID."""
        for rule in self.get_rules():
            if rule.rule_id == rule_id:
                return rule
        return None
    
    def collect_all_findings(self, config: Dict[str, Any]) -> List[Finding]:
        """Collect findings from all registered rules."""
        all_findings = []
        for rule in self.get_rules():
            try:
                findings = rule.collect_findings(config)
                all_findings.extend(findings)
            except Exception as e:
                # Log error but continue with other rules
                warnings.warn(f"Error in rule '{rule.rule_id}': {e}")
        
        return all_findings
    
    def apply_all_fixes(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply fixes from all rules that have findings.

        Backward-compatible convenience wrapper that returns only the repaired
        config dict. For the safety-rail surface (diff preview, backup, refuse,
        re-validation) use :meth:`plan_fixes`.
        """
        return self.plan_fixes(config).config

    def plan_fixes(
        self,
        config: Dict[str, Any],
        *,
        dry_run: bool = True,
        backup: bool = False,
        backup_path: Optional[str] = None,
    ) -> RepairPlan:
        """
        Produce a :class:`RepairPlan` describing what the doctor repair changes.

        Safety contract:
        - **Diff preview**: every applied rule records a before/after ``ConfigDiff``.
        - **Refuse-on-unrecoverable**: a rule that raises is skipped, its blocking
          finding(s) recorded in ``refused``, and its partial change discarded.
        - **Backup**: when ``dry_run=False`` and ``backup=True`` the original
          config is snapshotted to ``backup_path`` before returning.
        - **Re-validation**: after applying, residual findings are re-collected so
          callers can report "repair left N finding(s)".

        Args:
            config: The configuration to repair (never mutated).
            dry_run: When True (default) nothing is written to disk; the plan's
                ``config`` holds the proposed result for previewing.
            backup: When True (and not dry_run), write a timestamped backup of
                the original config before applying.
            backup_path: Explicit backup destination. If omitted a timestamped
                path is derived.

        Returns:
            A :class:`RepairPlan`.
        """
        result = copy.deepcopy(config)
        diffs: List[ConfigDiff] = []
        refused: List[Finding] = []

        for rule in self.get_rules():
            try:
                findings = rule.collect_findings(result)
            except Exception as e:
                warnings.warn(f"Error collecting findings for rule '{rule.rule_id}': {e}")
                continue

            if not findings:
                continue

            before = copy.deepcopy(result)
            try:
                fixed = rule.apply_fix(before)
            except Exception as e:
                # Refuse-on-unrecoverable: discard this rule's change, preserve
                # the prior state, and record the blocking finding(s).
                warnings.warn(f"Refusing fix for rule '{rule.rule_id}': {e}")
                refused.append(Finding(
                    rule_id=rule.rule_id,
                    severity="error",
                    message=f"Refused to apply fix (unrecoverable): {e}",
                    fix_description=None,
                    context={"error": str(e)},
                ))
                continue

            if fixed != before:
                diffs.append(ConfigDiff(rule_id=rule.rule_id, before=before, after=copy.deepcopy(fixed)))
                result = fixed

        residual_findings = self.collect_all_findings(result)

        written_backup_path: Optional[str] = None
        if not dry_run and backup and diffs:
            written_backup_path = self._write_backup(config, backup_path)

        return RepairPlan(
            config=result,
            diffs=diffs,
            backup_path=written_backup_path,
            residual_findings=residual_findings,
            refused=refused,
            applied=not dry_run,
        )

    @staticmethod
    def _write_backup(config: Dict[str, Any], backup_path: Optional[str]) -> str:
        """Snapshot the original config to a timestamped backup file."""
        import json
        from datetime import datetime

        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"doctor-config.bak-{timestamp}.json"

        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, sort_keys=True, default=str)

        return backup_path
    
    def _load_builtin_rules(self) -> None:
        """Load built-in migration rules."""
        # Register built-in cli_backend migration rule
        self.register_rule(CliBackendMigrationRule())
    
    def _load_plugin_rules(self) -> None:
        """Discover and load plugin-provided rules via entry points."""
        # Prioritize importlib.metadata over pkg_resources for better performance
        try:
            from importlib.metadata import entry_points
            eps = entry_points()
            if hasattr(eps, 'select'):
                doctor_eps = eps.select(group='praisonai.doctor_contracts')
            else:
                doctor_eps = eps.get('praisonai.doctor_contracts', [])
            
            for entry_point in doctor_eps:
                try:
                    rule_class = entry_point.load()
                    if callable(rule_class):
                        rule_instance = rule_class()
                        self.register_rule(rule_instance)
                except Exception as e:
                    warnings.warn(f"Failed to load doctor rule from {entry_point.name}: {e}")
        except ImportError:
            # Fallback to pkg_resources if importlib.metadata not available
            try:
                import pkg_resources
                for entry_point in pkg_resources.iter_entry_points('praisonai.doctor_contracts'):
                    try:
                        rule_class = entry_point.load()
                        if callable(rule_class):
                            rule_instance = rule_class()
                            self.register_rule(rule_instance)
                    except Exception as e:
                        warnings.warn(f"Failed to load doctor rule from {entry_point.name}: {e}")
            except ImportError:
                pass  # No plugin system available


# Global registry singleton
_default_registry: Optional[DoctorRulesRegistry] = None


def get_default_registry() -> DoctorRulesRegistry:
    """Get the default doctor rules registry (singleton)."""
    global _default_registry
    if _default_registry is None:
        _default_registry = DoctorRulesRegistry()
    return _default_registry


def register_rule(rule: DoctorContractProtocol) -> None:
    """Register a rule with the default registry."""
    get_default_registry().register_rule(rule)


def get_rules() -> List[DoctorContractProtocol]:
    """Get all rules from the default registry."""
    return get_default_registry().get_rules()


def collect_findings(config: Dict[str, Any]) -> List[Finding]:
    """Collect findings from all rules in the default registry."""
    return get_default_registry().collect_all_findings(config)


def apply_fixes(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply fixes from all rules in the default registry."""
    return get_default_registry().apply_all_fixes(config)


def plan_fixes(
    config: Dict[str, Any],
    *,
    dry_run: bool = True,
    backup: bool = False,
    backup_path: Optional[str] = None,
) -> RepairPlan:
    """Produce a RepairPlan from all rules in the default registry."""
    return get_default_registry().plan_fixes(
        config, dry_run=dry_run, backup=backup, backup_path=backup_path
    )