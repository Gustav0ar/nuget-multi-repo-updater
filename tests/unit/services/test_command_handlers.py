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
        mock_report_instance.generate_markdown_report.assert_called_once_with('test_report', results=[{
            'web_url': 'https://gitlab.com/test/repo/-/merge_requests/1',
            'iid': 1,
            'target_branch': 'main',
            'source_branch': 'update-package'
        }])

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
        # Mock config service to return {} for 'discover' and ['123', '456'] for 'repositories'
        def mock_get(key, default=None):
            if key == 'discover':
                return {}
            elif key == 'repositories':
                return ['123', '456']
            return default
        
        self.mock_config_service.get.side_effect = mock_get
        mock_repo_manager.get_repositories_from_config.return_value = self.sample_repositories

        result = self.handler._get_repositories(args, mock_repo_manager, None)

        assert result == self.sample_repositories
        # Verify both calls were made
        assert self.mock_config_service.get.call_count == 2
        self.mock_config_service.get.assert_any_call('discover', {})
        self.mock_config_service.get.assert_any_call('repositories', [])
        mock_repo_manager.get_repositories_from_config.assert_called_once_with(['123', '456'])

    def test_get_repositories_no_repositories(self):
        """Test getting repositories when none are specified."""
        args = Namespace(
            repositories=None,
            repo_file=None,
            discover_group=None
        )

        mock_repo_manager = Mock()
        # Mock config service to return {} for 'discover' and [] for 'repositories'
        def mock_get(key, default=None):
            if key == 'discover':
                return {}
            elif key == 'repositories':
                return []
            return default
        
        self.mock_config_service.get.side_effect = mock_get
        # Mock repository manager to return empty list when called with empty config
        mock_repo_manager.get_repositories_from_config.return_value = []

        # Since the actual sys.exit is hard to test, let's verify the logging call instead
        with patch('src.services.command_handlers.logging.error') as mock_logging:
            with patch('src.services.command_handlers.sys.exit') as mock_exit:
                self.handler._get_repositories(args, mock_repo_manager, None)
                mock_logging.assert_called_with("No repositories specified. Use --repositories, --repo-file, --discover-group, or specify repositories/discover config in config file.")
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
            max_repositories=None,
            use_local_clone=False,
            use_most_recent_branch=False,  # Explicitly disable
            branch_filter=None
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        mock_dry_run_instance = mock_dry_run.return_value

        self.handler.execute(args)

        # Verify dry run service was called with repositories that include target_branch (same as default_branch when not using most recent)
        called_args = mock_dry_run_instance.simulate_package_updates.call_args[0]
        repositories_passed = called_args[0]
        
        assert len(repositories_passed) == 1
        assert repositories_passed[0]['target_branch'] == 'main'  # Should be same as default_branch
        assert called_args[1] == [{'name': 'Package1', 'version': '1.0.0'}]
        assert called_args[2] == False  # allow_downgrade
        assert called_args[3] == 'test_report'  # report_file
        assert called_args[4] == False  # use_local_clone

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    def test_execute_dry_run_mode_with_local_clone(self, mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test dry run execution with use_local_clone enabled."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=['123'],
            repo_file=None,
            discover_group=None,
            dry_run=True,
            allow_downgrade=False,
            report_file='test_report',
            max_repositories=None,
            use_local_clone=True,
            use_most_recent_branch=False,  # Explicitly disable
            branch_filter=None
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        mock_dry_run_instance = mock_dry_run.return_value

        self.handler.execute(args)

        # Verify dry run service was called with use_local_clone=True
        called_args = mock_dry_run_instance.simulate_package_updates.call_args[0]
        repositories_passed = called_args[0]
        
        assert len(repositories_passed) == 1
        assert repositories_passed[0]['target_branch'] == 'main'  # Should be same as default_branch
        assert called_args[1] == [{'name': 'Package1', 'version': '1.0.0'}]
        assert called_args[2] == False  # allow_downgrade
        assert called_args[3] == 'test_report'  # report_file
        assert called_args[4] == True  # use_local_clone

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    def test_execute_dry_run_mode_with_local_clone_from_config(self, mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test dry run execution with use_local_clone from config."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=['123'],
            repo_file=None,
            discover_group=None,
            dry_run=True,
            allow_downgrade=False,
            report_file=None, # Not in args
            max_repositories=None,
            use_local_clone=None,  # Not provided via args
            use_most_recent_branch=None,  # Not provided via args
            branch_filter=None
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        mock_dry_run_instance = mock_dry_run.return_value
        
        def mock_config_get(key, default=None):
            if key == 'use_local_clone':
                return True
            elif key == 'report_file':
                return 'test_report_from_config'
            elif key == 'use_most_recent_branch':
                return False
            elif key == 'branch_filter':
                return None
            return default
        
        self.mock_config_service.get.side_effect = mock_config_get

        self.handler.execute(args)

        # Verify dry run service was called with use_local_clone=True and report file from config
        called_args = mock_dry_run_instance.simulate_package_updates.call_args[0]
        repositories_passed = called_args[0]
        
        assert len(repositories_passed) == 1
        assert repositories_passed[0]['target_branch'] == 'main'  # Should be same as default_branch
        assert called_args[1] == [{'name': 'Package1', 'version': '1.0.0'}]
        assert called_args[2] == False  # allow_downgrade
        assert called_args[3] == 'test_report_from_config'  # report_file
        assert called_args[4] == True  # use_local_clone

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
            {'id': 123, 'name': 'repo1', 'default_branch': 'main'},
            {'id': 456, 'name': 'repo2', 'default_branch': 'main'},
            {'id': 789, 'name': 'repo3', 'default_branch': 'main'}
        ]
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = large_repo_list

        mock_dry_run_instance = mock_dry_run.return_value

        self.handler.execute(args)

        # Verify only first 2 repositories were passed to dry run
        called_args = mock_dry_run_instance.simulate_package_updates.call_args[0]
        repositories_passed = called_args[0]
        assert len(repositories_passed) == 2  # Should be limited to 2
        assert repositories_passed[0]['id'] == 123
        assert repositories_passed[1]['id'] == 456
        # Each should have target_branch set
        assert all('target_branch' in repo for repo in repositories_passed)

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
        # Mock config service to return {} for 'discover' and [] for 'repositories'
        def mock_get(key, default=None):
            if key == 'discover':
                return {}
            elif key == 'repositories':
                return []
            return default
        
        self.mock_config_service.get.side_effect = mock_get
        # Add the missing mock for get_repositories_from_config
        mock_repo_manager_instance.get_repositories_from_config.return_value = []

        with pytest.raises(SystemExit):
            self.handler.execute(args)

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    @patch('src.services.command_handlers.MultiPackageUpdateAction')
    def test_enable_migrations_from_config(self, mock_action, mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test that enable_migrations is correctly read from config file."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=['123'],
            repo_file=None,
            discover_group=None,
            dry_run=False,
            allow_downgrade=False,
            report_file=None,
            max_repositories=None,
            use_local_clone=False,
            enable_migrations=None,  # Not provided via args
            strict_migration_mode=False,
            migration_config=None
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        # Mock config service to return migration_settings
        def mock_config_get(key, default=None):
            if key == 'migration_settings':
                return {'enabled': True}
            if key == 'packages_to_update':
                return []
            return default
        
        self.mock_config_service.get.side_effect = mock_config_get

        with patch('src.services.command_handlers.MigrationConfigurationService'):
            self.handler.execute(args)

        # Verify that MultiPackageUpdateAction is called with enable_migrations=True
        mock_action.assert_called_once()
        action_args, action_kwargs = mock_action.call_args
        assert action_kwargs['enable_migrations'] is True

    def test_get_target_branch_default_behavior(self):
        """Test _get_target_branch returns default branch when use_most_recent_branch is False."""
        args = Namespace(
            use_most_recent_branch=False,
            branch_filter=None
        )
        repo_info = {'id': 123, 'default_branch': 'main'}

        result = self.handler._get_target_branch(repo_info, args)

        assert result == 'main'

    def test_get_target_branch_most_recent_enabled(self):
        """Test _get_target_branch uses most recent branch when enabled."""
        args = Namespace(
            use_most_recent_branch=True,
            branch_filter='*main*'
        )
        repo_info = {'id': 123, 'default_branch': 'main'}

        self.mock_scm_provider.get_most_recent_branch.return_value = 'hotfix-main'

        result = self.handler._get_target_branch(repo_info, args)

        assert result == 'hotfix-main'
        self.mock_scm_provider.get_most_recent_branch.assert_called_once_with('123', '*main*')

    def test_get_target_branch_most_recent_from_config(self):
        """Test _get_target_branch reads settings from config when not in args."""
        args = Namespace(
            use_most_recent_branch=None,
            branch_filter=None
        )
        repo_info = {'id': 123, 'default_branch': 'main'}

        def mock_config_get(key, default=None):
            if key == 'use_most_recent_branch':
                return True
            elif key == 'branch_filter':
                return '*develop*'
            return default

        self.mock_config_service.get.side_effect = mock_config_get
        self.mock_scm_provider.get_most_recent_branch.return_value = 'feature-develop'

        result = self.handler._get_target_branch(repo_info, args)

        assert result == 'feature-develop'
        self.mock_scm_provider.get_most_recent_branch.assert_called_once_with('123', '*develop*')

    def test_get_target_branch_most_recent_fallback_to_default(self):
        """Test _get_target_branch falls back to default when most recent branch not found."""
        args = Namespace(
            use_most_recent_branch=True,
            branch_filter='*nonexistent*'
        )
        repo_info = {'id': 123, 'default_branch': 'main'}

        self.mock_scm_provider.get_most_recent_branch.return_value = None

        result = self.handler._get_target_branch(repo_info, args)

        assert result == 'main'
        self.mock_scm_provider.get_most_recent_branch.assert_called_once_with('123', '*nonexistent*')

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.dry_run_service.DryRunService')
    @patch('src.services.user_interaction_service.UserInteractionService')
    def test_execute_dry_run_with_target_branch(self, mock_user_interaction, mock_dry_run, mock_repo_manager):
        """Test dry run execution with target branch functionality."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=['123'],
            repo_file=None,
            discover_group=None,
            dry_run=True,
            allow_downgrade=False,
            report_file='test_report',
            max_repositories=None,
            use_local_clone=False,
            use_most_recent_branch=True,
            branch_filter='*main*'
        )

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        self.mock_scm_provider.get_most_recent_branch.return_value = 'hotfix-main'

        mock_dry_run_instance = mock_dry_run.return_value

        self.handler.execute(args)

        # Verify dry run service was called with repositories that have target_branch set
        called_args = mock_dry_run_instance.simulate_package_updates.call_args[0]
        repositories_with_target = called_args[0]
        
        assert len(repositories_with_target) == 1
        assert repositories_with_target[0]['target_branch'] == 'hotfix-main'
        self.mock_scm_provider.get_most_recent_branch.assert_called_once_with('123', '*main*')

    @patch('src.services.repository_manager.RepositoryManager')
    @patch('src.services.user_interaction_service.UserInteractionService')
    @patch('src.services.command_handlers.MultiPackageUpdateAction')
    @patch('src.services.git_service.GitService')
    def test_execute_with_target_branch(self, mock_git_service, mock_action, mock_user_interaction, mock_repo_manager):
        """Test actual execution with target branch functionality."""
        args = Namespace(
            packages=['Package1@1.0.0'],
            repositories=['123'],
            repo_file=None,
            discover_group=None,
            dry_run=False,
            allow_downgrade=False,
            report_file=None,
            max_repositories=None,
            use_local_clone=False,
            enable_migrations=False,
            strict_migration_mode=False,
            migration_config=None,
            use_most_recent_branch=True,
            branch_filter='*release*'
        )

        # Mock the config service to return proper values, not Mock objects
        def mock_config_get(key, default=None):
            if key == 'report_file':
                return 'test_report'  # Return a proper string instead of Mock
            if key == 'migration_settings':
                return {}
            if key == 'packages_to_update':
                return []
            return default
        
        self.mock_config_service.get.side_effect = mock_config_get

        mock_repo_manager_instance = mock_repo_manager.return_value
        mock_repo_manager_instance.get_repositories_from_command_line.return_value = self.sample_repositories

        self.mock_scm_provider.get_most_recent_branch.return_value = 'release-v2'

        mock_action_instance = mock_action.return_value
        mock_action_instance.execute.return_value = {
            'web_url': 'https://gitlab.com/test/repo/-/merge_requests/1',
            'iid': 1,
            'target_branch': 'release-v2',
            'source_branch': 'update-package'
        }

        with patch('src.services.command_handlers.MigrationConfigurationService'):
            self.handler.execute(args)

        # Verify that the action was executed with the target branch
        self.mock_scm_provider.get_most_recent_branch.assert_called_once_with('123', '*release*')
        mock_action_instance.execute.assert_called_once_with(
            self.sample_repositories[0]['ssh_url_to_repo'],
            '123',
            'release-v2'  # Should use the target branch, not default 'main'
        )


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
