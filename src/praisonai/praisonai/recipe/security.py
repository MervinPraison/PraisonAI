"""
Recipe Security Module

Provides security features for recipes:
- SBOM (Software Bill of Materials) generation
- Bundle signing and verification
- Dependency auditing
- PII redaction
- Lockfile validation
"""

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class SecurityError(Exception):
    """Base exception for security operations."""
    pass


class SignatureError(SecurityError):
    """Signature verification failed."""
    pass


class LockfileError(SecurityError):
    """Lockfile validation failed."""
    pass


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# SBOM Generation
# ============================================================================

def generate_sbom(
    recipe_path: Union[str, Path],
    format: str = "cyclonedx",
    include_python_deps: bool = True,
    include_tools: bool = True,
) -> Dict[str, Any]:
    """
    Generate Software Bill of Materials for a recipe.
    
    Args:
        recipe_path: Path to recipe directory or bundle
        format: Output format (cyclonedx or spdx)
        include_python_deps: Include Python dependencies
        include_tools: Include tool dependencies
        
    Returns:
        SBOM as dictionary
    """
    recipe_path = Path(recipe_path)
    
    # Load recipe manifest
    template_path = recipe_path / "TEMPLATE.yaml"
    manifest = {}
    if template_path.exists():
        import yaml
        with open(template_path) as f:
            manifest = yaml.safe_load(f) or {}
    
    # Get recipe info
    recipe_name = manifest.get("name", recipe_path.name)
    recipe_version = manifest.get("version", "0.0.0")
    
    # Collect components
    components = []
    
    # Add praisonai as component
    try:
        import praisonai
        praisonai_version = getattr(praisonai, "__version__", "unknown")
    except ImportError:
        praisonai_version = "unknown"
    
    components.append({
        "type": "library",
        "name": "praisonai",
        "version": praisonai_version,
        "purl": f"pkg:pypi/praisonai@{praisonai_version}",
    })
    
    # Add Python dependencies from lockfile
    if include_python_deps:
        deps = _get_python_deps(recipe_path)
        for dep in deps:
            components.append({
                "type": "library",
                "name": dep["name"],
                "version": dep["version"],
                "purl": f"pkg:pypi/{dep['name']}@{dep['version']}",
            })
    
    # Add tool dependencies
    if include_tools:
        requires = manifest.get("requires", {})
        tools = requires.get("tools", [])
        for tool in tools:
            if isinstance(tool, str):
                components.append({
                    "type": "application",
                    "name": tool,
                    "version": "unknown",
                })
            elif isinstance(tool, dict):
                components.append({
                    "type": "application",
                    "name": tool.get("name", "unknown"),
                    "version": tool.get("version", "unknown"),
                })
        
        # External dependencies
        external = requires.get("external", [])
        for ext in external:
            if isinstance(ext, str):
                components.append({
                    "type": "application",
                    "name": ext,
                    "version": "unknown",
                })
    
    if format == "cyclonedx":
        return _generate_cyclonedx(recipe_name, recipe_version, components)
    elif format == "spdx":
        return _generate_spdx(recipe_name, recipe_version, components)
    else:
        raise SecurityError(f"Unknown SBOM format: {format}")


def _generate_cyclonedx(
    name: str,
    version: str,
    components: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate CycloneDX SBOM."""
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "serialNumber": f"urn:uuid:{hashlib.md5(f'{name}{version}{_get_timestamp()}'.encode()).hexdigest()}",
        "version": 1,
        "metadata": {
            "timestamp": _get_timestamp(),
            "tools": [{"name": "praisonai-sbom", "version": "1.0.0"}],
            "component": {
                "type": "application",
                "name": name,
                "version": version,
            },
        },
        "components": [
            {
                "type": comp["type"],
                "name": comp["name"],
                "version": comp["version"],
                "purl": comp.get("purl"),
            }
            for comp in components
        ],
    }


def _generate_spdx(
    name: str,
    version: str,
    components: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate SPDX SBOM."""
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{name}-{version}",
        "documentNamespace": f"https://praison.ai/sbom/{name}/{version}",
        "creationInfo": {
            "created": _get_timestamp(),
            "creators": ["Tool: praisonai-sbom-1.0.0"],
        },
        "packages": [
            {
                "SPDXID": f"SPDXRef-Package-{i}",
                "name": comp["name"],
                "versionInfo": comp["version"],
                "downloadLocation": "NOASSERTION",
            }
            for i, comp in enumerate(components)
        ],
    }


def _get_python_deps(recipe_path: Path) -> List[Dict[str, str]]:
    """Get Python dependencies from lockfile."""
    deps = []
    lock_dir = recipe_path / "lock"
    
    # Try uv.lock
    uv_lock = lock_dir / "uv.lock"
    if uv_lock.exists():
        deps.extend(_parse_uv_lock(uv_lock))
        return deps
    
    # Try requirements.lock
    req_lock = lock_dir / "requirements.lock"
    if req_lock.exists():
        deps.extend(_parse_requirements_lock(req_lock))
        return deps
    
    # Try poetry.lock
    poetry_lock = lock_dir / "poetry.lock"
    if poetry_lock.exists():
        deps.extend(_parse_poetry_lock(poetry_lock))
        return deps
    
    # Fallback: try requirements.txt in recipe root
    req_txt = recipe_path / "requirements.txt"
    if req_txt.exists():
        deps.extend(_parse_requirements_lock(req_txt))
    
    return deps


def _parse_uv_lock(path: Path) -> List[Dict[str, str]]:
    """Parse uv.lock file."""
    deps = []
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        
        for pkg in data.get("package", []):
            deps.append({
                "name": pkg.get("name", ""),
                "version": pkg.get("version", ""),
            })
    except Exception:
        pass
    
    return deps


def _parse_requirements_lock(path: Path) -> List[Dict[str, str]]:
    """Parse requirements.lock or requirements.txt."""
    deps = []
    
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            
            # Parse package==version
            match = re.match(r"^([a-zA-Z0-9_-]+)==([^\s;]+)", line)
            if match:
                deps.append({
                    "name": match.group(1),
                    "version": match.group(2),
                })
    
    return deps


def _parse_poetry_lock(path: Path) -> List[Dict[str, str]]:
    """Parse poetry.lock file."""
    deps = []
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        
        for pkg in data.get("package", []):
            deps.append({
                "name": pkg.get("name", ""),
                "version": pkg.get("version", ""),
            })
    except Exception:
        pass
    
    return deps


# ============================================================================
# Bundle Signing
# ============================================================================

def sign_bundle(
    bundle_path: Union[str, Path],
    private_key_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Sign a recipe bundle.
    
    Args:
        bundle_path: Path to .praison bundle
        private_key_path: Path to private key (PEM format)
        output_path: Output path for signature (default: bundle.sig)
        
    Returns:
        Path to signature file
    """
    bundle_path = Path(bundle_path)
    private_key_path = Path(private_key_path)
    
    if not bundle_path.exists():
        raise SecurityError(f"Bundle not found: {bundle_path}")
    if not private_key_path.exists():
        raise SecurityError(f"Private key not found: {private_key_path}")
    
    # Calculate bundle hash
    bundle_hash = _calculate_file_hash(bundle_path)
    
    # Sign using cryptography library (lazy import)
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        raise SecurityError("cryptography package required for signing. Install with: pip install cryptography")
    
    # Load private key
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    
    # Sign the hash
    signature = private_key.sign(
        bundle_hash.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    
    # Write signature
    output_path = Path(output_path) if output_path else bundle_path.with_suffix(".praison.sig")
    
    sig_data = {
        "bundle": bundle_path.name,
        "hash": bundle_hash,
        "algorithm": "RSA-PKCS1v15-SHA256",
        "signature": signature.hex(),
        "signed_at": _get_timestamp(),
    }
    
    with open(output_path, "w") as f:
        json.dump(sig_data, f, indent=2)
    
    return output_path


def verify_bundle(
    bundle_path: Union[str, Path],
    public_key_path: Union[str, Path],
    signature_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """
    Verify a signed recipe bundle.
    
    Args:
        bundle_path: Path to .praison bundle
        public_key_path: Path to public key (PEM format)
        signature_path: Path to signature file (default: bundle.sig)
        
    Returns:
        Tuple of (valid: bool, message: str)
    """
    bundle_path = Path(bundle_path)
    public_key_path = Path(public_key_path)
    signature_path = Path(signature_path) if signature_path else bundle_path.with_suffix(".praison.sig")
    
    if not bundle_path.exists():
        return False, f"Bundle not found: {bundle_path}"
    if not public_key_path.exists():
        return False, f"Public key not found: {public_key_path}"
    if not signature_path.exists():
        return False, f"Signature not found: {signature_path}"
    
    # Load signature
    with open(signature_path) as f:
        sig_data = json.load(f)
    
    # Calculate current bundle hash
    current_hash = _calculate_file_hash(bundle_path)
    
    # Check hash matches
    if current_hash != sig_data["hash"]:
        return False, "Bundle hash mismatch - file may have been modified"
    
    # Verify signature
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        return False, "cryptography package required for verification"
    
    # Load public key
    with open(public_key_path, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())
    
    # Verify
    try:
        signature = bytes.fromhex(sig_data["signature"])
        public_key.verify(
            signature,
            sig_data["hash"].encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True, "Signature valid"
    except Exception as e:
        return False, f"Signature verification failed: {e}"


def _calculate_file_hash(path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ============================================================================
# Dependency Auditing
# ============================================================================

def audit_dependencies(
    recipe_path: Union[str, Path],
    check_vulnerabilities: bool = True,
) -> Dict[str, Any]:
    """
    Audit recipe dependencies for security issues.
    
    Args:
        recipe_path: Path to recipe directory
        check_vulnerabilities: Check for known vulnerabilities
        
    Returns:
        Audit report dictionary
    """
    recipe_path = Path(recipe_path)
    
    report = {
        "recipe": recipe_path.name,
        "audited_at": _get_timestamp(),
        "lockfile": None,
        "dependencies": [],
        "vulnerabilities": [],
        "warnings": [],
        "passed": True,
    }
    
    # Check for lockfile
    lockfile = _find_lockfile(recipe_path)
    if lockfile:
        report["lockfile"] = str(lockfile)
    else:
        report["warnings"].append("No lockfile found - dependencies may not be reproducible")
    
    # Get dependencies
    deps = _get_python_deps(recipe_path)
    report["dependencies"] = deps
    
    # Check for vulnerabilities using pip-audit if available
    if check_vulnerabilities and deps:
        vulns = _check_vulnerabilities(deps)
        report["vulnerabilities"] = vulns
        if vulns:
            report["passed"] = False
    
    # Check for outdated dependencies
    outdated = _check_outdated(deps)
    if outdated:
        report["warnings"].extend([
            f"Outdated: {d['name']} ({d['current']} -> {d['latest']})"
            for d in outdated
        ])
    
    return report


def _find_lockfile(recipe_path: Path) -> Optional[Path]:
    """Find lockfile in recipe directory."""
    lock_dir = recipe_path / "lock"
    
    candidates = [
        lock_dir / "uv.lock",
        lock_dir / "requirements.lock",
        lock_dir / "poetry.lock",
        recipe_path / "uv.lock",
        recipe_path / "requirements.lock",
        recipe_path / "poetry.lock",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    return None


def _check_vulnerabilities(deps: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Check dependencies for known vulnerabilities."""
    vulns = []
    
    # Try using pip-audit
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            audit_data = json.loads(result.stdout)
            for vuln in audit_data.get("vulnerabilities", []):
                vulns.append({
                    "package": vuln.get("name"),
                    "version": vuln.get("version"),
                    "vulnerability_id": vuln.get("id"),
                    "description": vuln.get("description"),
                    "fix_versions": vuln.get("fix_versions", []),
                })
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    
    return vulns


def _check_outdated(deps: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Check for outdated dependencies."""
    # Simplified - would need PyPI API for full implementation
    return []


# ============================================================================
# Lockfile Validation
# ============================================================================

def validate_lockfile(
    recipe_path: Union[str, Path],
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Validate recipe lockfile.
    
    Args:
        recipe_path: Path to recipe directory
        strict: Fail if lockfile missing
        
    Returns:
        Validation result dictionary
    """
    recipe_path = Path(recipe_path)
    
    result = {
        "valid": True,
        "lockfile": None,
        "lockfile_type": None,
        "errors": [],
        "warnings": [],
    }
    
    lockfile = _find_lockfile(recipe_path)
    
    if not lockfile:
        if strict:
            result["valid"] = False
            result["errors"].append("No lockfile found")
        else:
            result["warnings"].append("No lockfile found - dependencies may not be reproducible")
        return result
    
    result["lockfile"] = str(lockfile)
    
    # Determine lockfile type
    if "uv.lock" in lockfile.name:
        result["lockfile_type"] = "uv"
    elif "poetry.lock" in lockfile.name:
        result["lockfile_type"] = "poetry"
    else:
        result["lockfile_type"] = "pip"
    
    # Validate lockfile format
    try:
        if result["lockfile_type"] == "uv":
            _parse_uv_lock(lockfile)
        elif result["lockfile_type"] == "poetry":
            _parse_poetry_lock(lockfile)
        else:
            _parse_requirements_lock(lockfile)
    except Exception as e:
        result["valid"] = False
        result["errors"].append(f"Invalid lockfile format: {e}")
    
    return result


# ============================================================================
# PII Redaction
# ============================================================================

# Default PII patterns
PII_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
}


def redact_pii(
    data: Any,
    policy: Optional[Dict[str, Any]] = None,
    fields: Optional[List[str]] = None,
) -> Any:
    """
    Redact PII from data based on policy.
    
    Args:
        data: Data to redact (dict, list, or string)
        policy: Data policy configuration
        fields: Specific fields to redact (overrides policy)
        
    Returns:
        Redacted data
    """
    policy = policy or {}
    mode = policy.get("pii", {}).get("mode", "allow")
    
    if mode == "allow":
        return data
    
    fields = fields or policy.get("pii", {}).get("fields", list(PII_PATTERNS.keys()))
    
    if isinstance(data, dict):
        return {k: redact_pii(v, policy, fields) for k, v in data.items()}
    elif isinstance(data, list):
        return [redact_pii(item, policy, fields) for item in data]
    elif isinstance(data, str):
        return _redact_string(data, fields, mode)
    else:
        return data


def _redact_string(text: str, fields: List[str], mode: str) -> str:
    """Redact PII patterns from a string."""
    for field in fields:
        if field in PII_PATTERNS:
            pattern = PII_PATTERNS[field]
            if mode == "redact":
                text = re.sub(pattern, f"[REDACTED:{field}]", text)
            elif mode == "deny":
                if re.search(pattern, text):
                    raise SecurityError(f"PII detected ({field}) and policy is 'deny'")
    return text


def detect_pii(
    data: Any,
    fields: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Detect PII in data without redacting.
    
    Args:
        data: Data to scan
        fields: Specific fields to check
        
    Returns:
        List of detected PII instances
    """
    fields = fields or list(PII_PATTERNS.keys())
    detections = []
    
    def scan(value, path=""):
        if isinstance(value, dict):
            for k, v in value.items():
                scan(v, f"{path}.{k}" if path else k)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                scan(item, f"{path}[{i}]")
        elif isinstance(value, str):
            for field in fields:
                if field in PII_PATTERNS:
                    matches = re.findall(PII_PATTERNS[field], value)
                    for match in matches:
                        detections.append({
                            "type": field,
                            "path": path,
                            "sample": match[:4] + "..." if len(match) > 4 else match,
                        })
    
    scan(data)
    return detections
