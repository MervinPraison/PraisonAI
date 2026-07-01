"""
Package CLI Feature Handler

Provides pip-like CLI commands for package management:
- install: Install Python packages
- uninstall: Uninstall Python packages
- list: List installed packages
- search: Search packages
- index: Manage package indexes

All commands use the canonical `praisonai` or `praisonai package` prefix.

Security:
- Default to single authoritative index (PyPI)
- Warn loudly about dependency confusion when using extra indexes
- Require explicit opt-in for extra index fallback
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


# Default configuration
DEFAULT_INDEX_URL = "https://pypi.org/simple"
CONFIG_DIR = Path.home() / ".praison"
CONFIG_FILE = CONFIG_DIR / "config.toml"


class PackageConfig:
    """Package configuration manager."""
    
    def __init__(self):
        """Initialize config."""
        self._config = None
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if self._config is not None:
            return self._config
        
        self._config = {
            "package": {
                "index_url": DEFAULT_INDEX_URL,
                "extra_index_urls": [],
                "allow_extra_index": False,
                "trusted_hosts": [],
            }
        }
        
        if CONFIG_FILE.exists():
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    return self._config
            
            try:
                with open(CONFIG_FILE, "rb") as f:
                    file_config = tomllib.load(f)
                    if "package" in file_config:
                        self._config["package"].update(file_config["package"])
            except Exception:
                pass
        
        # Environment variable overrides
        if os.environ.get("PRAISONAI_PACKAGE_INDEX_URL"):
            self._config["package"]["index_url"] = os.environ["PRAISONAI_PACKAGE_INDEX_URL"]
        
        if os.environ.get("PRAISONAI_PACKAGE_EXTRA_INDEX_URLS"):
            urls = os.environ["PRAISONAI_PACKAGE_EXTRA_INDEX_URLS"].split(",")
            self._config["package"]["extra_index_urls"] = [u.strip() for u in urls if u.strip()]
        
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value."""
        config = self._load_config()
        parts = key.split(".")
        value = config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value
    
    def save_index(self, index_url: str) -> None:
        """Save index URL to config."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        config = {}
        if CONFIG_FILE.exists():
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    # Fall back to simple write
                    with open(CONFIG_FILE, "w") as f:
                        f.write(f'[package]\nindex_url = "{index_url}"\n')
                    return
            
            try:
                with open(CONFIG_FILE, "rb") as f:
                    config = tomllib.load(f)
            except Exception:
                pass
        
        if "package" not in config:
            config["package"] = {}
        config["package"]["index_url"] = index_url
        
        # Write config (simple TOML format)
        with open(CONFIG_FILE, "w") as f:
            for section, values in config.items():
                f.write(f"[{section}]\n")
                for key, value in values.items():
                    if isinstance(value, str):
                        f.write(f'{key} = "{value}"\n')
                    elif isinstance(value, bool):
                        f.write(f'{key} = {"true" if value else "false"}\n')
                    elif isinstance(value, list):
                        f.write(f'{key} = {json.dumps(value)}\n')
                    else:
                        f.write(f'{key} = {value}\n')
                f.write("\n")


class PackageHandler:
    """
    CLI handler for package operations.
    
    Commands:
    - install: Install Python packages
    - uninstall: Uninstall Python packages
    - list: List installed packages
    - search: Search packages (best-effort)
    - index: Manage package indexes
    """
    
    # Stable exit codes
    EXIT_SUCCESS = 0
    EXIT_GENERAL_ERROR = 1
    EXIT_VALIDATION_ERROR = 2
    EXIT_NETWORK_ERROR = 10
    EXIT_DEPENDENCY_ERROR = 11
    
    def __init__(self):
        """Initialize the handler."""
        self.config = PackageConfig()
    
    def handle(self, args: List[str]) -> int:
        """
        Handle package subcommand.
        
        Args:
            args: Command arguments
            
        Returns:
            Exit code
        """
        if not args:
            self._print_help()
            return self.EXIT_SUCCESS
        
        command = args[0]
        remaining = args[1:]
        
        commands = {
            "list": self.cmd_list,
            "search": self.cmd_search,
            "index": self.cmd_index,
            "help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "--help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "-h": lambda _: self._print_help() or self.EXIT_SUCCESS,
        }
        
        handler = commands.get(command)
        if handler:
            return handler(remaining)
        
        self._print_error(f"Unknown command: {command}")
        self._print_help()
        return self.EXIT_VALIDATION_ERROR
    
    def _print_help(self):
        """Print help message."""
        print("""
PraisonAI Package Commands

Usage: praisonai package <command> [options]
       praisonai install <spec...>
       praisonai uninstall <pkg...>

Commands:
  install     Install Python packages (shortcut: praisonai install)
  uninstall   Uninstall Python packages (shortcut: praisonai uninstall)
  list        List installed packages
  search      Search for packages
  index       Manage package indexes

Examples:
  praisonai install requests
  praisonai install "requests>=2.28" httpx
  praisonai uninstall requests
  praisonai package list
  praisonai package search langchain
  praisonai package index show
  praisonai package index set https://my-index.example.com/simple

Options for 'install':
  --index-url URL       Use custom index URL
  --extra-index-url URL Add extra index (requires --allow-extra-index)
  --allow-extra-index   Allow extra index URLs (security risk!)
  --python PATH         Python interpreter to use
  --upgrade, -U         Upgrade packages
  --no-deps             Don't install dependencies
  --json                Output in JSON format

Options for 'uninstall':
  --python PATH         Python interpreter to use
  --yes, -y             Don't ask for confirmation
  --json                Output in JSON format

Security Notes:
  - By default, only the primary index is used (PyPI)
  - Using --extra-index-url can lead to dependency confusion attacks
  - Always prefer --index-url over --extra-index-url when possible
""")
    
    def _print_error(self, message: str):
        """Print error message."""
        print(f"Error: {message}", file=sys.stderr)
    
    def _print_warning(self, message: str):
        """Print warning message."""
        print(f"Warning: {message}", file=sys.stderr)
    
    def _print_success(self, message: str):
        """Print success message."""
        print(f"✓ {message}")
    
    def _print_json(self, data: Any):
        """Print JSON output."""
        print(json.dumps(data, indent=2))
    
    def _parse_args(self, args: List[str], spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Parse command arguments, returning parsed args and positional args."""
        result = {k: v.get("default") for k, v in spec.items()}
        positional = []
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg.startswith("--"):
                key = arg[2:].replace("-", "_")
                if key in spec:
                    if spec[key].get("flag"):
                        result[key] = True
                    elif i + 1 < len(args):
                        result[key] = args[i + 1]
                        i += 1
                else:
                    positional.append(arg)
            elif arg.startswith("-") and len(arg) == 2:
                # Short flag
                found = False
                for key, val in spec.items():
                    if val.get("short") == arg:
                        if val.get("flag"):
                            result[key] = True
                        elif i + 1 < len(args):
                            result[key] = args[i + 1]
                            i += 1
                        found = True
                        break
                if not found:
                    positional.append(arg)
            else:
                positional.append(arg)
            i += 1
        
        return result, positional
    
    def _get_python(self, python_path: str = None) -> str:
        """Get Python interpreter path."""
        if python_path:
            return python_path
        return sys.executable
    
    def _run_pip(
        self,
        args: List[str],
        python: str = None,
        capture: bool = False,
    ) -> Tuple[int, str, str]:
        """
        Run pip command.
        
        Args:
            args: pip arguments
            python: Python interpreter path
            capture: Capture output instead of streaming
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        python = self._get_python(python)
        cmd = [python, "-m", "pip"] + args
        
        if capture:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, "PAGER": "cat"},
            )
            return result.returncode, result.stdout, result.stderr
        else:
            result = subprocess.run(
                cmd,
                env={**os.environ, "PAGER": "cat"},
            )
            return result.returncode, "", ""
    
    def cmd_install(self, args: List[str]) -> int:
        """Install Python packages."""
        spec = {
            "index_url": {"default": None},
            "extra_index_url": {"default": None},
            "allow_extra_index": {"flag": True, "default": False},
            "python": {"default": None},
            "upgrade": {"flag": True, "short": "-U", "default": False},
            "no_deps": {"flag": True, "default": False},
            "json": {"flag": True, "default": False},
        }
        parsed, packages = self._parse_args(args, spec)
        
        if not packages:
            self._print_error("No packages specified")
            return self.EXIT_VALIDATION_ERROR
        
        # Build pip command
        pip_args = ["install"]
        
        # Index URL
        index_url = parsed["index_url"] or self.config.get("package.index_url", DEFAULT_INDEX_URL)
        pip_args.extend(["--index-url", index_url])
        
        # Extra index URL (with security warning)
        extra_index = parsed["extra_index_url"]
        if extra_index:
            allow_extra = parsed["allow_extra_index"] or self.config.get("package.allow_extra_index", False)
            if not allow_extra:
                self._print_error(
                    "Extra index URLs are disabled by default for security.\n"
                    "Using multiple indexes can lead to dependency confusion attacks.\n"
                    "To enable, use --allow-extra-index flag or set package.allow_extra_index=true in config."
                )
                return self.EXIT_VALIDATION_ERROR
            
            self._print_warning(
                "⚠️  SECURITY WARNING: Using extra index URLs can lead to dependency confusion attacks!\n"
                "   An attacker could publish a malicious package with the same name on PyPI.\n"
                "   Only use this if you trust both indexes and understand the risks."
            )
            pip_args.extend(["--extra-index-url", extra_index])
        
        # Other options
        if parsed["upgrade"]:
            pip_args.append("--upgrade")
        if parsed["no_deps"]:
            pip_args.append("--no-deps")
        
        # Add packages
        pip_args.extend(packages)
        
        if parsed["json"]:
            returncode, stdout, stderr = self._run_pip(pip_args, parsed["python"], capture=True)
            self._print_json({
                "ok": returncode == 0,
                "packages": packages,
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
            })
            return returncode
        else:
            print(f"Installing: {', '.join(packages)}")
            returncode, _, _ = self._run_pip(pip_args, parsed["python"])
            if returncode == 0:
                self._print_success("Installation complete")
            return returncode
    
    def cmd_uninstall(self, args: List[str]) -> int:
        """Uninstall Python packages."""
        spec = {
            "python": {"default": None},
            "yes": {"flag": True, "short": "-y", "default": False},
            "json": {"flag": True, "default": False},
        }
        parsed, packages = self._parse_args(args, spec)
        
        if not packages:
            self._print_error("No packages specified")
            return self.EXIT_VALIDATION_ERROR
        
        pip_args = ["uninstall"]
        if parsed["yes"]:
            pip_args.append("-y")
        pip_args.extend(packages)
        
        if parsed["json"]:
            returncode, stdout, stderr = self._run_pip(pip_args, parsed["python"], capture=True)
            self._print_json({
                "ok": returncode == 0,
                "packages": packages,
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
            })
            return returncode
        else:
            print(f"Uninstalling: {', '.join(packages)}")
            returncode, _, _ = self._run_pip(pip_args, parsed["python"])
            if returncode == 0:
                self._print_success("Uninstall complete")
            return returncode
    
    def cmd_list(self, args: List[str]) -> int:
        """List installed packages."""
        spec = {
            "python": {"default": None},
            "json": {"flag": True, "default": False},
            "outdated": {"flag": True, "default": False},
        }
        parsed, _ = self._parse_args(args, spec)
        
        pip_args = ["list", "--format=json"]
        if parsed["outdated"]:
            pip_args.append("--outdated")
        
        returncode, stdout, stderr = self._run_pip(pip_args, parsed["python"], capture=True)
        
        if returncode != 0:
            self._print_error(stderr or "Failed to list packages")
            return returncode
        
        try:
            packages = json.loads(stdout)
        except json.JSONDecodeError:
            packages = []
        
        if parsed["json"]:
            self._print_json({
                "ok": True,
                "packages": packages,
                "count": len(packages),
            })
        else:
            if not packages:
                print("No packages installed.")
            else:
                print(f"{'Package':<30} {'Version':<15}")
                print("-" * 45)
                for pkg in packages:
                    name = pkg.get("name", "")
                    version = pkg.get("version", "")
                    print(f"{name:<30} {version:<15}")
                print(f"\nTotal: {len(packages)} packages")
        
        return self.EXIT_SUCCESS
    
    def cmd_search(self, args: List[str]) -> int:
        """Search for packages (best-effort, uses pip search or PyPI API)."""
        spec = {
            "json": {"flag": True, "default": False},
        }
        parsed, query_parts = self._parse_args(args, spec)
        
        if not query_parts:
            self._print_error("Search query required")
            return self.EXIT_VALIDATION_ERROR
        
        query = " ".join(query_parts)
        
        # pip search is deprecated, use PyPI JSON API
        try:
            import urllib.request
            import urllib.error
            
            url = f"https://pypi.org/pypi/{query}/json"
            try:
                with urllib.request.urlopen(url, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    
                    info = data.get("info", {})
                    result = {
                        "name": info.get("name"),
                        "version": info.get("version"),
                        "summary": info.get("summary"),
                        "author": info.get("author"),
                        "home_page": info.get("home_page"),
                    }
                    
                    if parsed["json"]:
                        self._print_json({"ok": True, "results": [result]})
                    else:
                        print(f"Found: {result['name']} ({result['version']})")
                        print(f"  {result['summary']}")
                        if result['home_page']:
                            print(f"  Homepage: {result['home_page']}")
                    
                    return self.EXIT_SUCCESS
                    
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    if parsed["json"]:
                        self._print_json({"ok": True, "results": [], "message": "No exact match found"})
                    else:
                        print(f"No exact match for '{query}'")
                        print("Try: pip search <query> (if available) or browse https://pypi.org")
                    return self.EXIT_SUCCESS
                raise
                
        except Exception as e:
            if parsed["json"]:
                self._print_json({"ok": False, "error": str(e)})
            else:
                self._print_error(f"Search failed: {e}")
            return self.EXIT_NETWORK_ERROR
    
    def cmd_index(self, args: List[str]) -> int:
        """Manage package indexes."""
        if not args:
            return self._index_show([])
        
        subcommand = args[0]
        remaining = args[1:]
        
        subcommands = {
            "show": self._index_show,
            "set": self._index_set,
            "add": self._index_add,
            "remove": self._index_remove,
        }
        
        handler = subcommands.get(subcommand)
        if handler:
            return handler(remaining)
        
        self._print_error(f"Unknown index subcommand: {subcommand}")
        return self.EXIT_VALIDATION_ERROR
    
    def _index_show(self, args: List[str]) -> int:
        """Show current index configuration."""
        spec = {
            "json": {"flag": True, "default": False},
        }
        parsed, _ = self._parse_args(args, spec)
        
        index_url = self.config.get("package.index_url", DEFAULT_INDEX_URL)
        extra_urls = self.config.get("package.extra_index_urls", [])
        allow_extra = self.config.get("package.allow_extra_index", False)
        
        if parsed["json"]:
            self._print_json({
                "ok": True,
                "index_url": index_url,
                "extra_index_urls": extra_urls,
                "allow_extra_index": allow_extra,
            })
        else:
            print(f"Primary Index: {index_url}")
            if extra_urls:
                print(f"Extra Indexes: {', '.join(extra_urls)}")
            print(f"Allow Extra Index: {'yes' if allow_extra else 'no'}")
        
        return self.EXIT_SUCCESS
    
    def _index_set(self, args: List[str]) -> int:
        """Set primary index URL."""
        if not args:
            self._print_error("Index URL required")
            return self.EXIT_VALIDATION_ERROR
        
        url = args[0]
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            self._print_error("Index URL must start with http:// or https://")
            return self.EXIT_VALIDATION_ERROR
        
        self.config.save_index(url)
        self._print_success(f"Primary index set to: {url}")
        
        return self.EXIT_SUCCESS
    
    def _index_add(self, args: List[str]) -> int:
        """Add extra index URL."""
        self._print_warning(
            "Adding extra index URLs is a security risk!\n"
            "This can lead to dependency confusion attacks.\n"
            "Consider using --index-url to switch indexes instead."
        )
        
        if not args:
            self._print_error("Index URL required")
            return self.EXIT_VALIDATION_ERROR
        
        # For now, just print instructions
        print("\nTo use extra index, run:")
        print(f"  praisonai install <pkg> --extra-index-url {args[0]} --allow-extra-index")
        
        return self.EXIT_SUCCESS
    
    def _index_remove(self, args: List[str]) -> int:
        """Remove extra index URL."""
        print("Extra index URLs are not persisted by default.")
        print("To reset to PyPI, run:")
        print(f"  praisonai package index set {DEFAULT_INDEX_URL}")
        
        return self.EXIT_SUCCESS
