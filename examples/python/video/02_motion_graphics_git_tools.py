"""Motion Graphics — GitTools safety demo (no network required for this demo).

GitTools is the read-only toolkit used by the code-exploration specialist in
`motion_graphics_team`. It clones repos on demand, validates paths against
traversal, and restricts to GitHub URLs or `owner/repo` format.

This example exercises the pure-Python safety helpers (URL parsing + file
path validation). Cloning is network-bound and demonstrated separately.

Requirements:
    pip install praisonai-tools
"""

from praisonai_tools.tools.git_tools import GitTools


def main() -> None:
    tools = GitTools(base_dir="/tmp/praison_git_repos_demo")

    print("URL parsing")
    print("-----------")
    for repo_input in [
        "octocat/Hello-World",                         # owner/repo
        "https://github.com/octocat/Hello-World.git",  # https URL
        "git@github.com:octocat/Hello-World.git",      # ssh URL
    ]:
        try:
            url, name = tools._parse_repo_input(repo_input)
            print(f"  {repo_input:<50}  ->  name={name}")
        except ValueError as exc:
            print(f"  {repo_input:<50}  ->  REJECTED: {exc}")

    print("\nFile-path validation")
    print("--------------------")
    for path in [
        "README.md",            # safe
        "src/main.py",          # safe
        "../etc/passwd",        # traversal
        "../../secret.txt",     # traversal
        "/etc/passwd",          # absolute
    ]:
        try:
            safe = tools._validate_file_path(path)
            print(f"  {path:<30}  ->  SAFE:   {safe}")
        except ValueError as exc:
            print(f"  {path:<30}  ->  REJECT: {exc}")

    print("\nListing any previously cloned repos:", tools.list_repos())


if __name__ == "__main__":
    main()
