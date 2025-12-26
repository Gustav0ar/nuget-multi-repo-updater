# NuGet Package Updater with Automated C# Code Migration

A powerful automation tool for updating NuGet packages across multiple GitLab repositories with **automated C# code migration** and comprehensive tracking of merge requests. This tool not only updates package references but also intelligently migrates your C# code to work with new package versions, eliminating manual code changes and reducing migration effort.

## Features

### 🚀 **Package Updates with Code Migration**

- **Multiple Package Support**: Update multiple NuGet packages in a single operation
- **Automated Code Migration**: AST-based C# code transformations using Roslyn
- **Two-Commit Workflow**: Separate commits for package updates and code migrations
- **Smart Rollback**: Comprehensive rollback mechanism with transaction-based recovery
- **Version Validation**: Automatic downgrade prevention with override option
- **Smart Detection**: Supports both single-line and multi-line PackageReference formats

### 🔧 **Code Migration Engine**

- **AST-Based Transformations**: Uses Microsoft.CodeAnalysis (Roslyn) for precise code changes
- **Method Invocation Removal**: Smart removal of deprecated method calls with chain-aware logic
- **Method Name Replacement**: Automatic renaming of methods for API changes
- **Configurable Rules**: YAML-based migration rules for different package versions
- **Rollback Support**: Complete transaction rollback on migration failures

### 🔍 **Repository Discovery**

- **Multiple Input Methods**: Command-line lists, file-based, GitLab group discovery, or configuration
- **Advanced Filtering**: Ignore patterns, fork exclusion, archived repository handling
- **Interactive Confirmation**: User confirmation modes for discovered repositories
- **Flexible Selection**: Repository limits and custom selection criteria

### 📊 **Status Tracking & Reporting**

- **Comprehensive Tracking**: Monitor merge request status across all repositories
- **Interactive Dashboard**: HTML visualization with filtering and status breakdown
- **Detailed Reports**: Markdown reports with branch information and package details
- **Progress Monitoring**: Track merge request lifecycle from creation to merge

### 🛡️ **Enterprise Ready**

- **Rate Limiting**: Built-in GitLab API rate limiting with intelligent backoff
- **SSL Support**: Configurable SSL verification for self-hosted instances
- **Error Handling**: Robust retry logic with exponential backoff
- **Dry Run Mode**: Comprehensive simulation to preview all changes

## Installation

### Prerequisites

- Python 3.8 or higher
- Access to GitLab instance with API token
- Git configured for repository access

### Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:

- `requests` - HTTP client for GitLab API
- `GitPython` - Git repository operations
- `PyYAML` - YAML configuration support
- `packaging` - Version parsing and comparison

### C# Migration Tool

The C# migration tool requires:

- **.NET 10.0 SDK** or higher
- **Microsoft.CodeAnalysis.CSharp** NuGet package for AST operations

Build the C# migration tool:

```bash
cd CSharpMigrationTool
dotnet build
```

## Configuration

### GitLab API Token

Create a GitLab personal access token with the following scopes:

- `api` - Full access to the API
- `read_repository` - Read access to repositories
- `write_repository` - Write access to repositories
- `read_user` - Read access to user information

**Required Role**: Developer or Maintainer in target repositories.

### Configuration Files

The application supports both JSON and YAML configuration formats:

#### Basic Configuration (`config.json`)

```json
{
  "gitlab_url": "https://gitlab.company.com",
  "token": "glpat-xxxxxxxxxxxxxxxxxxxx",
  "use_local_clone": false,
  "enable_code_migrations": true,
  "migration_config_file": "package-migrations.yml",
  "use_most_recent_branch": false,
  "branch_filter": "*main*",
  "packages_to_update": [
    {
      "name": "Microsoft.EntityFrameworkCore",
      "version": "7.0.5"
    },
    {
      "name": "Newtonsoft.Json",
      "version": "13.0.3"
    }
  ],
  "repositories": [
    "123",
    "456",
    "backend-team/user-service",
    "backend-team/order-service"
  ],
  "report_file": "reports/package-update.md",
  "verify_ssl": true,
  "allow_downgrade": false
}
```

#### Basic Configuration (`config.yaml`)

```yaml
gitlab_url: 'https://gitlab.company.com'
token: 'glpat-xxxxxxxxxxxxxxxxxxxx'
use_local_clone: false
enable_code_migrations: true
migration_config_file: 'package-migrations.yml'
use_most_recent_branch: false
branch_filter: '*main*'

packages_to_update:
  - name: 'Microsoft.EntityFrameworkCore'
    version: '7.0.5'
  - name: 'Newtonsoft.Json'
    version: '13.0.3'

repositories:
  - '123'
  - '456'
  - 'backend-team/user-service'
  - 'backend-team/order-service'

report_file: 'reports/package-update.md'
verify_ssl: true
allow_downgrade: false
```

#### Migration Configuration (`package-migrations.yml`)

```yaml
migrations:
  - id: 'entityframework-remove-obsolete'
    package_name: 'Microsoft.EntityFrameworkCore'
    description: 'Remove obsolete Entity Framework methods'
    version_conditions:
      - type: 'greater_than'
        version: '6.0.0'
    rules:
      - name: 'Remove Entity.Property() calls'
        target_nodes:
          - type: 'InvocationExpression'
            method_name: 'Property'
            containing_namespace: 'Microsoft.EntityFrameworkCore'
        action:
          type: 'remove_invocation'
          strategy: 'smart_chain_aware'

  - id: 'newtonsoft-method-rename'
    package_name: 'Newtonsoft.Json'
    description: 'Rename deprecated JsonConvert methods'
    version_conditions:
      - type: 'greater_than_or_equal'
        version: '13.0.0'
    rules:
      - name: 'Rename SerializeObjectAsync'
        target_nodes:
          - type: 'InvocationExpression'
            method_name: 'SerializeObjectAsync'
        action:
          type: 'replace_invocation'
          replacement_method: 'SerializeAsync'
```

#### Discovery Configuration (`config-discover.json`)

```json
{
  "gitlab_url": "https://gitlab.company.com",
  "token": "glpat-xxxxxxxxxxxxxxxxxxxx",
  "use_local_clone": false,
  "enable_code_migrations": true,
  "migration_config_file": "package-migrations.yml",
  "packages_to_update": [
    {
      "name": "Microsoft.EntityFrameworkCore",
      "version": "7.0.5"
    }
  ],
  "discover": {
    "group": "backend-team",
    "owned_only": false,
    "member_only": false,
    "include_archived": false,
    "exclude_forks": true,
    "ignore_patterns": [
      "*-test*",
      "*-demo",
      "*-ui",
      "*-frontend",
      "playground-*"
    ]
  }
}
```

#### Discovery Configuration (`config-discover.yaml`)

```yaml
gitlab_url: 'https://gitlab.company.com'
token: 'glpat-xxxxxxxxxxxxxxxxxxxx'
use_local_clone: false
enable_code_migrations: true
migration_config_file: 'package-migrations.yml'
use_most_recent_branch: false
branch_filter: '*main*'

packages_to_update:
  - name: 'Microsoft.EntityFrameworkCore'
    version: '7.0.5'

discover:
  group: 'backend-team'
  owned_only: false
  member_only: false
  include_archived: false
  exclude_forks: true
  ignore_patterns:
    - '*-test*'
    - '*-demo'
    - '*-ui'
    - '*-frontend'
    - 'playground-*'
```

## Usage

### Update NuGet Packages with Code Migration

#### Basic Usage with Configuration File

```bash
python run.py update-nuget --config-file config.json
```

With code migration enabled (via config or `--enable-migrations`), this will:

1. Update package references in .csproj files
2. Apply configured C# code migrations
3. Create two separate commits (package updates + code changes)
4. Automatically rollback on failure

#### Disable Code Migration

There is no CLI flag to force-disable migrations if they are enabled in the config file. To disable migrations, set `enable_code_migrations: false` (or `migration_settings.enabled: false`) in your config.

```yaml
# config.yaml
enable_code_migrations: false
```

#### Command Line Package Specification

```bash
python run.py update-nuget --config-file config.json \
  --packages "EntityFramework@7.0.0" \
  --packages "Newtonsoft.Json@13.0.3"
```

#### Repository Discovery Mode

```bash
python run.py update-nuget --config-file config.json \
  --discover-group "backend-team" \
  --ignore-patterns "*-test*,*-demo" \
  --exclude-forks \
  --max-repositories 10
```

#### Direct Repository Specification

```bash
# From command line
python run.py update-nuget --config-file config.json \
  --repositories "123,456,group/project"

# From file
python run.py update-nuget --config-file config.json \
  --repo-file repositories.txt
```

#### Advanced Options

```bash
python run.py update-nuget --config-file config.json \
  --dry-run \
  --allow-downgrade \
  --no-verify-ssl \
  --log-level DEBUG \
  --report-file custom-report.md \
  --enable-migrations \
  --strict-migration-mode \
  --migration-config custom-migration-config.yml
```

#### Using Most Recent Branch

By default, the tool uses the repository's default branch (usually `main` or `master`). You can configure it to use the most recent branch instead:

```bash
python run.py update-nuget --config-file config.yaml \
  --use-most-recent-branch \
  --branch-filter "*main*"
```

The `--branch-filter` supports wildcard patterns:

- `*main` - Branches ending with "main" (e.g., "hotfix-main", "feature-main")
- `main*` - Branches starting with "main" (e.g., "main-v2", "main-develop")
- `*main*` - Branches containing "main" (e.g., "feature-main-fix", "main")

You can also configure this in your config file:

```json
{
  "use_most_recent_branch": true,
  "branch_filter": "*main*",
  ...
}
```

Or in YAML format:

```yaml
use_most_recent_branch: true
branch_filter: '*main*'
# ... other configuration options
```

### Check Merge Request Status

#### Basic Status Check

```bash
python run.py check-status \
  --config-file config.json \
  --tracking-file multi_package_MRs.json
```

#### Generate Reports and Dashboard

```bash
python run.py check-status \
  --config-file config.json \
  --tracking-file multi_package_MRs.json \
  --report-file status-report.md \
  --html-dashboard dashboard.html
```

#### Filter by Status

```bash
python run.py check-status \
  --config-file config.json \
  --tracking-file multi_package_MRs.json \
  --filter-status merged
```

### Dry Run Mode

Preview all changes before execution:

```bash
python run.py update-nuget --config-file config.json --dry-run
```

**Dry Run Features:**

- Repository analysis without cloning
- .csproj file examination with current version detection
- Package update simulation with downgrade checking
- Code migration simulation with applicable rules preview
- Merge request creation preview with branch information
- Comprehensive summary with file modification counts

## Code Migration Features

### Migration Rules

The code migration engine supports several types of transformations:

#### Remove Method Invocations

Remove deprecated method calls with smart chain-aware logic:

```yaml
- name: 'Remove obsolete method calls'
  target_nodes:
    - type: 'InvocationExpression'
      method_name: 'ObsoleteMethod'
      containing_namespace: 'MyPackage'
  action:
    type: 'remove_invocation'
    strategy: 'smart_chain_aware'
```

**Smart Chain-Aware Strategy:**

- Removes method calls while preserving method chaining
- Example: `builder.Method1().ObsoleteMethod().Method2()` becomes `builder.Method1().Method2()`

#### Replace Method Names

Rename methods to match new API signatures:

```yaml
- name: 'Rename deprecated methods'
  target_nodes:
    - type: 'InvocationExpression'
      method_name: 'OldMethodName'
  action:
    type: 'replace_invocation'
    replacement_method: 'NewMethodName'
```

### Version Conditions

Control when migrations are applied based on package versions:

| Condition Type          | Description                               | Example                                |
| ----------------------- | ----------------------------------------- | -------------------------------------- |
| `greater_than`          | Apply when upgrading from below threshold | Migrate when upgrading from 1.x to 2.x |
| `greater_than_or_equal` | Apply when reaching or exceeding version  | Migrate when reaching 2.0+             |
| `exact`                 | Apply only for specific target version    | Migrate only when upgrading to 2.1.0   |
| `range`                 | Apply within version range                | Migrate when upgrading to 2.0-3.0      |

### Transaction-Based Rollback

The migration system includes comprehensive rollback capabilities:

- **Automatic Rollback**: Failed migrations trigger automatic rollback of all changes
- **LIFO Action Stack**: Operations are rolled back in reverse order (Last In, First Out)
- **Git-Based Recovery**: Uses Git reset to restore repository state
- **File-Level Cleanup**: Removes temporary files and artifacts
- **Branch Management**: Cleans up feature branches on failure

### Testing the Migration Feature

Run the comprehensive test suite:

```bash
# Run all migration tests
python tests/run_migration_tests.py

# Run only unit tests
python tests/run_migration_tests.py --unit

# Run only integration tests
python tests/run_migration_tests.py --integration
```

## Command Reference

### Common Arguments

| Argument          | Description                                     |
| ----------------- | ----------------------------------------------- |
| `--config-file`   | Path to JSON/YAML configuration file            |
| `--dry-run`       | Preview changes without making modifications    |
| `--log-level`     | Set logging level (DEBUG, INFO, WARNING, ERROR) |
| `--no-verify-ssl` | Disable SSL certificate verification            |

### Update NuGet Arguments

| Argument                   | Description                                                    |
| -------------------------- | -------------------------------------------------------------- |
| `--packages`               | Package in "name@version" format (can be used multiple times)  |
| `--repositories`           | Comma-separated list of repository IDs or paths                |
| `--repo-file`              | File containing repository IDs/paths (one per line)            |
| `--discover-group`         | Discover repositories in GitLab group/namespace                |
| `--ignore-patterns`        | Comma-separated patterns to ignore in repository names         |
| `--owned-only`             | Only include repositories owned by the user                    |
| `--member-only`            | Only include repositories where user is a member               |
| `--gitlab-url`             | GitLab instance URL (overrides config file)                    |
| `--gitlab-token`           | GitLab access token (overrides config file)                    |
| `--include-archived`       | Include archived repositories                                  |
| `--exclude-forks`          | Exclude forked repositories                                    |
| `--max-repositories`       | Maximum number of repositories to process                      |
| `--allow-downgrade`        | Allow package version downgrades                               |
| `--report-file`            | Output file for update report                                  |
| `--use-local-clone`        | Use local git cloning mode instead of API mode                 |
| `--enable-migrations`      | Enable automatic code migrations                               |
| `--migration-config`       | Path to migration configuration file                           |
| `--strict-migration-mode`  | Roll back everything if migrations fail                        |
| `--use-most-recent-branch` | Use the most recent branch instead of default branch           |
| `--branch-filter`          | Wildcard pattern to filter branches (e.g., "_main_", "main\*") |

### Check Status Arguments

| Argument            | Description                                    |
| ------------------- | ---------------------------------------------- |
| `--tracking-file`   | JSON file with merge request tracking data     |
| `--report-only`     | Generate report without updating status        |
| `--html-dashboard`  | Generate interactive HTML dashboard            |
| `--filter-status`   | Filter merge requests by status                |
| `--report-file`     | Output file for status report                  |
| `--gitlab-url`      | GitLab instance URL (overrides config file)    |
| `--gitlab-token`    | GitLab access token (overrides config file)    |
| `--use-local-clone` | Use local git cloning mode instead of API mode |

## Output Files

### Tracking Data

- **Purpose**: Stores merge request information for status tracking
- **Contains**: Repository details, package information, MR URLs, branch information, migration results

### Reports

- **Markdown Reports**: Detailed status with package and branch information, migration summaries
- **HTML Dashboard**: Interactive visualization with filtering capabilities, migration status indicators

## Architecture

### Migration Workflow

1. **Package Analysis**: Determine which packages need updates
2. **Migration Configuration**: Load applicable migration rules based on package versions
3. **Transaction Setup**: Initialize rollback transaction for each repository
4. **Package Updates**: Update .csproj files and commit changes
5. **Code Migration**: Apply C# AST transformations using Roslyn
6. **Verification**: Validate migration results and commit code changes
7. **Rollback**: Automatic rollback on any failure

### Components

- **Migration Configuration Service**: Loads and validates YAML-based migration rules
- **Code Migration Service**: Orchestrates C# migration tool execution
- **Rollback Service**: Manages transaction rollback with LIFO action stack
- **C# Migration Tool**: .NET console application using Roslyn for AST manipulation
- **Enhanced Repository Strategies**: Support for two-commit workflow and rollback

---

## Contributing

This tool is designed for enterprise NuGet package management with automated code migration. Contributions are welcome for:

- Additional migration rule types
- Enhanced C# transformation patterns
- Integration with other source control systems
- Performance optimizations for large repository sets

## License

MIT License - see LICENSE file for details.

### Example Report Structure

```markdown
# Merge Request Status Report

Generated: 2025-09-10 14:30:00
| `--use-local-clone` | Use local git cloning mode instead of API mode |

- **File Pattern**: `multi_package_MRs_YYYYMMDD_HHMMSS.json` (timestamped for uniqueness)
- **Example**: `multi_package_MRs_20250912_143052.json`

## Summary

- Total Merge Requests: 15
- Opened: 3
- Merged: 10
- Closed: 2

- **Example**: `multi_package_MRs_20250912_143052.json`
- **ProjectName** (EntityFramework → 7.0.0): [MR Link](...)
  - **Target Branch**: main
  - **Source Branch**: update-entityframework-to-7_0_0
```

The application follows a clean, modular architecture:

```
src/
├── actions/           # Business logic actions
├── core/             # Base classes and interfaces
## Details
└── run.py           # Main application entry point
```

### Key Components

- **Command Handlers**: Orchestrate business logic for different commands
- **Repository Manager**: Handle various repository input methods
- **Dry Run Service**: Provide comprehensive simulation capabilities
- **GitLab Provider**: Interface with GitLab API with rate limiting
- **Status Check Action**: Monitor and report merge request status

## Troubleshooting

### Common Issues

**Rate Limiting**

- The application includes automatic rate limiting
- For heavy usage, the tool will prompt for user confirmation on long waits
- Consider using `--max-repositories` to limit batch size

**SSL Certificate Issues**

- Use `--no-verify-ssl` for self-hosted GitLab with self-signed certificates
- Ensure your GitLab URL is correct and accessible

**Authentication Errors**

- Verify your GitLab token has the required permissions
- Check that the token hasn't expired
- Ensure you have Developer/Maintainer access to target repositories

**Repository Access**

- Verify repository IDs/paths are correct
- Check that repositories exist and are accessible
- Ensure your token has access to the specified repositories

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
python run.py update-nuget --config-file config.json --log-level DEBUG
```
