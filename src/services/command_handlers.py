"""
Command handlers for different application actions with migration support.
"""
import logging
import sys
from typing import List, Dict, Any

from src.actions.multi_package_update_action import MultiPackageUpdateAction
from src.actions.status_check_action import StatusCheckAction
from src.providers.scm_provider import ScmProvider
from src.services.config_service import ConfigurationService
from src.services.git_service import GitService
from src.services.report_generator import ReportGenerator
from src.services.migration_configuration_service import MigrationConfigurationService
from src.services.rollback_service import TransactionException


class UpdateNugetCommandHandler:
    """Handles the update-nuget command execution with migration support."""

    def __init__(self, scm_provider: ScmProvider, config_service: ConfigurationService):
        self.scm_provider = scm_provider
        self.config_service = config_service

    def execute(self, args: Any) -> None:
        """Execute the update-nuget command with migration support."""
        # Import here to avoid circular imports
        from src.services.repository_manager import RepositoryManager
        from src.services.dry_run_service import DryRunService
        from src.services.user_interaction_service import UserInteractionService

        repository_manager = RepositoryManager(self.scm_provider)
        dry_run_service = DryRunService(self.scm_provider)
        user_interaction = UserInteractionService()

        # Parse packages to update
        packages_to_update = self._parse_packages_to_update(args)

        # Initialize migration support if enabled
        migration_config_service = None
        enable_migrations = getattr(args, 'enable_migrations', False)
        
        if not enable_migrations and self.config_service:
            enable_migrations = self.config_service.get('enable_code_migrations', False)
            
        if enable_migrations:
            migration_config_file = self._get_migration_config_file(args)
            if migration_config_file:
                try:
                    migration_config_service = MigrationConfigurationService(migration_config_file)
                    if not migration_config_service.validate_migration_rules():
                        logging.error("Migration configuration validation failed")
                        sys.exit(1)
                    logging.info(f"Loaded migration configuration from {migration_config_file}")
                except Exception as e:
                    logging.error(f"Failed to load migration configuration: {e}")
                    if getattr(args, 'strict_migration_mode', False):
                        sys.exit(1)
                    else:
                        logging.warning("Continuing without migrations")
                        enable_migrations = False

        # Get repositories based on input method
        repositories = self._get_repositories(args, repository_manager, user_interaction)

        # Apply repository limits
        if hasattr(args, 'max_repositories') and args.max_repositories and isinstance(args.max_repositories, int) and args.max_repositories > 0:
            repositories = repositories[:args.max_repositories]

        if not repositories:
            logging.error("No repositories to process")
            sys.exit(1)

        # Handle dry run mode
        if args.dry_run:
            dry_run_report_file = getattr(args, 'report_file', None)
            if not dry_run_report_file and self.config_service:
                dry_run_report_file = self.config_service.get('report_file')

            use_local_clone = getattr(args, 'use_local_clone', None)
            if use_local_clone is None and self.config_service:
                use_local_clone = self.config_service.get('use_local_clone', False)

            dry_run_service.simulate_package_updates(
                repositories, packages_to_update, args.allow_downgrade, dry_run_report_file, use_local_clone
            )
            return

        # Execute actual updates with migration support
        self._execute_updates_with_migrations(repositories, packages_to_update, args, 
                                            migration_config_service, enable_migrations)

    def _get_migration_config_file(self, args: Any) -> str:
        """Get migration configuration file path."""
        migration_config = getattr(args, 'migration_config', None)
        if migration_config:
            return migration_config
            
        if self.config_service:
            return self.config_service.get('migration_config_file', 'package-migrations.yml')
            
        return 'package-migrations.yml'

    def _execute_updates_with_migrations(self, repositories: List[Dict], packages_to_update: List[Dict[str, str]], 
                                       args: Any, migration_config_service: MigrationConfigurationService,
                                       enable_migrations: bool) -> None:
        """Execute updates with migration support and comprehensive error handling."""
        git_service = GitService()
        successful_results = []
        failed_repositories = []
        rollback_reports = []

        # Get migration settings
        strict_migration_mode = getattr(args, 'strict_migration_mode', False)
        if not strict_migration_mode and self.config_service:
            rollback_settings = self.config_service.get('rollback_settings', {})
            strict_migration_mode = rollback_settings.get('strict_migration_mode', False)

        for repo_info in repositories:
            try:
                # Create enhanced action with migration support
                action = MultiPackageUpdateAction(
                    git_service=git_service,
                    scm_provider=self.scm_provider,
                    packages=packages_to_update,
                    allow_downgrade=args.allow_downgrade,
                    use_local_clone=args.use_local_clone,
                    migration_config_service=migration_config_service,
                    enable_migrations=enable_migrations,
                    strict_migration_mode=strict_migration_mode
                )

                result = action.execute(repo_info['ssh_url_to_repo'], 
                                      str(repo_info['id']), 
                                      repo_info['default_branch'])

                if result:
                    successful_results.append(result)
                    logging.info(f"Successfully processed repository {repo_info['id']}")
                    
                    if result.get('migration_result'):
                        migration_info = result['migration_result']
                        if migration_info['success'] and migration_info['applied_rules']:
                            logging.info(f"Applied {len(migration_info['applied_rules'])} migration rules")
                else:
                    failed_repositories.append(repo_info)
                    logging.error(f"Failed to process repository {repo_info['id']}")

            except TransactionException as e:
                logging.error(f"Repository update failed with rollback for {repo_info['id']}: {e}")
                failed_repositories.append(repo_info)
                
                if e.rollback_result:
                    rollback_reports.append({
                        'repository': repo_info['id'],
                        'error': str(e),
                        'rollback_report': e.rollback_result.generate_report()
                    })

            except Exception as e:
                logging.error(f"Unexpected error processing repository {repo_info['id']}: {e}")
                failed_repositories.append(repo_info)

        # Generate comprehensive report
        self._generate_comprehensive_report(successful_results, failed_repositories, rollback_reports, args)

    def _generate_comprehensive_report(self, successful_results: List[Dict], failed_repositories: List[Dict],
                                     rollback_reports: List[Dict], args: Any) -> None:
        """Generate comprehensive report including rollback information."""
        report_file = getattr(args, 'report_file', None)
        if not report_file and self.config_service:
            report_file = self.config_service.get('report_file')

        if report_file:
            try:
                report_generator = ReportGenerator()
                
                enhanced_results = []
                for result in successful_results:
                    enhanced_result = result.copy()
                    if 'migration_result' in result:
                        enhanced_result['has_migrations'] = True
                        enhanced_result['migration_summary'] = result['migration_result']['summary']
                    enhanced_results.append(enhanced_result)

                report_generator.generate_markdown_report(report_file, results=enhanced_results)
                
                if rollback_reports:
                    self._append_rollback_report(report_file, rollback_reports)
                    
                logging.info(f"Enhanced report generated: {report_file}")
                
            except Exception as e:
                logging.error(f"Failed to generate enhanced report: {e}")

        total_repos = len(successful_results) + len(failed_repositories)
        logging.info(f"Processing complete: {len(successful_results)}/{total_repos} repositories succeeded")
        
        if rollback_reports:
            logging.warning(f"Rollbacks were required for {len(rollback_reports)} repositories")

    def _append_rollback_report(self, report_file: str, rollback_reports: List[Dict]) -> None:
        """Append rollback information to the report file."""
        try:
            with open(report_file, 'a', encoding='utf-8') as f:
                f.write("\n\n## 🔄 Rollback Information\n\n")
                f.write("The following repositories required rollback due to failures:\n\n")
                
                for report in rollback_reports:
                    f.write(f"### Repository: {report['repository']}\n\n")
                    f.write(f"**Error:** {report['error']}\n\n")
                    f.write("**Rollback Details:**\n")
                    f.write("```\n")
                    f.write(report['rollback_report'])
                    f.write("\n```\n\n")
                    
        except Exception as e:
            logging.error(f"Failed to append rollback report: {e}")

    def _parse_packages_to_update(self, args: Any) -> List[Dict[str, str]]:
        """Parse and validate packages to update with migration support."""
        packages_to_update = []

        if args.packages:
            for p in args.packages:
                try:
                    name, version = p.split('@')
                    packages_to_update.append({'name': name, 'version': version})
                except ValueError:
                    logging.error(f"Invalid package format: {p}. Expected 'name@version'.")
                    sys.exit(1)
        else:
            if self.config_service:
                packages_to_update = self.config_service.get('packages_to_update', [])
            if not packages_to_update:
                logging.error("No packages specified via --packages argument or in config file.")
                sys.exit(1)

        return packages_to_update

    def _get_repositories(self, args: Any, repository_manager, user_interaction) -> List[Dict]:
        """Get repositories based on input method."""
        repositories = []

        if args.repositories:
            repositories = repository_manager.get_repositories_from_command_line(args.repositories)
        elif args.repo_file:
            repositories = repository_manager.get_repositories_from_file(args.repo_file)
        elif args.discover_group:
            # Use command line arguments, falling back to config file values
            discover_config = self.config_service.get('discover', {}) if self.config_service else {}
            
            group = args.discover_group
            owned_only = getattr(args, 'owned_only', discover_config.get('owned_only', False))
            member_only = getattr(args, 'member_only', discover_config.get('member_only', False))
            include_archived = getattr(args, 'include_archived', discover_config.get('include_archived', False))
            exclude_forks = getattr(args, 'exclude_forks', discover_config.get('exclude_forks', False))
            ignore_patterns = getattr(args, 'ignore_patterns', None)
            
            # Handle ignore_patterns: could be None, empty list, or a string
            if ignore_patterns and isinstance(ignore_patterns, list) and len(ignore_patterns) == 0:
                ignore_patterns = None
            
            # If ignore_patterns not provided via args, get from config
            if not ignore_patterns and discover_config.get('ignore_patterns'):
                ignore_patterns_list = discover_config.get('ignore_patterns', [])
                if isinstance(ignore_patterns_list, list):
                    ignore_patterns = ','.join(ignore_patterns_list)
                elif isinstance(ignore_patterns_list, str):
                    ignore_patterns = ignore_patterns_list
            
            repositories = repository_manager.discover_repositories(
                group, owned_only, member_only, include_archived
            )

            if ignore_patterns:
                ignored_patterns = ignore_patterns.split(',')
                repositories = repository_manager.filter_repositories_by_patterns(repositories, ignored_patterns)

            if exclude_forks:
                repositories = repository_manager.filter_out_forks(repositories)

            if repositories:
                user_interaction.display_discovered_repositories(repositories)
            else:
                logging.info("No repositories found matching the discovery criteria")
                return []
        else:
            # Check if discover mode should be used from config file
            if self.config_service:
                discover_config = self.config_service.get('discover', {})
                # Ensure discover_config is a dict (safety check for tests)
                if isinstance(discover_config, dict) and discover_config.get('group'):
                    # Use discovery mode with config file values
                    group = discover_config.get('group')
                    owned_only = discover_config.get('owned_only', False)
                    member_only = discover_config.get('member_only', False)
                    include_archived = discover_config.get('include_archived', False)
                    exclude_forks = discover_config.get('exclude_forks', False)
                    ignore_patterns_list = discover_config.get('ignore_patterns', [])
                    
                    repositories = repository_manager.discover_repositories(
                        group, owned_only, member_only, include_archived
                    )

                    if ignore_patterns_list:
                        repositories = repository_manager.filter_repositories_by_patterns(repositories, ignore_patterns_list)

                    if exclude_forks:
                        repositories = repository_manager.filter_out_forks(repositories)

                    if repositories:
                        user_interaction.display_discovered_repositories(repositories)
                        return repositories
                    else:
                        logging.info("No repositories found matching the discovery criteria from config")
                
                # Fall back to repositories list from config
                repo_configs = self.config_service.get('repositories', [])
                repositories = repository_manager.get_repositories_from_config(repo_configs)
                
            if not repositories:
                logging.error("No repositories specified. Use --repositories, --repo-file, --discover-group, or specify repositories/discover config in config file.")
                sys.exit(1)

        return repositories


class CheckStatusCommandHandler:
    """Handles the check-status command execution."""

    def __init__(self, scm_provider: ScmProvider):
        self.scm_provider = scm_provider

    def execute(self, args: Any) -> None:
        """Execute the check-status command."""
        action = StatusCheckAction(
            self.scm_provider, 
            args.tracking_file, 
            getattr(args, 'report_only', False)
        )
        
        success = action.execute()

        # Generate report if requested
        if hasattr(args, 'report_file') and args.report_file:
            action.generate_status_report(args.report_file)
            
        # Generate HTML dashboard if requested
        if hasattr(args, 'html_dashboard') and args.html_dashboard:
            action.generate_html_visualization(args.html_dashboard)
            
        # Filter by status if requested
        if hasattr(args, 'filter_status') and args.filter_status:
            filtered_mrs = action.filter_by_status(args.filter_status)
            logging.info(f"Found {len(filtered_mrs)} merge requests with status '{args.filter_status}'")

        if success:
            logging.info("Status check completed successfully")
        else:
            logging.error("Status check failed")
            sys.exit(1)
