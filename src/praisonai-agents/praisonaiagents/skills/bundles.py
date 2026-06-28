"""Skill bundles: named, reusable sets of skills.

A *bundle* is a small manifest that references existing skills by name and is
itself selectable as one unit. It is composition over the existing skills
layer — not a new execution primitive. A bundle expands to its member skills,
which then flow through the unchanged budget + prompt-injection path.

Bundles are discovered alongside skills:
- a top-level ``BUNDLE.yaml`` / ``BUNDLE.yml`` inside a skill directory, or
- any ``*.yaml`` / ``*.yml`` file inside a ``bundles/`` subdirectory of a
  skill root.

Selection uses a ``@`` marker everywhere a skill is selected
(``skills=["@backend-dev"]``), mirroring how skills already behave:
forgiving membership, precedence-with-logging, and budget-awareness.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .discovery import get_default_skill_dirs

logger = logging.getLogger(__name__)

BUNDLE_MARKER = "@"


@dataclass
class BundleManifest:
    """A named set of skills selectable as one unit.

    Attributes:
        name: Bundle name (kebab-case, like a skill name).
        description: What the bundle is for.
        skills: Member skill names referenced by the bundle.
        instruction: Optional extra guidance loaded above the member skills.
        path: Path to the manifest file (set on discovery).
    """

    name: str
    description: str = ""
    skills: List[str] = field(default_factory=list)
    instruction: Optional[str] = None
    path: Optional[Path] = None

    @classmethod
    def from_dict(cls, data: dict, path: Optional[Path] = None) -> "BundleManifest":
        """Build a BundleManifest from a parsed mapping.

        Tolerant of both ``skills`` (preferred) and ``members`` keys for the
        member list, and accepts a string or list for the members.
        """
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Bundle manifest must define a 'name'")

        members = data.get("skills")
        if members is None:
            members = data.get("members")
        skills = _normalize_members(members)

        return cls(
            name=name,
            description=str(data.get("description") or ""),
            skills=skills,
            instruction=(str(data["instruction"]) if data.get("instruction") else None),
            path=path,
        )


def _normalize_members(value) -> List[str]:
    """Normalize a member list to a list of clean skill-name strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace(",", " ").split()
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def strip_bundle_marker(selector: str) -> str:
    """Return the bundle name for a ``@name`` selector (or the name itself)."""
    s = selector.strip()
    return s[len(BUNDLE_MARKER):] if s.startswith(BUNDLE_MARKER) else s


def is_bundle_selector(selector: str) -> bool:
    """True if ``selector`` is a ``@bundle`` reference."""
    return isinstance(selector, str) and selector.strip().startswith(BUNDLE_MARKER)


def _load_manifest_file(file_path: Path) -> Optional[BundleManifest]:
    """Load a single bundle manifest from a YAML file, tolerantly."""
    try:
        import yaml  # type: ignore
    except ImportError:
        logger.warning(
            "PyYAML is required to parse bundle manifests. "
            "Install it with: pip install PyYAML"
        )
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, Exception) as exc:  # noqa: BLE001 - tolerant discovery
        logger.warning("Skipping invalid bundle %s: %s", file_path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("Skipping bundle %s: manifest is not a mapping", file_path)
        return None
    try:
        return BundleManifest.from_dict(data, path=file_path)
    except Exception as exc:  # noqa: BLE001 - tolerant discovery
        logger.warning("Skipping invalid bundle %s: %s", file_path, exc)
        return None


def _iter_bundle_files(root: Path):
    """Yield candidate bundle-manifest files under a single skill root."""
    # bundles/ subdirectory of the root
    bundles_dir = root / "bundles"
    if bundles_dir.exists() and bundles_dir.is_dir():
        try:
            for item in sorted(bundles_dir.iterdir()):
                if item.is_file() and item.suffix.lower() in (".yaml", ".yml"):
                    yield item
        except PermissionError as exc:
            logger.warning("Cannot read bundles directory %s: %s", bundles_dir, exc)

    # BUNDLE.yaml inside each skill subdirectory
    try:
        for item in sorted(root.iterdir()):
            if not item.is_dir():
                continue
            for name in ("BUNDLE.yaml", "BUNDLE.yml", "bundle.yaml", "bundle.yml"):
                candidate = item / name
                if candidate.exists() and candidate.is_file():
                    yield candidate
                    break
    except PermissionError as exc:
        logger.warning("Cannot read skills directory %s: %s", root, exc)


def discover_bundles(
    skill_dirs: Optional[List[str]] = None,
    include_defaults: bool = True,
) -> List[BundleManifest]:
    """Discover bundle manifests alongside skills.

    Mirrors :func:`discovery.discover_skills`: scans the same roots, is
    forgiving of invalid manifests, and reports name collisions (first
    wins, later entries shadowed-and-logged).

    Args:
        skill_dirs: Explicit skill-root directories to scan.
        include_defaults: Whether to include default skill directories.

    Returns:
        List of discovered BundleManifest objects.
    """
    all_dirs: List[Path] = []

    if skill_dirs:
        for d in skill_dirs:
            path = Path(d).expanduser().resolve()
            if path.exists() and path.is_dir():
                all_dirs.append(path)

    if include_defaults:
        all_dirs.extend(get_default_skill_dirs())

    seen_dirs = set()
    unique_dirs: List[Path] = []
    for d in all_dirs:
        if d not in seen_dirs:
            seen_dirs.add(d)
            unique_dirs.append(d)

    bundles: List[BundleManifest] = []
    for root in unique_dirs:
        for file_path in _iter_bundle_files(root):
            manifest = _load_manifest_file(file_path)
            if manifest is None:
                continue
            if any(b.name == manifest.name for b in bundles):
                logger.info(
                    "Bundle '%s' at %s shadowed by earlier entry (precedence).",
                    manifest.name, file_path,
                )
                continue
            bundles.append(manifest)

    return bundles
