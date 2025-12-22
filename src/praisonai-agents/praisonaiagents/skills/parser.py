"""YAML frontmatter parsing for SKILL.md files."""

from pathlib import Path
from typing import Optional, Tuple
import re

from .models import ParseError, ValidationError, SkillProperties


def find_skill_md(skill_dir: Path) -> Optional[Path]:
    """Find the SKILL.md file in a skill directory.

    Prefers SKILL.md (uppercase) but accepts skill.md (lowercase).

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Path to the SKILL.md file, or None if not found
    """
    for name in ("SKILL.md", "skill.md"):
        path = skill_dir / name
        if path.exists():
            return path
    return None


def parse_frontmatter(content: str) -> Tuple[dict, str]:
    """Parse YAML frontmatter from SKILL.md content.

    Args:
        content: Raw content of SKILL.md file

    Returns:
        Tuple of (metadata dict, markdown body)

    Raises:
        ParseError: If frontmatter is missing or invalid
    """
    if not content.startswith("---"):
        raise ParseError("SKILL.md must start with YAML frontmatter (---)")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ParseError("SKILL.md frontmatter not properly closed with ---")

    frontmatter_str = parts[1]
    body = parts[2].strip()

    try:
        metadata = _parse_yaml(frontmatter_str)
    except Exception as e:
        raise ParseError(f"Invalid YAML in frontmatter: {e}")

    if not isinstance(metadata, dict):
        raise ParseError("SKILL.md frontmatter must be a YAML mapping")

    # Convert metadata values to strings where needed
    if "metadata" in metadata and isinstance(metadata["metadata"], dict):
        metadata["metadata"] = {str(k): str(v) for k, v in metadata["metadata"].items()}

    return metadata, body


def _parse_yaml(yaml_str: str) -> dict:
    """Parse YAML string to dictionary.
    
    Uses a simple parser to avoid strictyaml dependency.
    Falls back to yaml if available.
    
    Args:
        yaml_str: YAML string to parse
        
    Returns:
        Parsed dictionary
    """
    # Try to use PyYAML if available
    try:
        import yaml
        return yaml.safe_load(yaml_str) or {}
    except ImportError:
        pass
    
    # Simple fallback parser for basic YAML
    result = {}
    current_key = None
    current_dict = None
    
    for line in yaml_str.strip().split("\n"):
        if not line.strip():
            continue
            
        # Check for nested dict
        if line.startswith("  ") and current_dict is not None:
            match = re.match(r"^\s+(\w+):\s*(.*)$", line)
            if match:
                key, value = match.groups()
                current_dict[key] = value.strip().strip('"').strip("'")
            continue
        
        # Top-level key
        match = re.match(r"^(\S+):\s*(.*)$", line)
        if match:
            key, value = match.groups()
            value = value.strip()
            
            if not value:
                # Could be start of nested dict
                result[key] = {}
                current_key = key
                current_dict = result[key]
            else:
                result[key] = value.strip('"').strip("'")
                current_dict = None
    
    return result


def read_properties(skill_dir: Path) -> SkillProperties:
    """Read skill properties from SKILL.md frontmatter.

    This function parses the frontmatter and returns properties.
    It does NOT perform full validation. Use validate() for that.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        SkillProperties with parsed metadata

    Raises:
        ParseError: If SKILL.md is missing or has invalid YAML
        ValidationError: If required fields (name, description) are missing
    """
    skill_dir = Path(skill_dir)
    skill_md = find_skill_md(skill_dir)

    if skill_md is None:
        raise ParseError(f"SKILL.md not found in {skill_dir}")

    content = skill_md.read_text()
    metadata, _ = parse_frontmatter(content)

    if "name" not in metadata:
        raise ValidationError("Missing required field in frontmatter: name")
    if "description" not in metadata:
        raise ValidationError("Missing required field in frontmatter: description")

    name = metadata["name"]
    description = metadata["description"]

    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Field 'name' must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError("Field 'description' must be a non-empty string")

    return SkillProperties(
        name=name.strip(),
        description=description.strip(),
        license=metadata.get("license"),
        compatibility=metadata.get("compatibility"),
        allowed_tools=metadata.get("allowed-tools"),
        metadata=metadata.get("metadata") or {},
        path=skill_dir,
    )
