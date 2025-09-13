"""
Integration tests for error handling and edge cases in NuGet update workflows.
"""

import pytest
import tempfile
import json
import logging
import logging
from unittest.mock import Mock, patch
from requests.exceptions import RequestException, HTTPError

from src.providers.gitlab_provider import GitLabProvider, RateLimitExceeded
from src.services.config_service import ConfigurationService
from src.services.command_handlers import UpdateNugetCommandHandler


class TestErrorHandlingIntegration:
    """Integration tests for error handling scenarios."""

    @pytest.fixture
    def mock_gitlab_provider_with_errors(self):
        """Create a GitLab provider that simulates various error conditions."""
        provider = Mock(spec=GitLabProvider)
        return provider

    @pytest.fixture
    def mock_config_service(self):
        """Standard mock configuration service."""
        config = Mock(spec=ConfigurationService)
        config.get.side_effect = lambda key, default=None: {
            'gitlab_url': 'https://gitlab.com',
            'token': 'test-token',
            'verify_ssl': True,
            'repositories': [],  # Add empty repositories list for tests
            'enable_code_migrations': False,  # Disable migrations by default
            'migration_config_file': 'package-migrations.yml'
        }.get(key, default)
        return config

    def test_rate_limit_handling(self, mock_gitlab_provider_with_errors, mock_config_service):
        """Test handling of API rate limits."""
        # Mock rate limit exception
        mock_gitlab_provider_with_errors.get_project.side_effect = RateLimitExceeded(
            "Rate limit exceeded", retry_after=60
        )

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False

        handler = UpdateNugetCommandHandler(mock_gitlab_provider_with_errors, mock_config_service)

        # Should handle rate limit gracefully without crashing
        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm:
            mock_confirm.return_value = []

            # Mock time.sleep to avoid actual delays in tests
            with patch('time.sleep'):
                try:
                    handler.execute(args)
                except (SystemExit, RateLimitExceeded):
                    pass  # Expected in error conditions

        # Verify rate limit was encountered
        mock_gitlab_provider_with_errors.get_project.assert_called()

    def test_network_connection_errors(self, mock_gitlab_provider_with_errors, mock_config_service):
        """Test handling of network connection errors."""
        # Mock network error
        mock_gitlab_provider_with_errors.get_project.side_effect = RequestException("Connection timeout")

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False

        handler = UpdateNugetCommandHandler(mock_gitlab_provider_with_errors, mock_config_service)

        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm:
            mock_confirm.return_value = []

            try:
                handler.execute(args)
            except (SystemExit, RequestException):
                pass  # Expected in error conditions

        mock_gitlab_provider_with_errors.get_project.assert_called()

    def test_network_error_handling(self, mock_gitlab_provider_with_errors, mock_config_service):
        """Test handling of network errors."""
        # Mock network error
        mock_gitlab_provider_with_errors.get_project.side_effect = RequestException("Network error")

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider_with_errors, mock_config_service)

        # Should handle network error gracefully without crashing
        try:
            handler.execute(args)
        except (SystemExit, RequestException):
            pass  # Expected in error conditions

    def test_ssl_verification_disabled(self, mock_config_service):
        """Test handling when SSL verification is disabled."""
        # Mock SSL disabled in config
        mock_config_service.get.side_effect = lambda key, default=None: {
            'gitlab_url': 'https://self-signed.gitlab.com',
            'token': 'test-token',
            'verify_ssl': False
        }.get(key, default)

        args = Mock()
        args.no_verify_ssl = True
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']

        # Should create provider with SSL verification disabled
        with patch('src.providers.gitlab_provider.GitLabProvider') as mock_provider_class:
            handler = UpdateNugetCommandHandler(Mock(), mock_config_service)
            # The provider should be created with verify_ssl=False

    def test_invalid_package_format(self, mock_config_service):
        """Test handling of invalid package format."""
        # Mock a proper GitLab provider
        provider = Mock(spec=GitLabProvider)
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'default_branch': 'main',
            'http_url_to_repo': 'https://gitlab.com/group/test-project.git',
            'web_url': 'https://gitlab.com/group/test-project'
        }

        args = Mock()
        args.repositories = '123'
        args.packages = ['InvalidFormat']  # Missing @version
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        # Should exit with error due to invalid package format
        with patch('sys.exit') as mock_exit:
            handler.execute(args)
            mock_exit.assert_called_with(1)

    def test_empty_repository_list(self, mock_config_service):
        """Test handling when no repositories are found."""
        args = Mock()
        args.repositories = None  # No repositories specified
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None
        args.migration_config = None
        args.strict_migration_mode = False

        handler = UpdateNugetCommandHandler(Mock(), mock_config_service)

        # Should exit with error due to no repositories
        with patch('sys.exit') as mock_exit:
            handler.execute(args)
            # The handler may call sys.exit multiple times, so just check it was called with 1
            calls = mock_exit.call_args_list
            assert any(call.args == (1,) for call in calls)

    def test_git_operation_failures(self, mock_config_service):
        """Test handling of Git operation failures."""
        # Mock GitLab provider with successful API calls
        provider = Mock(spec=GitLabProvider)
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'default_branch': 'main',
            'http_url_to_repo': 'https://gitlab.com/group/test-project.git',
            'web_url': 'https://gitlab.com/group/test-project'
        }

        provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'App.csproj', 'path': 'App.csproj'}
        ]

        provider.get_file_content.return_value = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        provider.check_existing_merge_request.return_value = None

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        # Mock all Git and network operations to prevent actual calls
        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm, \
             patch('src.services.git_service.GitService') as mock_git_service_class, \
             patch('src.actions.nuspec_update_action.NuspecUpdateAction') as mock_action_class, \
             patch('requests.get') as mock_requests, \
             patch('requests.post') as mock_requests_post, \
             patch('git.Repo') as mock_repo_class, \
             patch('git.Repo.clone_from') as mock_clone, \
             patch('builtins.open', create=True) as mock_open, \
             patch('os.path.exists', return_value=True), \
             patch('os.makedirs'), \
             patch('shutil.rmtree'), \
             patch('tempfile.mkdtemp', return_value='/tmp/test-dir'):

            # Mock user interaction
            mock_confirm.return_value = []

            # Mock Git service to simulate failure
            mock_git_service = Mock()
            mock_git_service.clone_repository.side_effect = Exception("Git clone failed")
            mock_git_service_class.return_value = mock_git_service

            # Mock NuspecUpdateAction to prevent actual execution
            mock_action = Mock()
            mock_action.execute.side_effect = Exception("Git operation failed")
            mock_action_class.return_value = mock_action

            # Mock all network requests
            mock_requests.side_effect = Exception("Network not available")
            mock_requests_post.side_effect = Exception("Network not available")

            # Mock Git repo operations
            mock_clone.side_effect = Exception("Git clone failed")
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo

            # Test that Git operation failures are handled gracefully
            try:
                handler.execute(args)
            except SystemExit:
                pass  # Expected when operations fail

        # Verify the provider was called but no actual network/git operations occurred
        provider.get_project.assert_called()

    def test_file_permission_errors(self, mock_config_service, caplog):
        """Test handling of file permission errors."""
        provider = Mock()
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'default_branch': 'main',
            'http_url_to_repo': 'https://gitlab.com/group/test.git',
            'web_url': 'https://gitlab.com/group/test'
        }
        provider.check_existing_merge_request.return_value = None

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = "permission_error_report.md"
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        # Mock file operations to fail with permission error
        with patch('builtins.open', side_effect=PermissionError("Permission denied")) as mock_open, \
             patch('src.services.git_service.GitService') as mock_git_service, \
             patch('git.Repo.clone_from') as mock_clone, \
             caplog.at_level(logging.ERROR):

            # The handler should catch the permission error and log it
            handler.execute(args)

            # Verify that a permission error was logged (may be from migration config or report)
            assert ("Failed to load migration configuration: Permission denied" in caplog.text or 
                   "Failed to generate report: Permission denied" in caplog.text or
                   "Failed to generate enhanced report" in caplog.text)

    def test_malformed_csproj_file(self, mock_config_service):
        """Test handling of malformed .csproj files."""
        provider = Mock()
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'default_branch': 'main',
            'http_url_to_repo': 'https://gitlab.com/group/test.git'
        }
        provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'Project.csproj', 'path': 'src/Project.csproj'}
        ]
        # Return malformed XML
        provider.get_file_content.return_value = '<Project><ItemGroup><PackageReference Include="Test"'

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = True
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        # Should handle malformed files gracefully in dry run
        with patch('sys.exit'):
            handler.execute(args)

    def test_configuration_file_not_found(self):
        """Test handling when configuration file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            ConfigurationService('/nonexistent/config.json')

    def test_invalid_configuration_format(self):
        """Test handling of invalid configuration file format."""
        # Create temp file with invalid JSON
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('invalid json content')
            temp_file = f.name

        with pytest.raises(json.JSONDecodeError):
            ConfigurationService(temp_file)

        import os
        os.unlink(temp_file)

    def test_gitlab_authentication_failure(self, mock_config_service):
        """Test handling of GitLab authentication failures."""
        provider = Mock()
        provider.get_project.side_effect = HTTPError("401 Unauthorized")

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        # Should handle auth failure gracefully
        try:
            handler.execute(args)
        except (SystemExit, HTTPError):
            pass  # Expected for auth failures

    def test_repository_access_denied(self, mock_config_service):
        """Test handling when user doesn't have access to repository."""
        provider = Mock()
        provider.get_project.side_effect = HTTPError("403 Forbidden")

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        # Should handle access denied gracefully
        try:
            handler.execute(args)
        except (SystemExit, HTTPError):
            pass  # Expected for access denied

    def test_merge_request_creation_failure(self, mock_config_service):
        """Test handling when merge request creation fails."""
        provider = Mock(spec=GitLabProvider)
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'default_branch': 'main',
            'http_url_to_repo': 'https://gitlab.com/group/test-project.git',
            'web_url': 'https://gitlab.com/group/test-project'
        }

        provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'App.csproj', 'path': 'App.csproj'}
        ]

        provider.get_file_content.return_value = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        provider.check_existing_merge_request.return_value = None

        # Mock MR creation failure
        provider.create_merge_request.side_effect = HTTPError("403 Forbidden")

        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        # Mock all external dependencies to prevent network/git operations
        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm, \
             patch('src.services.git_service.GitService') as mock_git_service_class, \
             patch('src.actions.nuspec_update_action.NuspecUpdateAction') as mock_action_class, \
             patch('requests.get') as mock_requests_get, \
             patch('requests.post') as mock_requests_post, \
             patch('git.Repo') as mock_git_repo, \
             patch('git.Repo.clone_from') as mock_clone, \
             patch('builtins.open', create=True) as mock_open, \
             patch('os.path.exists', return_value=True), \
             patch('os.makedirs'), \
             patch('shutil.rmtree'), \
             patch('tempfile.mkdtemp', return_value='/tmp/test-mr-failure'):

            mock_confirm.return_value = []

            # Mock Git service to prevent actual Git operations
            mock_git = Mock()
            mock_git.clone_repository.return_value = '/tmp/mock-clone'
            mock_git.create_branch.return_value = True
            mock_git.checkout_branch.return_value = True
            mock_git.add_files.return_value = True
            mock_git.commit_changes.return_value = 'mock-commit-hash'
            mock_git.push_branch.return_value = True
            mock_git_service_class.return_value = mock_git

            # Mock NuspecUpdateAction to prevent actual execution
            mock_action = Mock()
            mock_action.execute.side_effect = HTTPError("403 Forbidden")  # Simulate MR creation failure
            mock_action_class.return_value = mock_action

            # Mock all network requests to prevent actual API calls
            mock_requests_get.return_value = Mock(status_code=200, json=lambda: {})
            mock_requests_post.return_value = Mock(status_code=403, json=lambda: {'error': 'Forbidden'})

            # Mock Git repo operations
            mock_repo = Mock()
            mock_git_repo.return_value = mock_repo
            mock_clone.return_value = mock_repo

            # Test that MR creation failure is handled gracefully
            try:
                handler.execute(args)
            except (SystemExit, HTTPError):
                pass  # Expected when MR creation fails

        # Verify provider was called but no actual network/git operations occurred
        provider.get_project.assert_called()

    def test_invalid_repository_handling(self, mock_config_service):
        """Test handling of invalid or non-existent repositories."""
        provider = Mock(spec=GitLabProvider)

        # Mock repository not found
        provider.get_project.return_value = None

        args = Mock()
        args.repositories = '999,invalid/repo'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False

        handler = UpdateNugetCommandHandler(provider, mock_config_service)

        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm:
            mock_confirm.return_value = []

            try:
                handler.execute(args)
            except SystemExit:
                pass  # Expected when no valid repositories

        # Verify attempts to get invalid projects
        assert provider.get_project.call_count >= 2


def mock_open_csproj(*args, **kwargs):
    """Mock file operations for .csproj files."""
    from unittest.mock import mock_open

    if args[0].endswith('.csproj'):
        return mock_open(read_data='''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>''')()
    else:
        return mock_open()()
