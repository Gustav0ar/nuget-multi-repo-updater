"""
Integration tests for the updated NuGet multi-repo updater workflows with migration support.
"""
import pytest
import tempfile
import os
import shutil
from unittest.mock import Mock, patch, MagicMock

from src.services.command_handlers import UpdateNugetCommandHandler
from src.actions.multi_package_update_action import MultiPackageUpdateAction
from src.services.migration_configuration_service import MigrationConfigurationService
from src.services.code_migration_service import CodeMigrationService, MigrationResult
from src.providers.gitlab_provider import GitLabProvider
from src.services.config_service import ConfigurationService
from src.services.git_service import GitService


class TestUpdatedWorkflows:
    """Integration tests for the updated workflow architecture."""
    
    @pytest.fixture
    def mock_config_service(self):
        """Create a mock configuration service."""
        config = Mock(spec=ConfigurationService)
        config.get.side_effect = lambda key, default=None: {
            'gitlab_url': 'https://gitlab.com',
            'token': 'test-token',
            'verify_ssl': True,
            'repositories': [],
            'enable_code_migrations': False,
            'migration_config_file': 'package-migrations.yml'
        }.get(key, default)
        return config
    
    @pytest.fixture
    def mock_gitlab_provider(self):
        """Create a mock GitLab provider."""
        provider = Mock(spec=GitLabProvider)
        provider.get_project.return_value = {
            'id': 123,
            'name': 'test-project',
            'path_with_namespace': 'group/test-project',
            'default_branch': 'main',
            'http_url_to_repo': 'https://gitlab.com/group/test-project.git',
            'ssh_url_to_repo': 'git@gitlab.com:group/test-project.git',
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
        provider.create_merge_request.return_value = {'id': 456, 'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/456'}
        return provider
    
    def test_basic_package_update_workflow(self, mock_gitlab_provider, mock_config_service):
        """Test basic package update workflow without migrations."""
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
        # Add the new branch selection attributes
        args.use_most_recent_branch = False
        args.branch_filter = None
        
        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)
        
        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm, \
             patch('src.actions.multi_package_update_action.MultiPackageUpdateAction.execute') as mock_execute:
            
            mock_confirm.return_value = []
            mock_execute.return_value = {
                'success': True,
                'merge_request': {'id': 456, 'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/456'}
            }
            
            # Should execute without errors
            handler.execute(args)
            
            # Verify the action was created and executed
            mock_execute.assert_called_once()
    
    def test_dry_run_workflow(self, mock_gitlab_provider, mock_config_service):
        """Test dry run workflow."""
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
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False
        # Add the new branch selection attributes
        args.use_most_recent_branch = False
        args.branch_filter = None
        
        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)
        
        with patch('src.services.dry_run_service.DryRunService.simulate_package_updates') as mock_dry_run:
            handler.execute(args)
            
            # Verify dry run was executed
            mock_dry_run.assert_called_once()
    
    def test_multi_package_update_action_creation(self):
        """Test creation of MultiPackageUpdateAction with correct parameters."""
        mock_git_service = Mock(spec=GitService)
        mock_scm_provider = Mock(spec=GitLabProvider)
        
        packages = [
            {'name': 'Microsoft.EntityFrameworkCore', 'version': '7.0.0'},
            {'name': 'Newtonsoft.Json', 'version': '13.0.3'}
        ]
        
        action = MultiPackageUpdateAction(
            git_service=mock_git_service,
            scm_provider=mock_scm_provider,
            packages=packages,
            allow_downgrade=False,
            use_local_clone=False,
            migration_config_service=None,
            enable_migrations=False,
            strict_migration_mode=False
        )
        
        # Verify action was created with correct parameters
        assert action.packages == packages
        assert action.git_service == mock_git_service
        assert action.scm_provider == mock_scm_provider
        assert action.allow_downgrade is False
        assert action.use_local_clone is False
        assert action.enable_migrations is False
    
    def test_migration_workflow_with_config_service(self):
        """Test migration workflow setup with MigrationConfigurationService."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("""
migrations:
  - from_package: "OldPackage"
    to_package: "NewPackage"
    rules:
      - type: "method_call"
        old_pattern: "OldMethod()"
        new_pattern: "NewMethod()"
""")
            config_file = f.name
        
        try:
            # Test migration config service creation
            migration_config_service = MigrationConfigurationService(config_file)
            assert migration_config_service is not None
            
            # Test code migration service creation
            code_migration_service = CodeMigrationService('/tmp/mock_tool')
            assert code_migration_service is not None
            
        finally:
            os.unlink(config_file)
    
    def test_rollback_functionality_basic(self):
        """Test basic rollback functionality exists."""
        from src.services.rollback_service import RepositoryUpdateTransaction
        
        mock_strategy = Mock()
        transaction = RepositoryUpdateTransaction('test-repo', mock_strategy)
        
        # Test that transaction can be created
        assert transaction.repo_id == 'test-repo'
        assert transaction.strategy == mock_strategy
    
    def test_command_handler_with_migration_config(self, mock_gitlab_provider, mock_config_service):
        """Test command handler with migration configuration."""
        # Update mock config to enable migrations
        mock_config_service.get.side_effect = lambda key, default=None: {
            'gitlab_url': 'https://gitlab.com',
            'token': 'test-token',
            'verify_ssl': True,
            'repositories': [],
            'enable_code_migrations': True,
            'migration_config_file': 'package-migrations.yml'
        }.get(key, default)
        
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
        # Set enable_migrations to None so config service setting is used
        args.enable_migrations = None
        # Add the new branch selection attributes
        args.use_most_recent_branch = None
        args.branch_filter = None
        
        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)
        
        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm, \
             patch('src.actions.multi_package_update_action.MultiPackageUpdateAction.execute') as mock_execute, \
             patch('os.path.exists', return_value=True):  # Mock that migration config file exists
            
            mock_confirm.return_value = []
            mock_execute.return_value = {
                'success': True,
                'merge_request': {'id': 456, 'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/456'}
            }
            
            # Should execute without errors
            handler.execute(args)
            
            # Verify that config service was queried for enable_code_migrations
            # This is the main thing we want to test - that migration config is considered
            expected_calls = [call for call in mock_config_service.get.call_args_list 
                            if 'enable_code_migrations' in str(call)]
            assert len(expected_calls) > 0, "Config service should have been queried for enable_code_migrations"
    
    def test_package_parsing(self, mock_gitlab_provider, mock_config_service):
        """Test package parsing functionality."""
        args = Mock()
        args.repositories = '123'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0', 'Newtonsoft.Json@13.0.3']
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
        # Add the new branch selection attributes
        args.use_most_recent_branch = False
        args.branch_filter = None
        
        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)
        
        # Test package parsing
        packages = handler._parse_packages_to_update(args)
        
        assert len(packages) == 2
        assert packages[0]['name'] == 'Microsoft.EntityFrameworkCore'
        assert packages[0]['version'] == '7.0.0'
        assert packages[1]['name'] == 'Newtonsoft.Json'
        assert packages[1]['version'] == '13.0.3'
    
    def test_repository_limit_functionality(self, mock_gitlab_provider, mock_config_service):
        """Test repository limit functionality."""
        args = Mock()
        args.repositories = '123,456,789'
        args.packages = ['Microsoft.EntityFrameworkCore@7.0.0']
        args.dry_run = False
        args.repo_file = None
        args.discover_group = None
        args.allow_downgrade = False
        args.max_repositories = 2  # Limit to 2 repositories
        args.ignore_patterns = None
        args.exclude_forks = False
        args.report_file = None
        args.migration_config = None
        args.strict_migration_mode = False
        args.enable_migrations = False
        # Add the new branch selection attributes
        args.use_most_recent_branch = False
        args.branch_filter = None
        
        # Mock multiple projects
        mock_gitlab_provider.get_project.side_effect = [
            {'id': 123, 'name': 'project1', 'path_with_namespace': 'group/project1', 'default_branch': 'main', 'ssh_url_to_repo': 'git@gitlab.com:group/project1.git'},
            {'id': 456, 'name': 'project2', 'path_with_namespace': 'group/project2', 'default_branch': 'main', 'ssh_url_to_repo': 'git@gitlab.com:group/project2.git'},
            {'id': 789, 'name': 'project3', 'path_with_namespace': 'group/project3', 'default_branch': 'main', 'ssh_url_to_repo': 'git@gitlab.com:group/project3.git'}
        ]
        
        handler = UpdateNugetCommandHandler(mock_gitlab_provider, mock_config_service)
        
        with patch('src.services.user_interaction_service.UserInteractionService.get_user_confirmation') as mock_confirm:
            mock_confirm.return_value = []
            
            with patch('src.actions.multi_package_update_action.MultiPackageUpdateAction.execute') as mock_execute:
                mock_execute.return_value = {
                    'success': True,
                    'merge_request': {'id': 456, 'web_url': 'https://gitlab.com/group/test-project/-/merge_requests/456'}
                }
                
                handler.execute(args)
                
                # Should only process 2 repositories due to limit
                assert mock_execute.call_count == 2
