"""
Starter template scaffolding for deploy projects.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml

from ._infra import STARTERS_INDEX, resolve_starters_root as _resolve_starters_root
from .models import DeployResult


def resolve_starters_root(starters_root: Optional[str] = None, cwd: Optional[Path] = None) -> Path:
    return _resolve_starters_root(starters_root=starters_root, cwd=cwd)


def list_templates(starters_root: Optional[str] = None) -> List[Dict[str, str]]:
    root = resolve_starters_root(starters_root)
    with open(root / STARTERS_INDEX, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("templates", []))


def create_from_template(
    template: str,
    directory: str = ".",
    starters_root: Optional[str] = None,
) -> DeployResult:
    """Copy a starter template into the target directory."""
    import shutil

    try:
        root = resolve_starters_root(starters_root)
        templates = {t["name"]: t for t in list_templates(str(root))}
        if template not in templates:
            available = ", ".join(sorted(templates)) or "(none)"
            return DeployResult(
                success=False,
                message=f"Unknown template: {template}",
                error=f"Available templates: {available}",
            )

        meta = templates[template]
        src = root / meta["path"]
        if not src.is_dir():
            return DeployResult(
                success=False,
                message=f"Template source missing: {src}",
                error=str(src),
            )

        dest = Path(directory).expanduser().resolve()
        dest.mkdir(parents=True, exist_ok=True)

        copied: List[str] = []
        for item in src.iterdir():
            target = dest / item.name
            if item.is_dir():
                if target.exists():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
            copied.append(item.name)

        return DeployResult(
            success=True,
            message=f"Created project from template '{template}' in {dest}",
            metadata={
                "template": template,
                "directory": str(dest),
                "files": copied,
                "description": meta.get("description", ""),
            },
        )
    except FileNotFoundError as e:
        return DeployResult(success=False, message=str(e), error=str(e))
    except Exception as e:
        return DeployResult(success=False, message="Template create failed", error=str(e))
