# Copilot Project Context: NuGet Package Updater + C# Code Migration

This repository is an automation tool that updates NuGet package references across many GitLab repositories and (optionally) applies automated C# code migrations. It consists of:

- **Python orchestrator** (this repo’s `run.py` + `src/`): discovers repos, updates package references, creates MRs, tracks status, generates reports, and coordinates rollback.
- **C# migration tool** (`CSharpMigrationTool/`): a .NET (net9.0) console app using Roslyn to apply AST-based transformations to C# source.

Use this document as the “always available” architectural reference when making changes, debugging issues, or adding features.

---

## What the tool does (product view)

### Main capabilities

- Update **one or multiple** NuGet packages in a batch run.
- Supports both `.csproj` PackageReference forms:
  - single-line: `<PackageReference Include="X" Version="Y" />`
  - multi-line: `<PackageReference Include="X"><Version>Y</Version></PackageReference>`
- Create GitLab merge requests (MRs) for the changes.
- Optional C# code migrations (a **second commit** conceptually) using Roslyn.
- Dry-run mode to preview what would change.
- MR status tracking + markdown report + optional HTML dashboard.
- Robust GitLab API behavior: rate limiting + retries + optional SSL verification disable.

### Non-goals / current limitations

- Only `.csproj` updates are implemented (there’s a stub for `package.json`).
- Migration rule validation is structural (required keys) but does **not** fully validate that `action.type` is supported by the C# tool.
- In API strategy migrations, files are downloaded into a temp dir by **basename**; repositories with duplicate basenames across folders can collide.

---

## High-level architecture

### Entrypoints

- `run.py` is the CLI entrypoint.
  - `update-nuget`: perform updates (+ optional migrations).
  - `check-status`: update MR statuses and generate status reports.

### Major Python modules

- `src/services/command_handlers.py`
  - `UpdateNugetCommandHandler`: parse/merge CLI + config; discovery; dry-run; orchestrate per-repo updates.
  - `CheckStatusCommandHandler`: execute MR tracking workflow.
- `src/actions/multi_package_update_action.py`
  - Core “per repository” update flow: branch → update `.csproj` → (optional) migrate code → MR.
- `src/providers/gitlab_provider.py`
  - Implements `ScmProvider` using GitLab REST API; rate limiter + retry handler.
- `src/strategies/`
  - `ApiStrategy`: operates purely via GitLab API (no local clone).
  - `LocalCloneStrategy`: clones repo, edits locally, commits, pushes.
- `src/services/`
  - `code_migration_service.py`: builds/locates and runs the C# migration tool.
  - `migration_configuration_service.py`: loads migrations from YAML/JSON and determines applicability.
  - `rollback_service.py`: transaction + rollback actions; wraps errors in `TransactionException`.
  - `dry_run_service.py`: simulates changes and prints a console report.
  - `dry_run_code_migration_service.py`: attempts a “dry-run” analysis; falls back to static pattern scan if needed.
  - `report_generator.py`: timestamped markdown update report.
  - `repository_manager.py`: repo list loading, discovery, ignore/fork filtering.

### C# migration tool

- `CSharpMigrationTool/Program.cs`: parses args and runs `MigrationEngine`.
- `CSharpMigrationTool/Services/MigrationEngine.cs`: Roslyn-based transformations.
- `CSharpMigrationTool/Models/MigrationModels.cs`: JSON schema for rules/action/targets/results.

---

## Execution flows

### 1) `update-nuget` flow (per run)

1. Parse CLI args (`run.py`).
2. Load config file if provided (`ConfigurationService`).
3. Determine GitLab URL/token (CLI overrides config).
4. Determine SSL verification (`verify_ssl` in config; `--no-verify-ssl` forces off).
5. Determine repos to process:
   - explicit `--repositories`, `--repo-file`, config `repositories`, or discovery (`--discover-group` / config `discover.group`).
6. If `--dry-run`:
   - `DryRunService.simulate_package_updates(...)` simulates repo scan and (optionally) migration analysis.
7. Otherwise, for each repo:
   - Construct `MultiPackageUpdateAction` (configured for API or local clone strategy).
   - Select target branch:
     - default branch, OR most-recent branch if enabled (`use_most_recent_branch` + optional `branch_filter`).
   - Skip repo if an existing MR already matches the computed MR title.
   - Create update branch.
   - Update all `.csproj` files for all requested packages.
     - **Commit 1** concept:
       - LocalCloneStrategy creates a commit after edits.
       - ApiStrategy commits per file via GitLab API.
   - If enabled and migrations are applicable:
     - Run the C# tool on `.cs` files and upload/apply changes.
     - **Commit 2** concept:
       - LocalCloneStrategy creates a second commit.
       - ApiStrategy commits per file.
   - Push (local clone only), then create MR.
   - On failures, a `RepositoryUpdateTransaction` executes rollback actions (branch deletion, file revert, local cleanup).

### 2) `check-status` flow

1. Read a tracking JSON file (provided externally).
2. Query GitLab for each MR’s status.
3. Save the updated tracking file.
4. Optionally generate:
   - Markdown status report
   - HTML dashboard (`StatusCheckAction.generate_html_visualization`)

---

## Configuration & CLI surface

### Common config keys (JSON/YAML)

- `gitlab_url`: GitLab base URL.
- `token`: GitLab access token.
- `verify_ssl`: boolean.
- `allow_downgrade`: boolean (prevents downgrades by default).
- `report_file`: base path for reports; report generator appends `_YYYY-MM-DD_HH-MM-SS.md`.
- `use_local_clone`: boolean (strategy selection).
- `repositories`: list of repo IDs or `group/project` paths.
- `packages_to_update`: list of objects:
  - `name`: package ID
  - `version`: target version
  - optional: `migration_rule` (present in example configs; current Python flow mostly uses package_name + version applicability).

### Branch selection

- `use_most_recent_branch`: boolean.
- `branch_filter`: wildcard pattern (e.g., `"*main*"`) used when selecting most recent branch.

### Discovery (optional)

Top-level `discover` object (used by `UpdateNugetCommandHandler`):

- `group`: group/namespace to discover within.
- `owned_only`, `member_only`, `include_archived`, `exclude_forks`.
- `ignore_patterns`: list of wildcard patterns.

### Migrations enablement

There are multiple supported toggles (for backward compatibility):

- CLI: `--enable-migrations`
- Config: `migration_settings.enabled` (preferred if present)
- Config legacy: `enable_code_migrations`

Migration rules file:

- CLI: `--migration-config <path>`
- Config: `migration_config_file` (defaults to `package-migrations.yml`)

Rollback strictness:

- CLI: `--strict-migration-mode`
- Config: `rollback_settings.strict_migration_mode`

---

## Migration rules: schema + supported actions

### File format

Migration config is YAML or JSON with top-level:

```yaml
migrations:
  - id: '...'
    package_name: '...'
    description: '...'
    version_conditions:
      - type: 'greater_than|greater_than_or_equal|exact|range'
        version: 'x.y.z'
        max_version: 'x.y.z' # only for range
    rules:
      - name: '...'
        target_nodes:
          - type: 'InvocationExpression|MethodDeclaration|ClassDeclaration|FieldDeclaration|ParameterDeclaration'
            method_name: '...' # invocation/method
            class_name: '...' # class
            identifier: '...' # field/parameter
            containing_type: '...' # optional
            containing_namespace: '...' # invocation optional
            attributes: ['...'] # optional
            parameters: # optional
              - type: '...'
                name: '...'
        action:
          type: '...'
          strategy: '...' # optional
          replacement_method: '...' # for replace_invocation/rename_method
          replacement_type: '...' # for type replacement
          attribute_name: '...' # for add_attribute
          preserve_parameters: true # optional
          preserve_variable_names: true # optional
```

### Supported `action.type` values (as implemented in `MigrationEngine`)

Invocation rules (`InvocationExpression`):

- `remove_invocation`
- `replace_invocation` (uses `replacement_method`)

Method declaration rules (`MethodDeclaration`):

- `rename_method`
- `replace_method_signature`
- `replace_return_type`
- `add_attribute`
- `remove_attribute`

Class declaration rules (`ClassDeclaration`):

- `rename_class`
- `add_attribute`
- `remove_attribute`
- `change_base_class`
- `add_interface`

Field rules (`FieldDeclaration`):

- `replace_field_type`
- `rename_field`
- `add_attribute`
- `remove_attribute`
- `change_accessibility`

Parameter rules (`ParameterDeclaration`):

- `replace_parameter_type`
- `rename_parameter`
- `add_attribute`
- `remove_attribute`

### Important note about rule examples

Some example rule files (e.g., `migration-config.yml`) may include fields like `new_name` or action types like `replace_method_name`. These are **not** part of the C# tool’s JSON schema (`MigrationModels.cs`). Prefer the schema above (as used in `package-migrations.yml`).

---

## Reports & tracking

### Update reports

`ReportGenerator.generate_markdown_report(output_file, ...)` writes to:

- `<output_file>_<timestamp>.md`

It can include:

- target branch
- old_version → new_version (if provided)
- migration analysis info in dry-run reports

### Status tracking

- `check-status` consumes a JSON tracking file (path provided by CLI).
- Note: the current `update-nuget` implementation generates markdown reports but does **not** write this tracking JSON; the tracking file must be created/maintained by another process (or a previous version of the tool).
- Generates:
  - markdown status report
  - optional HTML dashboard

---

## How to run (developer quickstart)

Python:

- Install deps: `pip install -r requirements.txt`

C# tool:

- Build: `cd CSharpMigrationTool && dotnet build`

Run update:

- `python run.py update-nuget --config-file config.yaml`

Dry run:

- `python run.py update-nuget --config-file config.yaml --dry-run`

Check status:

- `python run.py check-status --config-file config.yaml --tracking-file <tracking.json>`

Tests:

- `python tests/run_migration_tests.py`
- Unit only: `python tests/run_migration_tests.py --unit`
- Integration only: `python tests/run_migration_tests.py --integration`

---

## Copilot-specific working rules for this repo

When helping with this repository:

- Treat `run.py` + `src/services/command_handlers.py` as the CLI contract.
- Prefer minimal, surgical changes; keep config keys backward-compatible.
- If you change migration rule schema or behavior, update BOTH:
  - Python: `migration_configuration_service.py` / callers
  - C#: `MigrationModels.cs` + `MigrationEngine.cs`
  - And adjust example rule files in repo.
- Never hardcode credentials; prefer config/env patterns.
- If you add new config keys, document them in README and keep JSON/YAML parity.
