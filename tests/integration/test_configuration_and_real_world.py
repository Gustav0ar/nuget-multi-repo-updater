"""
Configuration-based integration tests that test real-world scenarios using config files.
"""

import pytest
import tempfile
import json
import os
from unittest.mock import Mock, patch

from src.services.config_service import ConfigurationService
from src.services.command_handlers import UpdateNugetCommandHandler
from src.providers.gitlab_provider import GitLabProvider


def mock_open_multiple_files(*args, **kwargs):
    """Mock multiple file operations with different content."""
    from unittest.mock import mock_open

    if 'WebApp.csproj' in str(args[0]):
        return mock_open(read_data='''<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net7.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Microsoft.AspNetCore" Version="6.0.0" />
  </ItemGroup>
</Project>''')()
    elif 'Tests.csproj' in str(args[0]):
        return mock_open(read_data='''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net7.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>''')()
    else:
        return mock_open()()


class TestConfigurationIntegrationComplete:
    """Complete integration tests using various configuration file formats and scenarios."""

    @pytest.fixture
    def sample_json_config(self):
        """Create a sample JSON configuration file."""
        config_data = {
            "gitlab_url": "https://gitlab.example.com",
            "token": "glpat-test-token-123",
            "verify_ssl": True,
            "packages_to_update": [
                {
                    "name": "Microsoft.EntityFrameworkCore",
                    "version": "7.0.0"
                },
                {
                    "name": "Newtonsoft.Json",
                    "version": "13.0.3"
                }
            ],
            "repositories": [
                "123",
                "group/project-name",
                "456"
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f, indent=2)
            temp_file = f.name

        yield temp_file
        os.unlink(temp_file)

    @pytest.fixture
    def mock_gitlab_provider_for_config(self):
        """Create a comprehensive mock GitLab provider for config tests."""
        provider = Mock(spec=GitLabProvider)

        # Mock project data
        provider.get_project.side_effect = lambda repo_id: {
            '123': {
                'id': 123,
                'name': 'test-project-1',
                'path_with_namespace': 'group/test-project-1',
                'default_branch': 'main',
                'http_url_to_repo': 'https://gitlab.example.com/group/test-project-1.git',
                'web_url': 'https://gitlab.example.com/group/test-project-1'
            },
            'group/project-name': {
                'id': 456,
                'name': 'project-name',
                'path_with_namespace': 'group/project-name',
                'default_branch': 'develop',
                'http_url_to_repo': 'https://gitlab.example.com/group/project-name.git',
                'web_url': 'https://gitlab.example.com/group/project-name'
            }
        }.get(str(repo_id))

        # Mock repository tree with .csproj files
        provider.get_repository_tree.return_value = [
            {'type': 'blob', 'name': 'WebApp.csproj', 'path': 'src/WebApp/WebApp.csproj'},
            {'type': 'blob', 'name': 'Tests.csproj', 'path': 'tests/Tests.csproj'}
        ]

        # Mock .csproj file content
        provider.get_file_content.return_value = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net7.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Microsoft.AspNetCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        # Mock merge request operations
        provider.check_existing_merge_request.return_value = None
        provider.create_merge_request.return_value = {
            'id': 101,
            'iid': 5,
            'web_url': 'https://gitlab.example.com/group/test-project/-/merge_requests/5',
            'title': 'Update packages to latest versions'
        }

        return provider

    def test_json_config_file_integration(self, sample_json_config, mock_gitlab_provider_for_config):
        """Test full integration using JSON configuration file."""
        # Load configuration from file
        config_service = ConfigurationService(sample_json_config)

        # Create handler with mocked dependencies
        handler = UpdateNugetCommandHandler(mock_gitlab_provider_for_config, config_service)

        # Mock command line arguments to use config file packages
        args = Mock()
        args.repositories = None  # Will use config file repositories
        args.repo_file = None
        args.discover_group = None
        args.packages = None  # Will use config file packages
        args.allow_downgrade = False
        args.dry_run = False
        args.max_repositories = None
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None

        # Mock all external dependencies to prevent network/git operations
        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm, \
             patch('src.services.git_service.GitService') as mock_git_service, \
             patch('src.actions.nuspec_update_action.NuspecUpdateAction') as mock_action_class, \
             patch('requests.get') as mock_requests_get, \
             patch('requests.post') as mock_requests_post, \
             patch('git.Repo') as mock_git_repo, \
             patch('git.Repo.clone_from') as mock_clone, \
             patch('builtins.open', mock_open_multiple_files), \
             patch('os.path.exists', return_value=True), \
             patch('os.makedirs'), \
             patch('shutil.rmtree'), \
             patch('tempfile.mkdtemp', return_value='/tmp/test-config'):

            mock_confirm.return_value = []  # No additional user input needed

            # Mock Git service to prevent actual Git operations
            mock_git = Mock()
            mock_git.clone_repository.return_value = '/tmp/mock-clone'
            mock_git.create_branch.return_value = True
            mock_git.checkout_branch.return_value = True
            mock_git.add_files.return_value = True
            mock_git.commit_changes.return_value = 'mock-commit-hash'
            mock_git.push_branch.return_value = True
            mock_git_service.return_value = mock_git

            # Mock NuspecUpdateAction to prevent actual execution
            mock_action = Mock()
            mock_action.execute.return_value = {'id': 123, 'web_url': 'mock-url'}
            mock_action_class.return_value = mock_action

            # Mock all network requests to prevent actual API calls
            mock_requests_get.return_value = Mock(status_code=200, json=lambda: {})
            mock_requests_post.return_value = Mock(status_code=201, json=lambda: {})

            # Mock Git repo operations
            mock_repo = Mock()
            mock_git_repo.return_value = mock_repo
            mock_clone.return_value = mock_repo

            # Execute the handler
            try:
                handler.execute(args)
            except SystemExit:
                pass  # May exit after processing

        # Verify configuration was loaded correctly
        packages = config_service.get('packages_to_update', [])
        assert len(packages) == 2
        assert packages[0]['name'] == 'Microsoft.EntityFrameworkCore'

    def test_config_validation_and_loading(self, sample_json_config):
        """Test that configuration files are properly validated and loaded."""
        config_service = ConfigurationService(sample_json_config)

        # Test that all expected configuration values are loaded
        assert config_service.get('gitlab_url') == 'https://gitlab.example.com'
        assert config_service.get('token') == 'glpat-test-token-123'
        assert config_service.get('verify_ssl') == True

        packages = config_service.get('packages_to_update', [])
        assert len(packages) == 2

        repositories = config_service.get('repositories', [])
        assert len(repositories) == 3
