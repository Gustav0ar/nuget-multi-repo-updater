"""
Command handlers for different application actions with migration support.
"""
import logging
import sys
import json
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
            # Get report file from args or config for dry run
            dry_run_report_file = getattr(args, 'report_file', None)
            if not dry_run_report_file and self.config_service:
                dry_run_report_file = self.config_service.get('report_file')

            dry_run_service.simulate_package_updates(
                repositories, packages_to_update, args.allow_downgrade, dry_run_report_file
            )
            return  # dry_run_service exits the program

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
                    
                    # Log migration information if available
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
                
                # Enhance report with migration and rollback information
                enhanced_results = []
                for result in successful_results:
                    enhanced_result = result.copy()
                    if 'migration_result' in result:
                        enhanced_result['has_migrations'] = True
                        enhanced_result['migration_summary'] = result['migration_result']['summary']
                    enhanced_results.append(enhanced_result)

                report_generator.generate_markdown_report(enhanced_results, report_file)
                
                # Add rollback information if any
                if rollback_reports:
                    self._append_rollback_report(report_file, rollback_reports)
                    
                logging.info(f"Enhanced report generated: {report_file}")
                
            except Exception as e:
                logging.error(f"Failed to generate enhanced report: {e}")

        # Log summary
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
            # Fallback to config for multiple package update
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
            # From command line
            repositories = repository_manager.get_repositories_from_command_line(args.repositories)
        elif args.repo_file:
            # From file
            repositories = repository_manager.get_repositories_from_file(args.repo_file)
        elif args.discover_group:
            # Discovery mode
            repositories = repository_manager.discover_repositories(
                args.discover_group, args.owned_only, args.member_only, args.include_archived
            )

            # Apply discovery filters
            if args.ignore_patterns:
                ignored_patterns = args.ignore_patterns.split(',')
                repositories = repository_manager.filter_repositories_by_ignore_patterns(repositories, ignored_patterns)

            if args.exclude_forks:
                repositories = repository_manager.filter_out_forks(repositories)

            # Ask for user confirmation for discovery mode
            if repositories:
                user_interaction.confirm_discovered_repositories(repositories)
            else:
                logging.info("No repositories found matching the discovery criteria")
                return []
        else:
            # Fallback to config
            if self.config_service:
                repositories = repository_manager.get_repositories_from_config(self.config_service)
            if not repositories:
                logging.error("No repositories specified. Use --repositories, --repo-file, --discover-group, or specify repositories in config file.")
                sys.exit(1)

        return repositories


class CheckStatusCommandHandler:
    """Handles the check-status command execution."""

    def __init__(self, scm_provider: ScmProvider):
        self.scm_provider = scm_provider

    def execute(self, args: Any) -> None:
        """Execute the check-status command."""
        # Import here to avoid circular imports
        from src.services.repository_manager import RepositoryManager

        repository_manager = RepositoryManager(self.scm_provider)

        action = StatusCheckAction(self.scm_provider)
        result = action.execute(
            args.tracking_file,
            args.report_only,
            args.html_dashboard,
            args.filter_status,
            args.report_file
        )

        if result:
            logging.info("Status check completed successfully")
        else:
            logging.error("Status check failed")
            sys.exit(1)

        if args.repositories:
            # From command line
            repositories = repository_manager.get_repositories_from_command_line(args.repositories)
        elif args.repo_file:
            # From file
            repositories = repository_manager.get_repositories_from_file(args.repo_file)
        elif args.discover_group:
            # Discovery mode
            repositories = repository_manager.discover_repositories(
                args.discover_group, args.owned_only, args.member_only, args.include_archived
            )
            repositories = repository_manager.filter_repositories(
                repositories, args.ignore_patterns, args.exclude_forks
            )
            repositories = user_interaction.get_user_confirmation(repositories)
        else:
            # From config file
            if self.config_service:
                repo_configs = self.config_service.get('repositories', [])
                repositories = repository_manager.get_repositories_from_config(repo_configs)
            if not repositories:
                logging.error("No repositories specified. Use --repositories, --repo-file, --discover-group, or provide repositories in config file.")
                sys.exit(1)

        return repositories

    def _execute_updates(self, repositories: List[Dict], packages_to_update: List[Dict], args: Any) -> None:
        """Execute the actual package updates."""
        report_generator = ReportGenerator()
        merge_requests_data = []

        for repo in repositories:
            # Handle both repository objects and IDs
            if isinstance(repo, dict):
                project = repo
            else:
                # This handles the case where repo is a string ID
                project = self.scm_provider.get_project(str(repo))

            if project:
                self._process_repository(
                    project, packages_to_update, args, report_generator, merge_requests_data
                )

        # Generate reports and save tracking data
        self._finalize_execution(args, report_generator, merge_requests_data)

    def _process_repository(self, project: Dict, packages_to_update: List[Dict], args: Any,
                          report_generator: ReportGenerator, merge_requests_data: List[Dict]) -> None:
        """Process a single repository for package updates."""
        repo_url = project['http_url_to_repo']
        default_branch = project['default_branch']
        local_path = f"./temp/{project['name']}"

        git_service = GitService(local_path)

        # Note: We cannot reliably check for existing MRs here because we don't know
        # which packages will actually be updated until we process the files.
        # The MultiPackageUpdateAction will handle existing MR detection based on actual updates.

        # Determine whether to use local clone mode
        use_local_clone = getattr(args, 'use_local_clone', False)
        if not use_local_clone and self.config_service:
            use_local_clone = self.config_service.get('use_local_clone', False)

        # Use MultiPackageUpdateAction to handle all packages in a single transaction
        action = MultiPackageUpdateAction(git_service, self.scm_provider, packages_to_update,
                                        args.allow_downgrade, use_local_clone)
        mr_info = action.execute(repo_url, project['id'], default_branch)

        if mr_info:
            updated_packages = mr_info.get('updated_packages', packages_to_update)

            # Check if this was an existing MR or a new one
            is_existing = 'iid' in mr_info and mr_info.get('state') != 'opened'

            for package_info in updated_packages:
                status = 'Existing' if is_existing else 'Success'
                message = f"Merge request {'found' if is_existing else 'created'}: {mr_info['web_url']}"

                report_generator.add_entry(
                    project['name'], package_info['name'], package_info['version'], status, message
                )
                merge_requests_data.append({
                    'repository_id': project['id'],
                    'repository_name': project['name'],
                    'package_name': package_info['name'],
                    'new_version': package_info['version'],
                    'merge_request_url': mr_info['web_url'],
                    'merge_request_iid': mr_info['iid'],
                    'target_branch': mr_info.get('target_branch', default_branch),
                    'source_branch': mr_info.get('source_branch', 'unknown'),
                    'existed': is_existing
                })

            # Log success message
            if len(updated_packages) == 1:
                action_word = 'Found existing' if is_existing else 'Successfully created'
                logging.info(f"{action_word} merge request for {updated_packages[0]['name']} in {project['name']}")
            else:
                package_names = [pkg['name'] for pkg in updated_packages]
                action_word = 'Found existing' if is_existing else 'Successfully created'
                logging.info(f"{action_word} merge request for {len(updated_packages)} packages ({', '.join(package_names)}) in {project['name']}")
        else:
            # If no MR was created/found, add failure entries for all packages
            for package_info in packages_to_update:
                report_generator.add_entry(
                    project['name'], package_info['name'], package_info['version'], 'Failed',
                    'No updates needed or failed to create merge request'
                )

    def _finalize_execution(self, args: Any, report_generator: ReportGenerator,
                          merge_requests_data: List[Dict]) -> None:
        """Finalize execution by generating reports and saving tracking data."""
        # Get report file from args or config
        report_file = getattr(args, 'report_file', None)
        if not report_file and self.config_service:
            report_file = self.config_service.get('report_file')

        if report_file:
            try:
                report_generator.generate(report_file)
            except PermissionError:
                logging.error(f"Failed to generate report: Permission denied to write to {report_file}")

        if merge_requests_data:
            # Generate unique tracking file name with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            tracking_file = f"multi_package_MRs_{timestamp}.json"

            with open(tracking_file, 'w') as f:
                json.dump({'merge_requests': merge_requests_data}, f, indent=2)
            print(f"Merge request tracking data saved to: {tracking_file}")


class CheckStatusCommandHandler:
    """Handles the check-status command execution."""

    def __init__(self, scm_provider: ScmProvider):
        self.scm_provider = scm_provider

    def execute(self, args: Any) -> None:
        """Execute the check-status command."""
        action = StatusCheckAction(self.scm_provider, args.tracking_file, args.report_only)
        action.execute()

        if args.report_file:
            action.generate_status_report(args.report_file)

        if args.html_dashboard:
            action.generate_html_visualization(args.html_dashboard)

        if args.filter_status:
            filtered_mrs = action.filter_by_status(args.filter_status)
            for mr in filtered_mrs:
                print(f"- {mr['repository_name']}: {mr['merge_request_url']}")
