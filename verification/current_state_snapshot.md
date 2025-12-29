# Current State Snapshot
Generated: 2024-12-29

## Recipe Runtime Location
- **Path**: `/Users/praison/praisonai-package/src/praisonai/praisonai/recipe/`
- **Files**:
  - `core.py` - Main runtime: run(), run_stream(), validate(), list_recipes(), describe()
  - `registry.py` - LocalRegistry, RemoteRegistry, get_registry()
  - `history.py` - RunHistory, store_run(), get_run(), export_run()
  - `security.py` - generate_sbom(), sign_bundle(), verify_bundle(), audit_dependencies(), validate_lockfile(), redact_pii(), detect_pii()
  - `policy.py` - PolicyPack, get_default_policy(), check_tool_policy()
  - `serve.py` - HTTP server with API key + JWT auth, CORS config
  - `models.py` - RecipeResult, RecipeEvent, RecipeConfig, ExitCode
  - `exceptions.py` - RecipeError hierarchy

## CLI Handlers Location
- **Path**: `/Users/praison/praisonai-package/src/praisonai/praisonai/cli/features/`
- **Files**:
  - `recipe.py` - RecipeHandler with all recipe commands
  - `endpoints.py` - EndpointsHandler for endpoints CLI

## Main CLI Entry Point
- **Path**: `/Users/praison/praisonai-package/src/praisonai/praisonai/cli/main.py`
- **Recipe routing**: Line 1189-1192 routes 'recipe' command to handle_recipe_command()
- **Endpoints routing**: Line 1196+ routes 'endpoints' command

## Recipe CLI Commands (from handle_recipe_command)
- list, search, info, validate, run, init, test
- pack, unpack, export, replay, serve
- publish, pull, runs
- sbom, audit, sign, verify, policy

## Endpoints CLI Commands
- list, describe, invoke, health

## Registry Code
- **Path**: `/Users/praison/praisonai-package/src/praisonai/praisonai/recipe/registry.py`
- **Classes**: LocalRegistry, RemoteRegistry
- **Functions**: get_registry()

## Documentation
- **Recipe docs**: `/Users/praison/PraisonAIDocs/docs/cli/recipe-*.mdx`
  - recipe-registry.mdx
  - recipe-runs.mdx
  - recipe-security.mdx
  - recipe-policy.mdx
  - recipe-serve.mdx

## Examples
- **Path**: `/Users/praison/praisonai-package/examples/`
  - registry/
  - run_history/
  - security/
  - policy/
  - serve/

## Tests
- **Path**: `/Users/praison/praisonai-package/src/praisonai/tests/`
  - test_registry.py - 35 tests
  - test_recipe.py - 32 tests
  - smoke_test_live.py - 5 live tests
