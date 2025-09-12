"""
Integration tests for NuGet package update flows.

Tests cover the complete end-to-end workflows including:
- Repository discovery
- Package updates
- Merge request creation
- Error handling
- Different input methods

All tests use comprehensive mocking to avoid network calls while preserving functionality testing.
"""

import pytest
import os
import tempfile
import json
from unittest.mock import Mock, patch
from unittest.mock import Mock, patch
import builtins
import unittest

from src.providers.gitlab_provider import GitLabProvider
from src.services.config_service import ConfigurationService
from src.services.command_handlers import UpdateNugetCommandHandler
from src.services.user_interaction_service import UserInteractionService
from src.services.dry_run_service import DryRunService
from src.actions.nuspec_update_action import CSProjUpdater

@pytest.fixture(autouse=True)
def mock_network_calls():
    """Auto-use fixture that mocks all network and external system calls."""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post, \
         patch('requests.put') as mock_put, \
         patch('requests.delete') as mock_delete, \
         patch('git.Repo') as mock_git_repo, \
         patch('git.Repo.clone_from') as mock_clone_from, \
         patch('os.makedirs') as mock_makedirs, \
         patch('shutil.rmtree') as mock_rmtree, \
         patch('tempfile.mkdtemp') as mock_mkdtemp:

        # Mock requests responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.text = "{}"

        mock_get.return_value = mock_response
        mock_post.return_value = mock_response
        mock_put.return_value = mock_response
        mock_delete.return_value = mock_response

        # Mock Git operations
        mock_repo = Mock()
        mock_repo.heads = []
        mock_repo.remotes = Mock()
        mock_repo.remotes.origin = Mock()
        mock_git_repo.return_value = mock_repo
        mock_clone_from.return_value = mock_repo

        # Mock file system operations
        mock_makedirs.return_value = None
        mock_rmtree.return_value = None
        mock_mkdtemp.return_value = '/tmp/test-temp-dir'

        yield {
            'requests_get': mock_get,
            'requests_post': mock_post,
            'requests_put': mock_put,
            'requests_delete': mock_delete,
            'git_repo': mock_git_repo,
            'clone_from': mock_clone_from,
            'makedirs': mock_makedirs,
            'rmtree': mock_rmtree,
            'mkdtemp': mock_mkdtemp,
            'mock_repo': mock_repo
        }


@pytest.fixture
def mock_git_service():
    """Fixture that provides a fully mocked Git service."""
    with patch('src.services.git_service.GitService') as mock_git_service_class:
        mock_git = Mock()
        mock_git.clone_repository.return_value = '/tmp/mock-clone-dir'
        mock_git.create_branch.return_value = True
        mock_git.checkout_branch.return_value = True
        mock_git.add_files.return_value = True
        mock_git.commit_changes.return_value = 'abc123def456'
        mock_git.push_branch.return_value = True
        mock_git.cleanup.return_value = True
        mock_git.get_current_branch.return_value = 'main'
        mock_git.branch_exists.return_value = False
        mock_git_service_class.return_value = mock_git
        yield mock_git


@pytest.fixture
def mock_nuspec_action():
    """Fixture that provides a fully mocked NuspecUpdateAction."""
    with patch('src.actions.nuspec_update_action.NuspecUpdateAction') as mock_action_class:
        mock_action = Mock()
        mock_action.execute.return_value = {
            'id': 456,
            'iid': 1,
            'web_url': 'https://gitlab.com/test/project/-/merge_requests/1',
            'title': 'Update NuGet packages'
        }
        mock_action_class.return_value = mock_action
        yield mock_action


import builtins
original_open = builtins.open

@pytest.fixture
def mock_file_operations():
    """Fixture that mocks file operations without affecting real file system."""
    with patch('builtins.open', create=True) as mock_open, \
         patch('os.path.exists') as mock_exists, \
         patch('os.path.isfile') as mock_isfile, \
         patch('os.path.isdir') as mock_isdir:

        # Configure file system mocks
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_isdir.return_value = True

        def open_side_effect(path, mode='r'):
            try:
                return original_open(path, mode)
            except FileNotFoundError:
                mock_file = Mock()
                mock_file.read.return_value = "123\ngroup/test-project"
                mock_file.__iter__.return_value = iter("123\ngroup/test-project".splitlines())
                mock_file.write.return_value = None
                return mock_file

        mock_open.side_effect = open_side_effect

        yield {
            'open': mock_open,
            'exists': mock_exists,
            'isfile': mock_isfile,
            'isdir': mock_isdir,
        }






class TestNuGetUpdateFlows:
    """Integration tests for complete NuGet update workflows."""

    @pytest.fixture
    def mock_gitlab_provider(self):
        """Create a mock GitLab provider with realistic responses."""
        provider = Mock(spec=GitLabProvider)

        # Mock project data with complete structure
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'default_branch': 'main',
            'http_url_to_repo': 'https://gitlab.com/group/test-project.git',
            'web_url': 'https://gitlab.com/group/test-project'
        }

        # Mock repository tree
        provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'Project.csproj', 'path': 'src/Project.csproj'},
            {'type': 'blob', 'name': 'Another.csproj', 'path': 'tests/Another.csproj'},
            {'type': 'blob', 'name': 'README.md', 'path': 'README.md'}
        ]

        # Mock file content with package reference
        provider.get_file_content.return_value = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>'''

        # Mock merge request creation with complete response
        provider.create_merge_request.return_value = {
            'id': 456,
            'iid': 1,
            'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/1',
            'title': 'Update Microsoft.EntityFrameworkCore to version 7.0.0'
        }

        # Mock repository discovery with complete project structures
        provider.discover_repositories.return_value = [
            {
                'id': 123,
                'name': 'test-project-1',
                'path_with_namespace': 'group/test-project-1',
                'default_branch': 'main',
                'http_url_to_repo': 'https://gitlab.com/group/test-project-1.git',
                'web_url': 'https://gitlab.com/group/test-project-1',
                'description': 'Test project 1',
                'archived': False,
                'forked_from_project': None
            },
            {
                'id': 124,
                'name': 'test-project-2',
                'path_with_namespace': 'group/test-project-2',
                'default_branch': 'develop',
                'http_url_to_repo': 'https://gitlab.com/group/test-project-2.git',
                'web_url': 'https://gitlab.com/group/test-project-2',
                'description': 'Test project 2',
                'archived': False,
                'forked_from_project': None
            }
        ]

        # Mock existing merge request check
        provider.check_existing_merge_request.return_value = None

        return provider

    @pytest.fixture
    def mock_config_service(self):
        """Create a mock configuration service."""
        config = Mock(spec=ConfigurationService)
        config.get.side_effect = lambda key, default=None: {
            'gitlab_url': 'https://gitlab.com',
            'token': 'test-token',
            'verify_ssl': True,
            'packages_to_update': [
                {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.0'}
            ],
            'repositories': ['123', 'group/test-project']
        }.get(key, default)
        return config

    @pytest.fixture
    def temp_repo_file(self):
        """Create a temporary repository file."""
        repos = ['123', 'group/test-project', 'another/repo']

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('\n'.join(repos))
            temp_file = f.name

        yield temp_file
        os.unlink(temp_file)

    def test_update_nuget_from_repositories_argument(self, mock_gitlab_provider, mock_config_service,
                                                   mock_git_service, mock_nuspec_action, mock_file_operations):
        """Test NuGet update flow using --repositories argument."""
        args = Mock()
        args.repositories = '123,group/test-project'
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        handler.execute(args)

        # Verify GitLab provider was called correctly
        assert mock_gitlab_provider.get_project.call_count >= 1

    def test_update_nuget_from_repo_file(self, mock_gitlab_provider, mock_config_service, temp_repo_file,
                                       mock_git_service, mock_nuspec_action, mock_file_operations):
        """Test NuGet update flow using --repo-file argument."""
        args = Mock()
        args.repositories = None
        args.repo_file = temp_repo_file
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        handler.execute(args)

        # Verify repositories were loaded from file
        assert mock_gitlab_provider.get_project.call_count >= 1

    def test_update_nuget_repository_discovery(self, mock_gitlab_provider, mock_config_service,
                                              mock_git_service, mock_nuspec_action, mock_file_operations):
        """Test NuGet update flow using repository discovery."""
        args = Mock()
        args.repositories = None
        args.repo_file = None
        args.discover_group = 'test-group'
        args.owned_only = False
        args.member_only = False
        args.include_archived = False
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        mock_projects = mock_gitlab_provider.discover_repositories.return_value
        with patch.object(UserInteractionService, 'get_user_confirmation', return_value=mock_projects):
            handler.execute(args)

        # Verify repository discovery was called
        mock_gitlab_provider.discover_repositories.assert_called_once_with(
            group_id='test-group',
            owned=False,
            membership=False,
            archived=False
        )

    def test_dry_run_mode(self, mock_gitlab_provider, mock_config_service):
        """Test dry run mode functionality."""
        args = Mock()
        args.repositories = '123,group/test-project'
        args.repositories = '123,group/test-project'
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.allow_downgrade = False
        args.dry_run = True
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        with patch('sys.exit') as mock_exit:
            handler.execute(args)
            mock_exit.assert_called_once()

    def test_package_version_downgrade_prevention(self, mock_gitlab_provider, mock_config_service,
                                                 mock_git_service, mock_nuspec_action, mock_file_operations):
        """Test that package downgrades are prevented by default."""
        # Mock file content with newer version
        mock_gitlab_provider.get_file_content.return_value = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
  </ItemGroup>
</Project>'''

        args = Mock()
        args.repositories = '123'
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']  # Downgrade attempt
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        handler.execute(args)

        # Verify no merge request was created due to downgrade prevention
        mock_gitlab_provider.create_merge_request.assert_not_called()

    def test_package_version_downgrade_allowed(self, mock_gitlab_provider, mock_config_service,
                                             mock_git_service, mock_file_operations):
        """Test that package downgrades work when explicitly allowed."""
        # Mock file content with newer version
        mock_gitlab_provider.get_file_content.return_value = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
  </ItemGroup>
</Project>'''

        args = Mock()
        args.repositories = '123'
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']  # Downgrade attempt
        args.allow_downgrade = True
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        with patch('src.actions.nuspec_update_action.NuspecUpdateAction.execute') as mock_execute:
            mock_execute.return_value = {
                'id': 456,
                'iid': 1,
                'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/1',
                'title': 'Update Microsoft.EntityFrameworkCore to version 7.0.0'
            }
            handler.execute(args)
            mock_execute.assert_called()

    def test_existing_merge_request_detection(self, mock_gitlab_provider, mock_config_service,
                                            mock_git_service, mock_nuspec_action, mock_file_operations):
        """Test detection and handling of existing merge requests."""
        # Mock existing merge request
        mock_gitlab_provider.check_existing_merge_request.return_value = {
            'id': 456,
            'iid': 1,
            'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/1',
            'title': 'Update Microsoft.EntityFrameworkCore to version 7.0.0'
        }

        args = Mock()
        args.repositories = '123'
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        handler.execute(args)

        # Verify existing MR was detected
        mock_gitlab_provider.check_existing_merge_request.assert_called()

    def test_no_csproj_files_found(self, mock_gitlab_provider, mock_config_service,
                                  mock_git_service, mock_nuspec_action, mock_file_operations):
        """Test handling when no .csproj files are found in repository."""
        # Mock empty repository tree
        mock_gitlab_provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'README.md', 'path': 'README.md'},
            {'type': 'blob', 'name': 'package.json', 'path': 'package.json'}
        ]

        args = Mock()
        args.repositories = '123'
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        handler.execute(args)

        # Verify no merge request was created
        mock_gitlab_provider.create_merge_request.assert_not_called()

    def test_multiple_packages_update(self, mock_gitlab_provider, mock_config_service,
                                    mock_git_service, mock_file_operations):
        """Test updating multiple packages in a single run."""
        args = Mock()
        args.repositories = '123'
        args.repo_file = None
        args.discover_group = None
        args.packages = [
            'Microsoft.EntityFrameworkCore@7.0.0',
            'Newtonsoft.Json@13.0.3'
        ]
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        with patch('src.actions.nuspec_update_action.NuspecUpdateAction.execute') as mock_execute:
            mock_execute.return_value = {
                'id': 456,
                'iid': 1,
                'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/1',
                'title': 'Update multiple packages'
            }
            handler.execute(args)
            assert mock_execute.call_count == 2

    def test_report_generation(self, mock_gitlab_provider, mock_config_service,
                             mock_git_service, mock_nuspec_action, mock_file_operations):
        """Test that reports are generated correctly."""
        args = Mock()
        args.repositories = '123'
        args.repo_file = None
        args.discover_group = None
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = 'test_report'

        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)

        with patch('src.services.report_generator.ReportGenerator.generate') as mock_generate:
            handler.execute(args)
            mock_generate.assert_called_with(unittest.mock.ANY)


class TestCSProjUpdaterIntegration:
    """Integration tests for CSProj file processing."""

    def test_single_line_package_reference_update(self):
        """Test updating single-line PackageReference format."""
        updater = CSProjUpdater('Microsoft.EntityFrameworkCore', '7.0.0')

        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = updater.update_package_version(content, allow_downgrade=False)

        assert modified
        assert 'Version="7.0.0"' in updated_content
        assert 'Version="6.0.0"' not in updated_content

    def test_multi_line_package_reference_update(self):
        """Test updating multi-line PackageReference format."""
        updater = CSProjUpdater('Microsoft.EntityFrameworkCore', '7.0.0')

        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>6.0.0</Version>
    </PackageReference>
  </ItemGroup>
</Project>'''

        updated_content, modified = updater.update_package_version(content, allow_downgrade=False)

        assert modified
        assert '<Version>7.0.0</Version>' in updated_content
        assert '<Version>6.0.0</Version>' not in updated_content

    def test_find_csproj_files_from_tree(self):
        """Test finding .csproj files from repository tree."""
        updater = CSProjUpdater('Test.Package', '1.0.0')

        tree = [
            {'type': 'blob', 'name': 'Project.csproj', 'path': 'src/Project.csproj'},
            {'type': 'blob', 'name': 'Test.csproj', 'path': 'tests/Test.csproj'},
            {'type': 'blob', 'name': 'README.md', 'path': 'README.md'},
            {'type': 'tree', 'name': 'docs', 'path': 'docs'}
        ]

        csproj_files = updater.find_csproj_files_from_tree(tree)

        assert len(csproj_files) == 2
        assert 'src/Project.csproj' in csproj_files
        assert 'tests/Test.csproj' in csproj_files

    def test_downgrade_prevention(self):
        """Test that downgrades are prevented when not allowed."""
        updater = CSProjUpdater('Microsoft.EntityFrameworkCore', '6.0.0')

        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="7.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = updater.update_package_version(content, allow_downgrade=False)

        assert not modified
        assert updated_content == content

    def test_downgrade_allowed(self):
        """Test that downgrades work when explicitly allowed."""
        updater = CSProjUpdater('Microsoft.EntityFrameworkCore', '6.0.0')

        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="7.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = updater.update_package_version(content, allow_downgrade=True)

        assert modified
        assert 'Version="6.0.0"' in updated_content
        assert 'Version="7.0.0"' not in updated_content


class TestUserInteractionIntegration:
    """Integration tests for user interaction workflows."""

    def test_repository_confirmation_workflow(self):
        """Test the complete repository confirmation workflow."""
        projects = [
            {
                'id': 123,
                'name': 'test-project',
                'path_with_namespace': 'group/test-project',
                'web_url': 'https://gitlab.com/group/test-project',
                'description': 'Test project'
            }
        ]

        # Mock user selecting "all" repositories
        with patch('builtins.input', return_value='1'):
            result = UserInteractionService.get_user_confirmation(projects)
            assert result == projects

    def test_repository_display_formatting(self):
        """Test that repository display is properly formatted."""
        projects = [
            {
                'id': 123,
                'name': 'test-project',
                'path_with_namespace': 'group/test-project',
                'web_url': 'https://gitlab.com/group/test-project',
                'description': 'A test project for integration testing'
            }
        ]

        with patch('builtins.print') as mock_print:
            UserInteractionService.display_discovered_repositories(projects)

            # Verify that print was called with repository information
            assert mock_print.call_count > 0
            # Check that project name was included in one of the print calls
            print_args = [str(call) for call in mock_print.call_args_list]
            assert any('test-project' in arg for arg in print_args)


class TestDryRunIntegration:
    """Integration tests for dry run functionality."""

    def test_dry_run_package_analysis(self):
        """Test dry run analysis of packages in repositories."""
        mock_gitlab_provider = Mock()
        mock_gitlab_provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'Project.csproj', 'path': 'src/Project.csproj'}
        ]
        mock_gitlab_provider.get_file_content.return_value = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        dry_run_service = DryRunService(mock_gitlab_provider)

        repositories = [
            {
                'id': 123,
                'name': 'test-project',
                'path_with_namespace': 'group/test-project',
                'http_url_to_repo': 'https://gitlab.com/group/test-project.git',
                'default_branch': 'main',
            }
        ]

        packages_to_update = [
            {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.0'}
        ]

        with patch('sys.exit') as mock_exit, \
             patch('builtins.print'):
            dry_run_service.simulate_package_updates(
                repositories, packages_to_update, False, None
            )
            mock_exit.assert_called_once()
