import pytest
import os
import glob
from unittest.mock import Mock, patch, mock_open, call
from argparse import Namespace

from src.services.command_handlers import UpdateNugetCommandHandler, CheckStatusCommandHandler


class TestUpdateNugetCommandHandler:
    """Test suite for UpdateNugetCommandHandler."""

    def setup_method(self):
        """Set up test dependencies for each test method."""
        self.mock_scm_provider = Mock()
        self.mock_config_service = Mock()
        self.handler = UpdateNugetCommandHandler(self.mock_scm_provider, self.mock_config_service)

        # Track test files that need cleanup
        self.test_files_to_cleanup = []

        # Sample test data
        self.sample_packages = [
            {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.5'},
            {'name': 'Newtonsoft.Json', 'version': '13.0.3'}
        ]

        self.sample_repositories = [
            {
                'id': 123,
                'name': 'test-repo',
                'http_url_to_repo': 'https://gitlab.com/test/repo.git',
                'ssh_url_to_repo': 'git@gitlab.com:test/repo.git',
                'default_branch': 'main'
            }
        ]

    def teardown_method(self):
        """Clean up test files after each test method."""
        # Clean up any test report files that may have been created
        test_patterns = ['test_report*', 'multi_package_MRs.json', 'test_tracking.json']

        for pattern in test_patterns:
            if '*' in pattern:
                # Handle wildcard patterns
                for file_path in glob.glob(pattern):
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except (OSError, PermissionError):
                        pass  # Ignore cleanup errors
            else:
                # Handle specific files
                try:
                    if os.path.exists(pattern):
                        os.remove(pattern)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors

        # Clean up tracked files
        for file_path in self.test_files_to_cleanup:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    @patch('src.services.command_handlers.ReportGenerator')
    @patch('src.services.command_handlers.GitService')
    @patch('src.services.command_handlers.MultiPackageUpdateAction')
    def test_execute_success_with_packages_arg(self, mock_action, mock_git, mock_report,
                                               mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test successful execution with packages from command line arguments."""
        # Setup
        args = Namespace(
            packages=['Microsoft.EntityFrameworkCore@7.0.5'],
            repositories=['123'],
            repo_file=None,
            discover_group=None,
            dry_run=False,
            allow_downgrade=False,
            report_file='test_report',
            max_repositories=None,
            use_local_clone=False,
            enable_migrations=False,
            strict_migration_mode=False
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        mock_project = self.sample_repositories[0]
        self.mock_scm_provider.get_project.return_value = mock_project
        self.mock_scm_provider.check_existing_merge_request.return_value = None

        mock_action_instance = mock_action.return_value
        mock_action_instance.execute.return_value = {
            'web_url': 'https://gitlab.com/test/repo/-/merge_requests/1',
            'iid': 1,
            'target_branch': 'main',
            'source_branch': 'update-package'
        }

        mock_report_instance = mock_report.return_value

        # Execute
        with patch('builtins.open', mock_open()) as mock_file:
            self.handler.execute(args)

        # Verify
        mock_repo_manager_instance.get_repositories_from_command_line.assert_called_once_with(['123'])
        mock_action.assert_called_once()
        mock_report_instance.generate_markdown_report.assert_called_once_with([{
            'web_url': 'https://gitlab.com/test/repo/-/merge_requests/1',
            'iid': 1,
            'target_branch': 'main',
            'source_branch': 'update-package'
        }], 'test_report')

    def test_parse_packages_to_update_from_args(self):
        """Test parsing packages from command line arguments."""
        args = Namespace(packages=['Package1@1.0.0', 'Package2@2.0.0'])

        result = self.handler._parse_packages_to_update(args)

        expected = [
            {'name': 'Package1', 'version': '1.0.0'},
            {'name': 'Package2', 'version': '2.0.0'}
        ]
        assert result == expected

    def test_parse_packages_to_update_from_config(self):
        """Test parsing packages from config service."""
        args = Namespace(packages=None)
        self.mock_config_service.get.return_value = self.sample_packages

        result = self.handler._parse_packages_to_update(args)

        assert result == self.sample_packages
        self.mock_config_service.get.assert_called_once_with('packages_to_update', [])

    def test_parse_packages_to_update_invalid_format(self):
        """Test parsing packages with invalid format."""
        args = Namespace(packages=['invalid-format'])

        with pytest.raises(SystemExit):
            with patch('src.services.command_handlers.logging.error') as mock_logging:
                self.handler._parse_packages_to_update(args)
                mock_logging.assert_called_with("Invalid package format: invalid-format. Expected 'name@version'.")

    def test_parse_packages_to_update_no_packages(self):
        """Test parsing when no packages are specified."""
        args = Namespace(packages=None)
        self.mock_config_service.get.return_value = []

        with pytest.raises(SystemExit):
            with patch('src.services.command_handlers.logging.error') as mock_logging:
                self.handler._parse_packages_to_update(args)
                mock_logging.assert_called_with("No packages specified via --packages argument or in config file.")

    def test_get_repositories_from_command_line(self):
        """Test getting repositories from command line."""
        args = Namespace(
            repositories=['123', '456'],
            repo_file=None,
            discover_group=None
        )

        mock_repo_manager = Mock()
        mock_repo_manager.get_repositories_from_command_line.return_value = self.sample_repositories

        result = self.handler._get_repositories(args, mock_repo_manager, None)

        assert result == self.sample_repositories
        mock_repo_manager.get_repositories_from_command_line.assert_called_once_with(['123', '456'])

    def test_get_repositories_from_file(self):
        """Test getting repositories from file."""
        args = Namespace(
            repositories=None,
            repo_file='repos.txt',
            discover_group=None
        )

        mock_repo_manager = Mock()
        mock_repo_manager.get_repositories_from_file.return_value = self.sample_repositories

        result = self.handler._get_repositories(args, mock_repo_manager, None)

        assert result == self.sample_repositories
        mock_repo_manager.get_repositories_from_file.assert_called_once_with('repos.txt')

    def test_get_repositories_discovery_mode(self):
        """Test getting repositories through discovery mode."""
        args = Namespace(
            repositories=None,
            repo_file=None,
            discover_group='test-group',
            owned_only=True,
            member_only=False,
            include_archived=False,
            ignore_patterns=[],
            exclude_forks=True
        )

        mock_repo_manager = Mock()
        mock_user_interaction = Mock()

        discovered_repos = [{'id': 1, 'name': 'repo1'}, {'id': 2, 'name': 'repo2'}]
        filtered_repos = [{'id': 1, 'name': 'repo1'}]

        mock_repo_manager.discover_repositories.return_value = discovered_repos
        mock_repo_manager.filter_out_forks.return_value = filtered_repos

        result = self.handler._get_repositories(args, mock_repo_manager, mock_user_interaction)

        assert result == filtered_repos
        mock_repo_manager.discover_repositories.assert_called_once_with('test-group', True, False, False)
        mock_repo_manager.filter_out_forks.assert_called_once_with(discovered_repos)
        mock_user_interaction.display_discovered_repositories.assert_called_once_with(filtered_repos)

    def test_get_repositories_from_config(self):
        """Test getting repositories from config service."""
        args = Namespace(
            repositories=None,
            repo_file=None,
            discover_group=None
        )

        mock_repo_manager = Mock()
        self.mock_config_service.get.return_value = ['123', '456']
        mock_repo_manager.get_repositories_from_config.return_value = self.sample_repositories

        result = self.handler._get_repositories(args, mock_repo_manager, None)

        assert result == self.sample_repositories
        self.mock_config_service.get.assert_called_once_with('repositories', [])
        mock_repo_manager.get_repositories_from_config.assert_called_once_with(['123', '456'])

    def test_get_repositories_no_repositories(self):
        """Test getting repositories when none are specified."""
        args = Namespace(
            repositories=None,
            repo_file=None,
            discover_group=None
        )

        mock_repo_manager = Mock()
        # Mock config service to return empty list
        self.mock_config_service.get.return_value = []
        # Mock repository manager to return empty list when called with empty config
        mock_repo_manager.get_repositories_from_config.return_value = []

        # Since the actual sys.exit is hard to test, let's verify the logging call instead
        with patch('src.services.command_handlers.logging.error') as mock_logging:
            with patch('src.services.command_handlers.sys.exit') as mock_exit:
                self.handler._get_repositories(args, mock_repo_manager, None)
                mock_logging.assert_called_with("No repositories specified. Use --repositories, --repo-file, --discover-group, or specify repositories in config file.")
                mock_exit.assert_called_once_with(1)

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    def test_execute_dry_run_mode(self, mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test execution in dry run mode."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=['123'],
            repo_file=None,
            discover_group=None,
            dry_run=True,
            allow_downgrade=False,
            report_file='test_report',
            max_repositories=None
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        mock_dry_run_instance = mock_dry_run.return_value

        self.handler.execute(args)

        # Verify dry run service was called
        mock_dry_run_instance.simulate_package_updates.assert_called_once_with(
            self.sample_repositories, [{'name': 'Package1', 'version': '1.0.0'}], False, 'test_report'
        )

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    def test_execute_with_max_repositories_limit(self, mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test execution with repository limit."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=['123', '456', '789'],
            repo_file=None,
            discover_group=None,
            dry_run=True,
            allow_downgrade=False,
            report_file='test_report',
            max_repositories=2
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        large_repo_list = [
            {'id': 123, 'name': 'repo1'},
            {'id': 456, 'name': 'repo2'},
            {'id': 789, 'name': 'repo3'}
        ]
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = large_repo_list

        mock_dry_run_instance = mock_dry_run.return_value

        self.handler.execute(args)

        # Verify only first 2 repositories were passed to dry run
        called_args = mock_dry_run_instance.simulate_package_updates.call_args[0]
        assert len(called_args[0]) == 2  # repositories argument
        assert called_args[0] == large_repo_list[:2]

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    def test_execute_no_repositories_found(self, mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test execution when no repositories are found."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=None,
            repo_file=None,
            discover_group=None,
            dry_run=False,
            allow_downgrade=False,
            report_file='test_report',
            max_repositories=None
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        self.mock_config_service.get.return_value = []
        # Add the missing mock for get_repositories_from_config
        mock_repo_manager_instance.get_repositories_from_config.return_value = []

        with pytest.raises(SystemExit):
            self.handler.execute(args)


class TestCheckStatusCommandHandler:
    """Test suite for CheckStatusCommandHandler."""

    def setup_method(self):
        """Set up test dependencies for each test method."""
        self.mock_scm_provider = Mock()
        self.handler = CheckStatusCommandHandler(self.mock_scm_provider)

        # Track test files that need cleanup
        self.test_files_to_cleanup = []

    def teardown_method(self):
        """Clean up test files after each test method."""
        # Clean up any test report files that may have been created
        test_patterns = ['test_tracking.json', 'status_report.md', 'dashboard.html']

        for pattern in test_patterns:
            try:
                if os.path.exists(pattern):
                    os.remove(pattern)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors

        # Clean up tracked files
        for file_path in self.test_files_to_cleanup:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors

    @patch('src.services.command_handlers.StatusCheckAction')
    def test_execute_basic(self, mock_action):
        """Test basic execution of check-status command."""
        args = Namespace(
            tracking_file='test_tracking.json',
            report_only=False,
            report_file=None,
            html_dashboard=None,
            filter_status=None
        )

        mock_action_instance = mock_action.return_value

        self.handler.execute(args)

        mock_action.assert_called_once_with(self.mock_scm_provider, 'test_tracking.json', False)
        mock_action_instance.execute.assert_called_once_with()

    @patch('src.services.command_handlers.StatusCheckAction')
    def test_execute_with_report_file(self, mock_action):
        """Test execution with report file generation."""
        args = Namespace(
            tracking_file='test_tracking.json',
            report_only=False,
            report_file='status_report.md',
            html_dashboard=None,
            filter_status=None
        )

        mock_action_instance = mock_action.return_value

        self.handler.execute(args)

        mock_action.assert_called_once_with(self.mock_scm_provider, 'test_tracking.json', False)
        mock_action_instance.execute.assert_called_once()
        mock_action_instance.generate_status_report.assert_called_once_with('status_report.md')

    @patch('src.services.command_handlers.StatusCheckAction')
    def test_execute_with_html_dashboard(self, mock_action):
        """Test execution with HTML dashboard generation."""
        args = Namespace(
            tracking_file='test_tracking.json',
            report_only=False,
            report_file=None,
            html_dashboard='dashboard.html',
            filter_status=None
        )

        mock_action_instance = mock_action.return_value

        self.handler.execute(args)

        mock_action.assert_called_once_with(self.mock_scm_provider, 'test_tracking.json', False)
        mock_action_instance.execute.assert_called_once()
        mock_action_instance.generate_html_visualization.assert_called_once_with('dashboard.html')

    @patch('src.services.command_handlers.StatusCheckAction')
    @patch('builtins.print')
    def test_execute_with_filter_status(self, mock_print, mock_action):
        """Test execution with status filtering."""
        args = Namespace(
            tracking_file='test_tracking.json',
            report_only=False,
            report_file=None,
            html_dashboard=None,
            filter_status='open'
        )

        mock_action_instance = mock_action.return_value
        filtered_mrs = [
            {'repository_name': 'repo1', 'merge_request_url': 'https://gitlab.com/repo1/mr/1'},
            {'repository_name': 'repo2', 'merge_request_url': 'https://gitlab.com/repo2/mr/1'}
        ]
        mock_action_instance.filter_by_status.return_value = filtered_mrs

        self.handler.execute(args)

        mock_action.assert_called_once_with(self.mock_scm_provider, 'test_tracking.json', False)
        mock_action_instance.execute.assert_called_once()
        mock_action_instance.filter_by_status.assert_called_once_with('open')

    @patch('src.services.command_handlers.StatusCheckAction')
    def test_execute_with_all_options(self, mock_action):
        """Test execution with all options enabled."""
        args = Namespace(
            tracking_file='test_tracking.json',
            report_only=True,
            report_file='status_report.md',
            html_dashboard='dashboard.html',
            filter_status='merged'
        )

        mock_action_instance = mock_action.return_value
        mock_action_instance.filter_by_status.return_value = []

        self.handler.execute(args)

        mock_action.assert_called_once_with(self.mock_scm_provider, 'test_tracking.json', True)
        mock_action_instance.execute.assert_called_once_with()
        mock_action_instance.generate_status_report.assert_called_once_with('status_report.md')
        mock_action_instance.generate_html_visualization.assert_called_once_with('dashboard.html')
        mock_action_instance.filter_by_status.assert_called_once_with('merged')

    @patch('src.services.command_handlers.StatusCheckAction')
    def test_execute_report_only_mode(self, mock_action):
        """Test execution in report-only mode."""
        args = Namespace(
            tracking_file='test_tracking.json',
            report_only=True,
            report_file=None,
            html_dashboard=None,
            filter_status=None
        )

        mock_action_instance = mock_action.return_value

        self.handler.execute(args)

        mock_action.assert_called_once_with(self.mock_scm_provider, 'test_tracking.json', True)
        mock_action_instance.execute.assert_called_once_with()

    @patch('src.services.command_handlers.StatusCheckAction')
    def test_execute_filter_status_empty_results(self, mock_action):
        """Test execution with status filtering that returns no results."""
        args = Namespace(
            tracking_file='test_tracking.json',
            report_only=False,
            report_file=None,
            html_dashboard=None,
            filter_status='closed'
        )

        mock_action_instance = mock_action.return_value
        mock_action_instance.filter_by_status.return_value = []

        self.handler.execute(args)

        mock_action.assert_called_once_with(self.mock_scm_provider, 'test_tracking.json', False)
        mock_action_instance.execute.assert_called_once_with()
        mock_action_instance.filter_by_status.assert_called_once_with('closed')
