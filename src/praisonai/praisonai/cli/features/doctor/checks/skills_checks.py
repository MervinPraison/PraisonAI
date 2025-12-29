"""
Skills checks for the Doctor CLI module.

Validates Agent Skills configurations and manifests.
"""

from pathlib import Path

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


def _find_skills_dirs() -> list:
    """Find skills directories."""
    locations = [
        Path.cwd() / ".praison" / "skills",
        Path.cwd() / ".claude" / "skills",
        Path.home() / ".praison" / "skills",
        Path.home() / ".config" / "praison" / "skills",
    ]
    
    found = []
    for loc in locations:
        if loc.exists() and loc.is_dir():
            found.append(str(loc))
    
    return found


def _validate_skill_dir(skill_path: Path) -> dict:
    """Validate a single skill directory."""
    result = {"valid": False, "errors": [], "warnings": []}
    
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        result["errors"].append("Missing SKILL.md")
        return result
    
    try:
        content = skill_md.read_text()
        
        # Check for YAML frontmatter
        if not content.startswith("---"):
            result["errors"].append("SKILL.md missing YAML frontmatter")
            return result
        
        # Parse frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            result["errors"].append("Invalid YAML frontmatter format")
            return result
        
        try:
            import yaml
            frontmatter = yaml.safe_load(parts[1])
            
            # Check required fields
            if not frontmatter.get("name"):
                result["errors"].append("Missing 'name' in frontmatter")
            if not frontmatter.get("description"):
                result["errors"].append("Missing 'description' in frontmatter")
            
            # Check name format
            name = frontmatter.get("name", "")
            if name and not name.replace("-", "").replace("_", "").isalnum():
                result["warnings"].append(f"Name '{name}' should be alphanumeric with hyphens")
            
            if not result["errors"]:
                result["valid"] = True
                result["name"] = name
                result["description"] = frontmatter.get("description", "")[:100]
            
        except Exception as e:
            result["errors"].append(f"YAML parse error: {e}")
    
    except Exception as e:
        result["errors"].append(f"Cannot read SKILL.md: {e}")
    
    return result


@register_check(
    id="skills_dirs",
    title="Skills Directories",
    description="Check for skills directories",
    category=CheckCategory.SKILLS,
    severity=CheckSeverity.INFO,
)
def check_skills_dirs(config: DoctorConfig) -> CheckResult:
    """Check for skills directories."""
    dirs = _find_skills_dirs()
    
    if config.path:
        # Check specific path
        path = Path(config.path)
        if path.exists():
            dirs = [str(path)]
        else:
            return CheckResult(
                id="skills_dirs",
                title="Skills Directories",
                category=CheckCategory.SKILLS,
                status=CheckStatus.FAIL,
                message=f"Specified path not found: {config.path}",
            )
    
    if dirs:
        return CheckResult(
            id="skills_dirs",
            title="Skills Directories",
            category=CheckCategory.SKILLS,
            status=CheckStatus.PASS,
            message=f"Found {len(dirs)} skills directory(ies)",
            details=", ".join(dirs),
            metadata={"directories": dirs},
        )
    else:
        return CheckResult(
            id="skills_dirs",
            title="Skills Directories",
            category=CheckCategory.SKILLS,
            status=CheckStatus.SKIP,
            message="No skills directories found (optional)",
            details="Create .praison/skills/ to add agent skills",
        )


@register_check(
    id="skills_valid",
    title="Skills Validation",
    description="Validate installed skills",
    category=CheckCategory.SKILLS,
    severity=CheckSeverity.MEDIUM,
    dependencies=["skills_dirs"],
)
def check_skills_valid(config: DoctorConfig) -> CheckResult:
    """Validate installed skills."""
    dirs = _find_skills_dirs()
    
    if config.path:
        path = Path(config.path)
        if path.exists():
            dirs = [str(path)]
    
    if not dirs:
        return CheckResult(
            id="skills_valid",
            title="Skills Validation",
            category=CheckCategory.SKILLS,
            status=CheckStatus.SKIP,
            message="No skills to validate",
        )
    
    valid_skills = []
    invalid_skills = []
    
    for dir_path in dirs:
        skills_dir = Path(dir_path)
        for skill_path in skills_dir.iterdir():
            if skill_path.is_dir() and not skill_path.name.startswith("."):
                result = _validate_skill_dir(skill_path)
                if result["valid"]:
                    valid_skills.append(result.get("name", skill_path.name))
                else:
                    invalid_skills.append(f"{skill_path.name}: {'; '.join(result['errors'])}")
    
    total = len(valid_skills) + len(invalid_skills)
    
    if total == 0:
        return CheckResult(
            id="skills_valid",
            title="Skills Validation",
            category=CheckCategory.SKILLS,
            status=CheckStatus.SKIP,
            message="No skills found in directories",
        )
    
    if invalid_skills:
        return CheckResult(
            id="skills_valid",
            title="Skills Validation",
            category=CheckCategory.SKILLS,
            status=CheckStatus.WARN,
            message=f"{len(valid_skills)}/{total} skills valid",
            details="; ".join(invalid_skills[:3]) + ("..." if len(invalid_skills) > 3 else ""),
            metadata={"valid": valid_skills, "invalid": invalid_skills},
        )
    else:
        return CheckResult(
            id="skills_valid",
            title="Skills Validation",
            category=CheckCategory.SKILLS,
            status=CheckStatus.PASS,
            message=f"All {total} skill(s) valid",
            metadata={"valid": valid_skills},
        )


@register_check(
    id="skills_praisonai_integration",
    title="PraisonAI Skills Integration",
    description="Check PraisonAI skills module",
    category=CheckCategory.SKILLS,
    severity=CheckSeverity.LOW,
)
def check_skills_praisonai_integration(config: DoctorConfig) -> CheckResult:
    """Check PraisonAI skills module."""
    try:
        from praisonaiagents.skills import SkillManager
        return CheckResult(
            id="skills_praisonai_integration",
            title="PraisonAI Skills Integration",
            category=CheckCategory.SKILLS,
            status=CheckStatus.PASS,
            message="PraisonAI skills module available",
        )
    except ImportError as e:
        return CheckResult(
            id="skills_praisonai_integration",
            title="PraisonAI Skills Integration",
            category=CheckCategory.SKILLS,
            status=CheckStatus.SKIP,
            message="Skills module not available",
            details=str(e),
        )
