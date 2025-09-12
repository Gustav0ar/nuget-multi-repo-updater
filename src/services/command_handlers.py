"""
Command handlers for different application actions.
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


class UpdateNugetCommandHandler:
    """Handles the update-nuget command execution."""

    def __init__(self, scm_provider: ScmProvider, config_service: ConfigurationService):
        self.scm_provider = scm_provider
        self.config_service = config_service

    def execute(self, args: Any) -> None:
        """Execute the update-nuget command."""
        # Import here to avoid circular imports
        from src.services.repository_manager import RepositoryManager
        from src.services.dry_run_service import DryRunService
        from src.services.user_interaction_service import UserInteractionService

        repository_manager = RepositoryManager(self.scm_provider)
        dry_run_service = DryRunService(self.scm_provider)
        user_interaction = UserInteractionService()

        # Parse packages to update
        packages_to_update = self._parse_packages_to_update(args)

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

        # Execute actual updates
        self._execute_updates(repositories, packages_to_update, args)

    def _parse_packages_to_update(self, args: Any) -> List[Dict[str, str]]:
        """Parse and validate packages to update."""
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
