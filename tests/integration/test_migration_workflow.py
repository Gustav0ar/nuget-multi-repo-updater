"""
Integration tests for the complete C# migration workflow.
"""
import pytest
import tempfile
import os
import shutil
import json
import yaml
from unittest.mock import Mock, patch, MagicMock

from src.actions.multi_package_update_action import MultiPackageUpdateAction
from src.services.migration_configuration_service import MigrationConfigurationService
from src.services.code_migration_service import CodeMigrationService, MigrationResult
from src.services.rollback_service import RepositoryUpdateTransaction, RollbackResult
from src.strategies.local_clone_strategy import LocalCloneStrategy
from src.strategies.api_strategy import ApiStrategy


class TestMigrationWorkflowIntegration:
    """Integration tests for the complete migration workflow."""
    
    def setup_method(self):
        """Set up test fixtures for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = os.path.join(self.temp_dir, 'test-repo')
        os.makedirs(self.repo_dir)
        
        # Create a sample C# project structure
        self.create_sample_csharp_project()
        
        # Create migration configuration
        self.config_file = self.create_migration_config()
        
        # Initialize services
        self.migration_config_service = MigrationConfigurationService(self.config_file)
        self.code_migration_service = CodeMigrationService('/tmp/mock_csharp_tool')
        
        # Create mock strategy for rollback transaction
        mock_strategy = Mock()
        self.rollback_transaction = RepositoryUpdateTransaction('test-repo', mock_strategy)
        
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            
    def create_sample_csharp_project(self):
        """Create a sample C# project for testing."""
        # Create project file
        csproj_content = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net7.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="OldPackage" Version="1.0.0" />
    <PackageReference Include="TestPackage" Version="2.0.0" />
  </ItemGroup>
</Project>'''
        
        with open(os.path.join(self.repo_dir, 'TestProject.csproj'), 'w') as f:
            f.write(csproj_content)
            
        # Create sample C# code file
        cs_content = '''using System;
using OldPackage;
using TestPackage;

namespace TestProject
{
    public class TestClass
    {
        public void TestMethod()
        {
            // This method call should be removed by migration
            OldPackage.DeprecatedMethod();
            
            // This should be replaced
            var result = TestPackage.OldMethod("test");
            
            // This should remain unchanged
            Console.WriteLine("Hello World");
        }
        
        public void ChainedMethod()
        {
            // Test method chaining scenario
            var builder = new StringBuilder()
                .Append("Hello")
                .OldMethod()  // This should be removed smartly
                .Append("World");
        }
    }
}'''
        
        with open(os.path.join(self.repo_dir, 'TestClass.cs'), 'w') as f:
            f.write(cs_content)
            
    def create_migration_config(self):
        """Create a migration configuration file."""
        config_content = {
            'migrations': [
                {
                    'id': 'oldpackage-deprecation',
                    'package_name': 'OldPackage',
                    'description': 'Remove deprecated OldPackage method calls',
                    'version_conditions': [
                        {'type': 'greater_than', 'version': '1.0.0'}
                    ],
                    'rules': [
                        {
                            'name': 'Remove DeprecatedMethod calls',
                            'target_nodes': [
                                {
                                    'type': 'InvocationExpression',
                                    'method_name': 'DeprecatedMethod',
                                    'containing_namespace': 'OldPackage'
                                }
                            ],
                            'action': {
                                'type': 'remove_invocation',
                                'strategy': 'smart_chain_aware'
                            }
                        }
                    ]
                },
                {
                    'id': 'testpackage-method-rename',
                    'package_name': 'TestPackage',
                    'description': 'Rename OldMethod to NewMethod',
                    'version_conditions': [
                        {'type': 'greater_than_or_equal', 'version': '3.0.0'}
                    ],
                    'rules': [
                        {
                            'name': 'Rename OldMethod to NewMethod',
                            'target_nodes': [
                                {
                                    'type': 'InvocationExpression',
                                    'method_name': 'OldMethod',
                                    'containing_namespace': 'TestPackage'
                                }
                            ],
                            'action': {
                                'type': 'replace_method_name',
                                'new_name': 'NewMethod'
                            }
                        }
                    ]
                }
            ]
        }
        
        config_file = os.path.join(self.temp_dir, 'migration-config.yml')
        with open(config_file, 'w') as f:
            yaml.dump(config_content, f)
            
        return config_file
        
    def test_complete_workflow_with_local_strategy(self):
        """Test complete migration workflow using local clone strategy."""
        # Create mock git service with proper local_path
        mock_git_service = Mock()
        mock_git_service.local_path = self.repo_dir  # Use real path
        mock_git_service.get_current_commit_sha.return_value = 'abc123'
        mock_git_service.create_and_checkout_branch.return_value = None
        mock_git_service.add_and_commit.return_value = None
        mock_git_service.push_branch.return_value = None
        
        # Create mock SCM provider
        mock_scm_provider = Mock()
        mock_scm_provider.create_merge_request.return_value = {'id': 123, 'web_url': 'https://example.com/mr/1'}
        mock_scm_provider.check_existing_merge_request.return_value = None  # No existing MR
        
        # Mock C# migration tool execution
        migration_result = MigrationResult(
            success=True,
            modified_files=['TestClass.cs'],
            applied_rules=['Remove DeprecatedMethod calls'],
            errors=[],
            summary='Migration completed successfully'
        )
        
        with patch.object(self.code_migration_service, 'execute_migrations', return_value=migration_result), \
             patch.object(self.code_migration_service, 'validate_tool_availability', return_value=True):
            
            # Create multi-package update action
            packages = [
                {'name': 'OldPackage', 'version': '2.0.0'},
                {'name': 'AnotherPackage', 'version': '3.0.0'}
            ]
            
            action = MultiPackageUpdateAction(
                git_service=mock_git_service,
                scm_provider=mock_scm_provider,
                packages=packages,
                allow_downgrade=False,
                use_local_clone=True,
                migration_config_service=self.migration_config_service,
                enable_migrations=True,
                strict_migration_mode=False
            )
            
            # Mock strategy methods for successful execution
            with patch.object(action.strategy, 'prepare_repository', return_value=True), \
                 patch.object(action.strategy, 'create_branch', return_value=True), \
                 patch.object(action.strategy, 'update_file', return_value=True), \
                 patch.object(action.strategy, 'create_merge_request', return_value={'id': 123, 'web_url': 'https://example.com/mr/1'}):
                
                # Execute the action
                result = action.execute(
                    repo_url='https://gitlab.com/test/repo.git',
                    repo_id='test-repo',
                    default_branch='main'
                )
                
                # Verify successful execution
                assert result is not None
                assert 'web_url' in result
            
    def test_workflow_with_migration_tool_unavailable(self):
        """Test workflow when C# migration tool is not available."""
        mock_git_service = Mock()
        mock_git_service.local_path = self.repo_dir
        mock_scm_provider = Mock()
        mock_scm_provider.check_existing_merge_request.return_value = None
        
        # Mock tool as unavailable
        with patch.object(self.code_migration_service, 'validate_tool_availability', return_value=False):
            
            packages = [
                {'name': 'OldPackage', 'version': '2.0.0'}
            ]
            
            action = MultiPackageUpdateAction(
                git_service=mock_git_service,
                scm_provider=mock_scm_provider,
                packages=packages,
                allow_downgrade=False,
                use_local_clone=True,
                migration_config_service=self.migration_config_service,
                enable_migrations=True,
                strict_migration_mode=False
            )
            
            # Mock strategy methods for successful execution
            with patch.object(action.strategy, 'prepare_repository', return_value=True), \
                 patch.object(action.strategy, 'create_branch', return_value=True), \
                 patch.object(action.strategy, 'update_file', return_value=True), \
                 patch.object(action.strategy, 'create_merge_request', return_value={'id': 123, 'web_url': 'https://example.com/mr/1'}):
                
                result = action.execute(
                    repo_url='https://gitlab.com/test/repo.git',
                    repo_id='test-repo',
                    default_branch='main'
                )
                
                # Should succeed but skip migration due to tool unavailability
                assert result is not None
                assert 'web_url' in result
            
    def test_workflow_rollback_on_migration_failure(self):
        """Test workflow rollback when migration fails."""
        mock_git_service = Mock()
        mock_git_service.local_path = self.repo_dir
        mock_git_service.get_current_commit_sha.return_value = 'abc123'
        mock_git_service.create_and_checkout_branch.return_value = None
        mock_git_service.add_and_commit.return_value = 'def456'  # Package update commit
        
        mock_scm_provider = Mock()
        mock_scm_provider.check_existing_merge_request.return_value = None
        
        # Mock successful tool availability but failed migration
        failed_migration_result = MigrationResult(
            success=False,
            modified_files=[],
            applied_rules=[],
            errors=['Migration failed: Syntax error'],
            summary='Migration failed: Syntax error'
        )
        
        with patch.object(self.code_migration_service, 'validate_tool_availability', return_value=True), \
             patch.object(self.code_migration_service, 'execute_migrations', return_value=failed_migration_result):
            
            packages = [
                {'name': 'OldPackage', 'version': '2.0.0'}
            ]
            
            action = MultiPackageUpdateAction(
                git_service=mock_git_service,
                scm_provider=mock_scm_provider,
                packages=packages,
                allow_downgrade=False,
                use_local_clone=True,
                migration_config_service=self.migration_config_service,
                enable_migrations=True,
                strict_migration_mode=True  # Enable strict mode to trigger rollback
            )
            
            # Mock strategy methods - prepare and package updates succeed, but migration will fail
            with patch.object(action.strategy, 'prepare_repository', return_value=True), \
                 patch.object(action.strategy, 'find_target_files', return_value=['test.csproj']), \
                 patch.object(action.strategy, 'create_branch', return_value=True), \
                 patch.object(action.strategy, 'update_file', return_value=True), \
                 patch.object(action, '_execute_package_updates', return_value={'success': True, 'updated_packages': [{'name': 'OldPackage', 'old_version': '1.0.0', 'new_version': '2.0.0'}]}), \
                 patch.object(action, '_has_applicable_migrations', return_value=True):
                
                # This should raise a TransactionException due to failed migration in strict mode
                with pytest.raises(Exception):  # Could be TransactionException or other exception
                    action.execute(
                        repo_url='https://gitlab.com/test/repo.git',
                        repo_id='test-repo',
                        default_branch='main'
                    )
            
    def test_workflow_with_api_strategy(self):
        """Test workflow using API strategy instead of local clone."""
        mock_scm_provider = Mock()
        mock_scm_provider.check_existing_merge_request.return_value = None
        mock_scm_provider.get_repository_tree.return_value = [
            {'name': 'test.csproj', 'type': 'blob', 'path': 'test.csproj'}
        ]
        mock_scm_provider.get_file_content.return_value = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="OldPackage" Version="1.0.0" />
  </ItemGroup>
</Project>'''
        mock_scm_provider.create_merge_request.return_value = {'id': 123, 'web_url': 'http://merge-request-url'}
        
        # Mock successful migration
        successful_migration_result = MigrationResult(
            success=True,
            modified_files=['Program.cs'],
            applied_rules=['rule1'],
            errors=[],
            summary='Migration completed successfully'
        )
        
        with patch.object(self.code_migration_service, 'validate_tool_availability', return_value=True), \
             patch.object(self.code_migration_service, 'execute_migrations', return_value=successful_migration_result):
            
            packages = [
                {'name': 'OldPackage', 'version': '2.0.0'}
            ]
            
            action = MultiPackageUpdateAction(
                git_service=None,  # No git service for API strategy
                scm_provider=mock_scm_provider,
                packages=packages,
                allow_downgrade=False,
                use_local_clone=False,  # Use API strategy
                migration_config_service=self.migration_config_service,
                enable_migrations=True
            )
            
            # Mock strategy methods for API strategy
            with patch.object(action.strategy, 'prepare_repository', return_value=True), \
                 patch.object(action.strategy, 'create_branch', return_value=True), \
                 patch.object(action.strategy, 'create_merge_request', return_value={'id': 123, 'web_url': 'http://merge-request-url'}):
                
                result = action.execute(
                    repo_url='https://gitlab.com/test/repo.git',
                    repo_id='test-repo',
                    default_branch='main'
                )
                
                assert result is not None
                assert 'web_url' in result
            
    def test_dry_run_workflow(self):
        """Test workflow in dry-run mode."""
        mock_git_service = Mock()
        mock_git_service.local_path = self.repo_dir
        mock_scm_provider = Mock()
        mock_scm_provider.check_existing_merge_request.return_value = None
        
        # Create a real test.csproj file in the repo directory
        test_csproj_path = os.path.join(self.repo_dir, 'test.csproj')
        with open(test_csproj_path, 'w') as f:
            f.write('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="OldPackage" Version="1.0.0" />
  </ItemGroup>
</Project>''')
        
        packages = [
            {'name': 'OldPackage', 'version': '2.0.0'}
        ]
        
        action = MultiPackageUpdateAction(
            git_service=mock_git_service,
            scm_provider=mock_scm_provider,
            packages=packages,
            allow_downgrade=False,
            use_local_clone=True,
            migration_config_service=self.migration_config_service,
            enable_migrations=True
        )
        
        # Mock strategy methods - for dry run, methods succeed but don't perform actual operations
        with patch.object(action.strategy, 'prepare_repository', return_value=True), \
             patch.object(action.strategy, 'create_branch', return_value=True), \
             patch.object(action.strategy, 'create_merge_request', return_value={'id': 123, 'web_url': 'http://merge-request-url'}):
            
            result = action.execute(
                repo_url='https://gitlab.com/test/repo.git',
                repo_id='test-repo',
                default_branch='main'
            )
            
            # Should succeed
            assert result is not None
            assert 'web_url' in result
            
    def test_migration_configuration_loading(self):
        """Test that migration configurations are loaded correctly."""
        # Verify configurations were loaded
        assert len(self.migration_config_service.migrations) == 2
        assert 'oldpackage-deprecation' in self.migration_config_service.migrations
        assert 'testpackage-method-rename' in self.migration_config_service.migrations
        
        # Test getting applicable migrations
        oldpackage_migrations = self.migration_config_service.get_applicable_migrations(
            'OldPackage', '1.0.0', '2.0.0'
        )
        assert len(oldpackage_migrations) == 1
        assert oldpackage_migrations[0].id == 'oldpackage-deprecation'
        
        # Test version condition that shouldn't match
        testpackage_migrations = self.migration_config_service.get_applicable_migrations(
            'TestPackage', '2.0.0', '2.5.0'  # Not >= 3.0.0
        )
        assert len(testpackage_migrations) == 0
