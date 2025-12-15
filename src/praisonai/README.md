# PraisonAI Package

## Development

```bash
# Install
uv sync

# Build
uv build

# Publish
uv publish
```

## Version Bump

```bash
# From project root
python src/praisonai/scripts/bump_version.py 2.2.96

# With praisonaiagents dependency
python src/praisonai/scripts/bump_version.py 2.2.96 --agents 0.0.167
```

## Release

```bash
# From project root (runs uv lock, build, git tag, gh release)
python src/praisonai/scripts/release.py

# Then publish
cd src/praisonai && uv publish
```
