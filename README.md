# NuGet Package Updater and MR Status Tracker

A powerful automation tool for updating NuGet packages across multiple GitLab repositories and tracking the status of merge requests. This tool streamlines the process of keeping .NET projects up-to-date by automatically creating merge requests with package updates and providing comprehensive status tracking.

## Features

### 🚀 **Package Updates**
- **Multiple Package Support**: Update multiple NuGet packages in a single operation
- **Batch Processing**: Process multiple repositories simultaneously
- **Single Commit Strategy**: All package updates bundled into one commit per repository
- **Version Validation**: Automatic downgrade prevention with override option
- **Smart Detection**: Supports both single-line and multi-line PackageReference formats

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

#### Discovery Configuration (`config-discover.json`)

```json
{
  "gitlab_url": "https://gitlab.company.com",
  "token": "glpat-xxxxxxxxxxxxxxxxxxxx",
  "use_local_clone": false,
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

## Usage

### Update NuGet Packages

#### Basic Usage with Configuration File

```bash
python run.py update-nuget --config-file config.json
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
  --report-file custom-report.md
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
- Merge request creation preview with branch information
- Comprehensive summary with file modification counts

## Command Reference

### Common Arguments

| Argument | Description |
|----------|-------------|
| `--config-file` | Path to JSON/YAML configuration file |
| `--dry-run` | Preview changes without making modifications |
| `--log-level` | Set logging level (DEBUG, INFO, WARNING, ERROR) |
| `--no-verify-ssl` | Disable SSL certificate verification |

### Update NuGet Arguments

| Argument | Description |
|----------|-------------|
| `--packages` | Package in "name@version" format (can be used multiple times) |
| `--repositories` | Comma-separated list of repository IDs or paths |
| `--repo-file` | File containing repository IDs/paths (one per line) |
| `--discover-group` | Discover repositories in GitLab group/namespace |
| `--ignore-patterns` | Comma-separated patterns to ignore in repository names |
| `--owned-only` | Only include repositories owned by the user |
| `--member-only` | Only include repositories where user is a member |
| `--gitlab-url` | GitLab instance URL (overrides config file) |
| `--gitlab-token` | GitLab access token (overrides config file) |
| `--include-archived` | Include archived repositories |
| `--exclude-forks` | Exclude forked repositories |
| `--max-repositories` | Maximum number of repositories to process |
| `--allow-downgrade` | Allow package version downgrades |
| `--report-file` | Output file for update report |

### Check Status Arguments

| Argument | Description |
|----------|-------------|
| `--tracking-file` | JSON file with merge request tracking data |
| `--report-only` | Generate report without updating status |
| `--html-dashboard` | Generate interactive HTML dashboard |
| `--filter-status` | Filter merge requests by status |
| `--report-file` | Output file for status report |

## Output Files

### Tracking Data
| `--report-file` | Output file for update report (overrides config file) |
| `--use-local-clone` | Use local git cloning mode instead of API mode |
- **Purpose**: Stores merge request information for status tracking
- **Contains**: Repository details, package information, MR URLs, branch information

### Reports
- **Markdown Reports**: Detailed status with package and branch information
| `--gitlab-url` | GitLab instance URL (overrides config file) |
| `--gitlab-token` | GitLab access token (overrides config file) |
- **HTML Dashboard**: Interactive visualization with filtering capabilities
| `--use-local-clone` | Use local git cloning mode instead of API mode |

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
