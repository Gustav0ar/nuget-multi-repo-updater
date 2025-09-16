#!/usr/bin/env python3
"""
NuGet Package Updater and MR Status Tracker

Main entry point for the application with clean separation of concerns.
"""
import argparse
import logging
import sys

from src.providers.gitlab_provider import GitLabProvider
from src.services.config_service import ConfigurationService
from src.services.command_handlers import UpdateNugetCommandHandler, CheckStatusCommandHandler


def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up and configure the argument parser."""
    parser = argparse.ArgumentParser(description='NuGet Package Updater and MR Status Tracker')
    subparsers = parser.add_subparsers(dest='action', required=True)

    # Sub-parser for the update-nuget action
    update_parser = subparsers.add_parser('update-nuget', help='Update NuGet packages')
    update_parser.add_argument('--config-file', help='Path to the configuration file')
    update_parser.add_argument('--gitlab-url', help='GitLab instance URL (overrides config file)')
    update_parser.add_argument('--gitlab-token', help='GitLab access token (overrides config file)')
    update_parser.add_argument('--discover-group', help='Discover all repositories in a specific group/namespace')
    update_parser.add_argument('--repositories', help='Comma-separated list of repository IDs or paths')
    update_parser.add_argument('--repo-file', help='Path to file containing repository IDs/paths (one per line)')
    update_parser.add_argument('--ignore-patterns', help='Comma-separated list of patterns to ignore in repository names')
    update_parser.add_argument('--owned-only', action='store_true', help='Only include repositories owned by the user')
    update_parser.add_argument('--member-only', action='store_true', help='Only include repositories where user is a member')
    update_parser.add_argument('--include-archived', action='store_true', help='Include archived repositories')
    update_parser.add_argument('--exclude-forks', action='store_true', help='Exclude forked repositories')
    update_parser.add_argument('--max-repositories', type=int, help='Maximum number of repositories to process')
    update_parser.add_argument('--dry-run', action='store_true', help='Show what repositories would be processed without making changes')
    update_parser.add_argument('--allow-downgrade', action='store_true', help='Allow downgrading package versions')
    update_parser.add_argument('--report-file', help='Output file for the report')
    update_parser.add_argument('--packages', action='append', help='Specify packages to update in "name@version" format. Can be used multiple times.')
    update_parser.add_argument('--use-local-clone', action='store_true', help='Clone repository locally for modifications (legacy mode)')
    update_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
    update_parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO', help='Logging level')
    
    # Migration-specific arguments
    update_parser.add_argument('--enable-migrations', default=None, action='store_true', help='Enable code migrations')
    update_parser.add_argument('--migration-config', help='Path to migration configuration file')
    update_parser.add_argument('--strict-migration-mode', action='store_true', help='Rollback everything if migrations fail')
    
    # Branch selection arguments
    update_parser.add_argument('--use-most-recent-branch', action='store_true', default=None, help='Use the most recent branch instead of default branch')
    update_parser.add_argument('--branch-filter', default=None, help='Wildcard pattern to filter branches (e.g., "*main", "main*", "*main*")')

    # Sub-parser for the check-status action
    status_parser = subparsers.add_parser('check-status', help='Check the status of merge requests')
    status_parser.add_argument('--config-file', required=True, help='Path to the configuration file')
    status_parser.add_argument('--gitlab-url', help='GitLab instance URL (overrides config file)')
    status_parser.add_argument('--gitlab-token', help='GitLab access token (overrides config file)')
    status_parser.add_argument('--tracking-file', required=True, help='Path to the tracking file')
    status_parser.add_argument('--report-only', action='store_true', help='Only generate report without updating status')
    status_parser.add_argument('--html-dashboard', help='Generate HTML dashboard file')
    status_parser.add_argument('--filter-status', help='Filter merge requests by status')
    status_parser.add_argument('--report-file', help='Output file for status report')

    return parser


def setup_logging(log_level: str) -> None:
    """Configure logging with the specified level."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def load_configuration(config_file: str) -> ConfigurationService:
    """Load and validate configuration."""
    if not config_file:
        return None

    return ConfigurationService(config_file)


def setup_ssl_verification(config_service: ConfigurationService, no_verify_ssl: bool) -> bool:
    """Configure SSL verification settings."""
    verify_ssl = True

    if config_service:
        verify_ssl = config_service.get('verify_ssl', True)

    if no_verify_ssl:
        verify_ssl = False

    if not verify_ssl:
        logging.warning("SSL certificate verification is DISABLED. This should only be used with trusted self-hosted GitLab instances.")
        # Suppress SSL warnings when verification is disabled
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    return verify_ssl

def get_gitlab_credentials(config_service: ConfigurationService, args) -> tuple[str, str]:
    """Extract GitLab URL and token from command line arguments or configuration."""
    # Priority: command line arguments > config file > error
    gitlab_url = getattr(args, 'gitlab_url', None)
    token = getattr(args, 'gitlab_token', None)

    # If not provided via command line, try config file
    if not gitlab_url and config_service:
        gitlab_url = config_service.get('gitlab_url')

    if not token and config_service:
        token = config_service.get('token')

    # Validate that we have both required values
    if not gitlab_url:
        if config_service:
            logging.error("GitLab URL must be provided via --gitlab-url argument or in config file")
        else:
            logging.error("GitLab URL must be provided via --gitlab-url argument (no config file specified)")
        sys.exit(1)

    if not token:
        if config_service:
            logging.error("GitLab token must be provided via --gitlab-token argument or in config file")
        else:
            logging.error("GitLab token must be provided via --gitlab-token argument (no config file specified)")
        sys.exit(1)

    return gitlab_url, token

def main():
    """Main entry point of the application."""
    # Parse command line arguments
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Setup logging
    log_level = getattr(args, 'log_level', 'INFO')
    setup_logging(log_level)

    # Load configuration
    config_service = load_configuration(args.config_file)

    # Setup SSL verification
    no_verify_ssl = getattr(args, 'no_verify_ssl', False)
    verify_ssl = setup_ssl_verification(config_service, no_verify_ssl)

    # Get GitLab credentials
    gitlab_url, token = get_gitlab_credentials(config_service, args)

    # Initialize GitLab provider
    scm_provider = GitLabProvider(gitlab_url, token, verify_ssl)
    # Route to appropriate command handler
    if args.action == 'update-nuget':
        handler = UpdateNugetCommandHandler(scm_provider, config_service)
        handler.execute(args)
    elif args.action == 'check-status':
        handler = CheckStatusCommandHandler(scm_provider)
        handler.execute(args)
    else:
        logging.error(f"Unknown action: {args.action}")
        sys.exit(1)


if __name__ == '__main__':
    main()
