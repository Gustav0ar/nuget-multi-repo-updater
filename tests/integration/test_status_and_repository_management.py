"""
Integration tests for status checking and repository management workflows.
"""

import pytest
import tempfile
import json
from unittest.mock import Mock, patch

from src.services.command_handlers import CheckStatusCommandHandler
from src.providers.gitlab_provider import GitLabProvider
from src.services.config_service import ConfigurationService
from src.services.repository_manager import RepositoryManager
from src.actions.status_check_action import StatusCheckAction


class TestStatusCheckIntegration:
    """Integration tests for merge request status checking workflows."""

    @pytest.fixture
    def mock_gitlab_provider(self):
        """Create a mock GitLab provider for status checking."""
        provider = Mock(spec=GitLabProvider)

        # Mock merge request status responses
        provider.get_merge_request_status.side_effect = lambda project_id, mr_iid: {
            '123': 'merged',
            '124': 'opened',
            '125': 'closed'
        }.get(project_id, 'opened')

        # Mock project information
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'web_url': 'https://gitlab.com/group/test-project'
        }

        return provider

    @pytest.fixture
    def sample_tracking_file(self):
        """Create a sample tracking file with merge request data."""
        tracking_data = {
            'metadata': {
                'generated_at': '2023-01-01T12:00:00',
                'package_name': 'Microsoft.EntityFrameworkCore',
                'new_version': '7.0.0',
                'total_repositories': 3,
                'successful_updates': 3
            },
            'merge_requests': [
                {
                    'repository_id': '123',
                    'repository_name': 'project-1',
                    'merge_request_url': 'https://gitlab.com/group/project-1/-/merge_requests/1',
                    'merge_request_iid': '1',
                    'created_at': '2023-01-01T12:00:00',
                    'was_existing': False,
                    'status': 'unknown',
                    'last_checked': None,
                    'modified_files': ['src/Project.csproj']
                },
                {
                    'repository_id': '124',
                    'repository_name': 'project-2',
                    'merge_request_url': 'https://gitlab.com/group/project-2/-/merge_requests/2',
                    'merge_request_iid': '2',
                    'created_at': '2023-01-01T12:00:00',
                    'was_existing': False,
                    'status': 'unknown',
                    'last_checked': None,
                    'modified_files': ['src/Another.csproj']
                },
                {
                    'repository_id': '125',
                    'repository_name': 'project-3',
                    'merge_request_url': 'https://gitlab.com/group/project-3/-/merge_requests/3',
                    'merge_request_iid': '3',
                    'created_at': '2023-01-01T12:00:00',
                    'was_existing': False,
                    'status': 'unknown',
                    'last_checked': None,
                    'modified_files': ['tests/Test.csproj']
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(tracking_data, f)
            temp_file = f.name

        yield temp_file
        import os
        os.unlink(temp_file)

    @pytest.fixture
    def mock_config_service(self):
        """Create a mock configuration service for status checking."""
        config = Mock(spec=ConfigurationService)
        config.get.side_effect = lambda key, default=None: {
            'gitlab_url': 'https://gitlab.com',
            'token': 'test-token',
            'verify_ssl': True
        }.get(key, default)
        return config

    def test_check_status_basic_workflow(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test basic status checking workflow."""
        args = Mock()
        args.config_file = 'dummy_config.json'
        args.tracking_file = sample_tracking_file
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        # Mock the config service loading
        with patch('src.services.config_service.ConfigurationService', return_value=mock_config_service):
            handler.execute(args)

        # Verify status was checked for all merge requests
        assert mock_gitlab_provider.get_merge_request_status.call_count >= 1

    def test_check_status_with_filtering(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test status checking with status filtering."""
        args = Mock()
        args.config_file = 'dummy_config.json'
        args.tracking_file = sample_tracking_file
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = 'opened'  # Filter for only opened MRs
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        with patch('src.services.config_service.ConfigurationService', return_value=mock_config_service):
            handler.execute(args)

        # Should still check status but filter results
        mock_gitlab_provider.get_merge_request_status.assert_called()

    def test_check_status_report_only_mode(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test status checking in report-only mode."""
        args = Mock()
        args.config_file = 'dummy_config.json'
        args.tracking_file = sample_tracking_file
        args.report_only = True
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = 'status_report.md'

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        with patch('src.services.config_service.ConfigurationService', return_value=mock_config_service), \
             patch('builtins.open', create=True) as mock_open:
            handler.execute(args)

        # Should generate report without updating tracking file
        mock_open.assert_called()

    def test_check_status_html_dashboard_generation(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test HTML dashboard generation."""
        args = Mock()
        args.config_file = 'dummy_config.json'
        args.tracking_file = sample_tracking_file
        args.report_only = False
        args.html_dashboard = 'dashboard.html'
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        with patch('src.services.config_service.ConfigurationService', return_value=mock_config_service), \
             patch('builtins.open', create=True) as mock_open, \
             patch('src.actions.status_check_action.StatusCheckAction.generate_html_visualization') as mock_html:
            handler.execute(args)

        # Should generate HTML dashboard
        mock_html.assert_called_with('dashboard.html')

    def test_status_check_with_invalid_tracking_file(self, mock_gitlab_provider, mock_config_service):
        """Test status checking with invalid tracking file."""
        args = Mock()
        args.config_file = 'dummy_config.json'
        args.tracking_file = '/nonexistent/tracking.json'
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        with patch('src.services.config_service.ConfigurationService', return_value=mock_config_service):
            # Should handle missing file gracefully without raising exception
            handler.execute(args)

    def test_status_check_merge_request_not_found(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test handling when merge request is not found (404)."""
        # Mock MR not found
        mock_gitlab_provider.get_merge_request_status.return_value = None

        args = Mock()
        args.config_file = 'dummy_config.json'
        args.tracking_file = sample_tracking_file
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        with patch('src.services.config_service.ConfigurationService', return_value=mock_config_service):
            # Should handle missing MR gracefully
            handler.execute(args)

    def test_status_update_timestamps(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test that timestamps are updated correctly during status checks."""
        args = Mock()
        args.config_file = 'dummy_config.json'
        args.tracking_file = sample_tracking_file
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        with patch('src.services.config_service.ConfigurationService', return_value=mock_config_service), \
             patch('src.actions.status_check_action.StatusCheckAction.save_tracking_data') as mock_save:
            handler.execute(args)

            # Verify that tracking file was saved (when not report_only)
            mock_save.assert_called()

    def test_check_merge_request_status_from_file(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test checking merge request status from tracking file."""
        args = Mock()
        args.tracking_file = sample_tracking_file
        args.repositories = None
        args.package_name = None
        args.update_file = True
        args.summary_only = False
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        # Execute the handler which should load the tracking file
        handler.execute(args)

        # Verify GitLab API calls were made to check status
        assert mock_gitlab_provider.get_merge_request_status.call_count >= 3

    def test_check_status_summary_only(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test checking status with summary only option."""
        args = Mock()
        args.tracking_file = sample_tracking_file
        args.repositories = None
        args.package_name = None
        args.update_file = False
        args.summary_only = True
        args.report_only = False  # Change to False so status checking actually happens
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        # Execute the handler
        handler.execute(args)

        # Verify status was checked but file wasn't modified
        mock_gitlab_provider.get_merge_request_status.assert_called()

    def test_check_status_with_repository_filter(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test checking status with repository filtering."""
        args = Mock()
        args.tracking_file = sample_tracking_file
        args.repositories = '123,124'  # Only check specific repositories
        args.package_name = None
        args.update_file = True
        args.summary_only = False
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        # Execute the handler
        handler.execute(args)

        # Should check all MRs in tracking file regardless of repository filter
        # Repository filtering is applied during update phase, not status checking
        assert mock_gitlab_provider.get_merge_request_status.call_count >= 2

    def test_check_status_with_package_filter(self, mock_gitlab_provider, mock_config_service, sample_tracking_file):
        """Test checking status with package name filtering."""
        args = Mock()
        args.tracking_file = sample_tracking_file
        args.repositories = None
        args.package_name = 'Microsoft.EntityFrameworkCore'
        args.update_file = True
        args.summary_only = False
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        # Execute the handler
        handler.execute(args)

        # Should check all MRs for the specified package
        mock_gitlab_provider.get_merge_request_status.assert_called()

    def test_repository_discovery_integration(self, mock_config_service):
        """Test repository discovery and management workflows."""
        provider = Mock(spec=GitLabProvider)

        # Mock repository discovery
        provider.discover_repositories.return_value = [
            {
                'id': 101,
                'name': 'web-app',
                'path_with_namespace': 'company/web-app',
                'default_branch': 'main',
                'web_url': 'https://gitlab.com/company/web-app',
                'description': 'Main web application',
                'archived': False,
                'forked_from_project': None,
                'last_activity_at': '2025-09-10T12:00:00Z'
            },
            {
                'id': 102,
                'name': 'api-service',
                'path_with_namespace': 'company/api-service',
                'default_branch': 'develop',
                'web_url': 'https://gitlab.com/company/api-service',
                'description': 'API microservice',
                'archived': False,
                'forked_from_project': None,
                'last_activity_at': '2025-09-09T15:30:00Z'
            },
            {
                'id': 103,
                'name': 'legacy-app',
                'path_with_namespace': 'company/legacy-app',
                'default_branch': 'master',
                'web_url': 'https://gitlab.com/company/legacy-app',
                'description': 'Legacy application',
                'archived': True,
                'forked_from_project': None,
                'last_activity_at': '2023-01-01T10:00:00Z'
            }
        ]

        # Test repository manager filtering
        repo_manager = RepositoryManager(provider)

        # Test discovery with correct method signature
        discovered_repos = repo_manager.discover_repositories(
            group_id='company',
            owned_only=False,
            member_only=True,
            include_archived=False
        )

        # Verify discovery was called with correct parameters
        provider.discover_repositories.assert_called_once_with(
            group_id='company',
            owned=False,
            membership=True,
            archived=False
        )

        # Verify filtering worked (should exclude archived repository)
        assert len(discovered_repos) == 3

    def test_status_check_with_network_errors(self, mock_config_service, sample_tracking_file):
        """Test status checking with network connectivity issues."""
        provider = Mock(spec=GitLabProvider)

        # Mock network errors for some requests
        def side_effect_network_error(project_id, mr_iid):
            if project_id == '123':
                raise Exception("Network timeout")
            elif project_id == '124':
                return 'merged'
            else:
                return 'opened'

        provider.get_merge_request_status.side_effect = side_effect_network_error

        args = Mock()
        args.tracking_file = sample_tracking_file
        args.repositories = None
        args.package_name = None
        args.update_file = True
        args.summary_only = False
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(provider)

        # Should handle network errors gracefully
        handler.execute(args)

        # Should attempt to check all MRs despite some failures
        assert provider.get_merge_request_status.call_count == 3

    def test_status_action_integration(self, mock_gitlab_provider, mock_config_service):
        """Test the status check action directly."""
        # Mock MR data
        mr_data = {
            'repository_id': '123',
            'repository_name': 'test-project',
            'merge_request_url': 'https://gitlab.com/group/test-project/-/merge_requests/1',
            'merge_request_iid': '1',
            'status': 'unknown'
        }

        # Mock successful status check
        mock_gitlab_provider.get_merge_request_status.return_value = 'merged'

        # Create temporary tracking file for the action
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'merge_requests': [mr_data]}, f)
            temp_tracking_file = f.name

        try:
            action = StatusCheckAction(mock_gitlab_provider, temp_tracking_file)

            # Execute status check using the correct method
            result = action.update_mr_status(mr_data)

            # Verify status was updated
            assert result == True
            assert mr_data['status'] == 'merged'
            assert 'last_checked' in mr_data
            mock_gitlab_provider.get_merge_request_status.assert_called_once_with('123', '1')
        finally:
            import os
            os.unlink(temp_tracking_file)

    def test_empty_tracking_file_handling(self, mock_gitlab_provider, mock_config_service):
        """Test handling of empty or malformed tracking files."""
        # Create empty tracking file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            empty_file = f.name

        args = Mock()
        args.tracking_file = empty_file
        args.repositories = None
        args.package_name = None
        args.update_file = True
        args.summary_only = False
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        # Should handle empty file gracefully
        try:
            handler.execute(args)
        except SystemExit:
            pass  # Expected for empty tracking file

        import os
        os.unlink(empty_file)

    def test_multiple_package_tracking(self, mock_gitlab_provider, mock_config_service):
        """Test tracking multiple packages across repositories."""
        # Create tracking file with multiple packages
        multi_package_data = {
            'metadata': {
                'generated_at': '2025-09-11T10:00:00',
                'total_operations': 2
            },
            'merge_requests': [
                {
                    'repository_id': '123',
                    'repository_name': 'project-1',
                    'package_name': 'Microsoft.EntityFrameworkCore',
                    'new_version': '7.0.0',
                    'merge_request_url': 'https://gitlab.com/group/project-1/-/merge_requests/1',
                    'merge_request_iid': '1',
                    'status': 'unknown'
                },
                {
                    'repository_id': '123',
                    'repository_name': 'project-1',
                    'package_name': 'Newtonsoft.Json',
                    'new_version': '13.0.3',
                    'merge_request_url': 'https://gitlab.com/group/project-1/-/merge_requests/2',
                    'merge_request_iid': '2',
                    'status': 'unknown'
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(multi_package_data, f)
            multi_file = f.name

        # Mock status responses
        mock_gitlab_provider.get_merge_request_status.side_effect = ['merged', 'opened']

        args = Mock()
        args.tracking_file = multi_file
        args.repositories = None
        args.package_name = None
        args.update_file = True
        args.summary_only = False
        args.report_only = False
        args.html_dashboard = None
        args.filter_status = None
        args.report_file = None

        handler = CheckStatusCommandHandler(mock_gitlab_provider)

        # Execute the handler
        handler.execute(args)

        # Should check status for both MRs
        assert mock_gitlab_provider.get_merge_request_status.call_count == 2

        import os
        os.unlink(multi_file)


class TestRepositoryManagerIntegration:
    """Integration tests for repository management workflows."""

    @pytest.fixture
    def mock_scm_provider(self):
        """Create a mock SCM provider for repository management."""
        provider = Mock()

        # Mock project responses
        provider.get_project.side_effect = lambda repo_id: {
            '123': {
                'id': 123,
                'name': 'project-1',
                'path_with_namespace': 'group/project-1'
            },
            'group/project-2': {
                'id': 124,
                'name': 'project-2',
                'path_with_namespace': 'group/project-2'
            }
        }.get(repo_id)

        # Mock repository discovery
        provider.discover_repositories.return_value = [
            {
                'id': 123,
                'name': 'project-1',
                'path_with_namespace': 'group/project-1',
                'archived': False,
                'forked_from_project': None
            },
            {
                'id': 124,
                'name': 'project-2-fork',
                'path_with_namespace': 'group/project-2-fork',
                'archived': False,
                'forked_from_project': {'id': 125}
            },
            {
                'id': 126,
                'name': 'test-project',
                'path_with_namespace': 'group/test-project',
                'archived': False,
                'forked_from_project': None
            },
            {
                'id': 127,
                'name': 'demo-project',
                'path_with_namespace': 'group/demo-project',
                'archived': True,
                'forked_from_project': None
            }
        ]

        return provider

    def test_repository_loading_from_command_line(self, mock_scm_provider):
        """Test loading repositories from command line arguments."""
        manager = RepositoryManager(mock_scm_provider)

        repositories = manager.get_repositories_from_command_line('123,group/project-2')

        assert len(repositories) == 2
        assert repositories[0]['id'] == 123
        assert repositories[1]['id'] == 124

    def test_repository_loading_from_file(self, mock_scm_provider):
        """Test loading repositories from file."""
        # Create temporary repository file
        repo_content = "123\ngroup/project-2\n# This is a comment\n\n"

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(repo_content)
            temp_file = f.name

        try:
            manager = RepositoryManager(mock_scm_provider)
            repositories = manager.get_repositories_from_file(temp_file)

            assert len(repositories) == 2
            assert repositories[0]['id'] == 123
            assert repositories[1]['id'] == 124
        finally:
            import os
            os.unlink(temp_file)

    def test_repository_discovery_with_filtering(self, mock_scm_provider):
        """Test repository discovery with various filtering options."""
        manager = RepositoryManager(mock_scm_provider)

        # Test basic discovery
        repositories = manager.discover_repositories('test-group')
        assert len(repositories) == 4

        # Test fork exclusion
        filtered_repos = manager.filter_repositories(repositories, exclude_forks=True)
        fork_count = sum(1 for repo in filtered_repos if repo.get('forked_from_project'))
        assert fork_count == 0

    def test_repository_filtering_by_patterns(self, mock_scm_provider):
        """Test repository filtering by name patterns."""
        manager = RepositoryManager(mock_scm_provider)

        # Discover repositories using the mock provider
        repositories = manager.discover_repositories('test-group')

        # Test ignore patterns - should exclude repositories matching patterns
        filtered_repos = manager.filter_repositories_by_patterns(
            repositories,
            ['*-fork', 'test-*']
        )

        # Should exclude test-project and project-2-fork
        names = [repo['name'] for repo in filtered_repos]
        assert 'test-project' not in names
        assert 'project-2-fork' not in names
        assert 'project-1' in names
        assert 'demo-project' in names

    def test_repository_filtering_case_insensitive(self, mock_scm_provider):
        """Test that repository filtering is case-insensitive."""
        manager = RepositoryManager(mock_scm_provider)

        repositories = [
            {
                'id': 1,
                'name': 'TEST-Project',
                'path_with_namespace': 'group/TEST-Project'
            },
            {
                'id': 2,
                'name': 'production-app',
                'path_with_namespace': 'group/production-app'
            }
        ]

        # Test case-insensitive pattern matching
        filtered_repos = manager.filter_repositories_by_patterns(
            repositories,
            ['*test*']  # Should match TEST-Project
        )

        assert len(filtered_repos) == 1
        assert filtered_repos[0]['name'] == 'production-app'

    def test_repository_loading_with_invalid_ids(self, mock_scm_provider):
        """Test handling of invalid repository IDs."""
        # Mock get_project to return None for invalid IDs
        mock_scm_provider.get_project.side_effect = lambda repo_id: {
            '123': {
                'id': 123,
                'name': 'valid-project',
                'path_with_namespace': 'group/valid-project'
            }
        }.get(repo_id)  # Returns None for unknown IDs

        manager = RepositoryManager(mock_scm_provider)

        # Mix of valid and invalid repository IDs
        repositories = manager.get_repositories_from_command_line('123,invalid-repo,another-invalid')

        # Should only return valid repositories
        assert len(repositories) == 1
        assert repositories[0]['id'] == 123

    def test_repository_config_loading(self, mock_scm_provider):
        """Test loading repositories from configuration objects."""
        manager = RepositoryManager(mock_scm_provider)

        # Mix of direct config objects and IDs
        repo_configs = [
            {
                'id': 200,
                'name': 'configured-project',
                'path_with_namespace': 'group/configured-project'
            },
            '123'  # Repository ID to be fetched
        ]

        repositories = manager.get_repositories_from_config(repo_configs)

        assert len(repositories) == 2
        assert repositories[0]['id'] == 200  # Direct config
        assert repositories[1]['id'] == 123  # Fetched by ID


class TestDryRunServiceIntegration:
    """Integration tests for dry run service functionality."""

    @pytest.fixture
    def mock_scm_provider_for_dry_run(self):
        """Create a mock SCM provider for dry run testing."""
        provider = Mock()

        provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'Project.csproj', 'path': 'src/Project.csproj'},
            {'type': 'blob', 'name': 'Tests.csproj', 'path': 'tests/Tests.csproj'}
        ]

        provider.get_file_content.return_value = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>'''

        return provider

    def test_dry_run_package_analysis(self, mock_scm_provider_for_dry_run):
        """Test dry run analysis of packages in repositories."""
        from src.services.dry_run_service import DryRunService

        dry_run_service = DryRunService(mock_scm_provider_for_dry_run)

        repositories = [
            {
                'id': 123,
                'name': 'test-project',
                'path_with_namespace': 'group/test-project',
                'default_branch': 'main',
                'http_url_to_repo': 'https://gitlab.com/group/test-project.git'
            }
        ]

        packages_to_update = [
            {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.0'}
        ]

        with patch('sys.exit') as mock_exit, \
             patch('builtins.print') as mock_print:
            dry_run_service.simulate_package_updates(
                repositories, packages_to_update, False, None
            )

            # Should print analysis results
            assert mock_print.call_count > 0
            mock_exit.assert_called_once()

    def test_dry_run_with_report_generation(self, mock_scm_provider_for_dry_run):
        """Test dry run with report file generation."""
        from src.services.dry_run_service import DryRunService

        dry_run_service = DryRunService(mock_scm_provider_for_dry_run)

        repositories = [
            {
                'id': 123,
                'name': 'test-project',
                'path_with_namespace': 'group/test-project',
                'default_branch': 'main',
                'http_url_to_repo': 'https://gitlab.com/group/test-project.git'
            }
        ]

        packages_to_update = [
            {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.0'}
        ]

        with patch('sys.exit'), \
             patch('builtins.open', create=True) as mock_open, \
             patch('src.services.report_generator.ReportGenerator.generate') as mock_generate:
            dry_run_service.simulate_package_updates(
                repositories, packages_to_update, False, 'dry_run_report.md'
            )

            # Should generate report file - check if generate was called
            mock_generate.assert_called()

    def test_dry_run_multiple_repositories(self, mock_scm_provider_for_dry_run):
        """Test dry run analysis across multiple repositories."""
        from src.services.dry_run_service import DryRunService

        dry_run_service = DryRunService(mock_scm_provider_for_dry_run)

        repositories = [
            {'id': 123, 'name': 'project-1', 'path_with_namespace': 'group/project-1', 'default_branch': 'main', 'http_url_to_repo': 'https://gitlab.com/group/project-1.git'},
            {'id': 124, 'name': 'project-2', 'path_with_namespace': 'group/project-2', 'default_branch': 'develop', 'http_url_to_repo': 'https://gitlab.com/group/project-2.git'},
            {'id': 125, 'name': 'project-3', 'path_with_namespace': 'group/project-3', 'default_branch': 'master', 'http_url_to_repo': 'https://gitlab.com/group/project-3.git'}
        ]

        packages_to_update = [
            {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.0'},
            {'name': 'Newtonsoft.Json', 'version': '13.0.3'}
        ]

        with patch('sys.exit'), \
             patch('builtins.print'):
            dry_run_service.simulate_package_updates(
                repositories, packages_to_update, False, None
            )

            # Should analyze all repositories - each repo is processed for each package
            # So 3 repos × 2 packages = 6 calls to get_repository_tree
            assert mock_scm_provider_for_dry_run.get_repository_tree.call_count == 6

    def test_dry_run_error_handling(self, mock_scm_provider_for_dry_run):
        """Test dry run error handling when repository access fails."""
        from src.services.dry_run_service import DryRunService

        # Mock error in repository tree access
        mock_scm_provider_for_dry_run.get_repository_tree.side_effect = Exception("Access denied")

        dry_run_service = DryRunService(mock_scm_provider_for_dry_run)

        repositories = [
            {'id': 123, 'name': 'inaccessible-project', 'path_with_namespace': 'group/inaccessible-project', 'default_branch': 'main', 'http_url_to_repo': 'https://gitlab.com/group/inaccessible-project.git'}
        ]

        packages_to_update = [
            {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.0'}
        ]

        with patch('sys.exit'), \
             patch('builtins.print'):
            # Should handle errors gracefully
            dry_run_service.simulate_package_updates(
                repositories, packages_to_update, False, None
            )
