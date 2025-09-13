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
from src.services.rollback_service import RollbackService
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
        self.code_migration_service = CodeMigrationService()
        self.rollback_service = RollbackService()
        
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
        # Create mock git service
        mock_git_service = Mock()
        mock_git_service.get_current_commit_sha.return_value = 'abc123'
        mock_git_service.create_and_checkout_branch.return_value = None
        mock_git_service.add_and_commit.return_value = None
        mock_git_service.push_branch.return_value = None
        
        # Create mock SCM provider
        mock_scm_provider = Mock()
        mock_scm_provider.create_merge_request.return_value = {'id': 123}
        
        # Set up local strategy
        strategy = LocalCloneStrategy(mock_git_service, self.rollback_service)
        strategy.set_transaction(strategy._create_transaction())
        
        # Mock C# migration tool execution
        migration_result = MigrationResult(
            success=True,
            files_modified=['TestClass.cs'],
            rules_applied=['Remove DeprecatedMethod calls'],
            message='Migration completed successfully'
        )
        
        with patch.object(self.code_migration_service, 'execute_migrations', return_value=migration_result), \
             patch.object(self.code_migration_service, 'is_tool_available', return_value=True):
            
            # Create multi-package update action
            action = MultiPackageUpdateAction(
                migration_config_service=self.migration_config_service,
                code_migration_service=self.code_migration_service,
                rollback_service=self.rollback_service
            )
            
            # Define package updates
            package_updates = [
                {
                    'name': 'OldPackage',
                    'old_version': '1.0.0',
                    'new_version': '2.0.0'
                },
                {
                    'name': 'TestPackage', 
                    'old_version': '2.0.0',
                    'new_version': '3.0.0'
                }
            ]
            
            # Execute the action
            result = action.execute(
                repository_path=self.repo_dir,
                strategy=strategy,
                scm_provider=mock_scm_provider,
                package_updates=package_updates,
                dry_run=False
            )
            
            # Verify successful execution
            assert result['success'] is True
            assert 'package_update_commit' in result
            assert 'migration_commit' in result
            assert result['files_migrated'] == ['TestClass.cs']
            
            # Verify git operations were called
            mock_git_service.create_and_checkout_branch.assert_called()
            assert mock_git_service.add_and_commit.call_count == 2  # Package update + migration
            
    def test_workflow_with_migration_tool_unavailable(self):
        """Test workflow when C# migration tool is not available."""
        mock_git_service = Mock()
        mock_scm_provider = Mock()
        
        strategy = LocalCloneStrategy(mock_git_service, self.rollback_service)
        strategy.set_transaction(strategy._create_transaction())
        
        # Mock tool as unavailable
        with patch.object(self.code_migration_service, 'is_tool_available', return_value=False):
            
            action = MultiPackageUpdateAction(
                migration_config_service=self.migration_config_service,
                code_migration_service=self.code_migration_service,
                rollback_service=self.rollback_service
            )
            
            package_updates = [
                {
                    'name': 'OldPackage',
                    'old_version': '1.0.0', 
                    'new_version': '2.0.0'
                }
            ]
            
            result = action.execute(
                repository_path=self.repo_dir,
                strategy=strategy,
                scm_provider=mock_scm_provider,
                package_updates=package_updates,
                dry_run=False
            )
            
            # Should succeed but skip migration
            assert result['success'] is True
            assert 'package_update_commit' in result
            assert 'migration_commit' not in result
            assert 'Migration tool not available' in result.get('warnings', [])
            
    def test_workflow_rollback_on_migration_failure(self):
        """Test workflow rollback when migration fails."""
        mock_git_service = Mock()
        mock_git_service.get_current_commit_sha.return_value = 'abc123'
        mock_git_service.create_and_checkout_branch.return_value = None
        mock_git_service.add_and_commit.return_value = 'def456'  # Package update commit
        
        mock_scm_provider = Mock()
        
        strategy = LocalCloneStrategy(mock_git_service, self.rollback_service)
        
        # Mock successful tool availability but failed migration
        failed_migration_result = MigrationResult(
            success=False,
            files_modified=[],
            rules_applied=[],
            message='Migration failed: Syntax error'
        )
        
        with patch.object(self.code_migration_service, 'is_tool_available', return_value=True), \
             patch.object(self.code_migration_service, 'execute_migrations', return_value=failed_migration_result), \
             patch.object(self.rollback_service, 'execute_rollback') as mock_rollback:
            
            # Mock successful rollback
            mock_rollback.return_value = Mock(success=True, message='Rollback completed')
            
            action = MultiPackageUpdateAction(
                migration_config_service=self.migration_config_service,
                code_migration_service=self.code_migration_service,
                rollback_service=self.rollback_service
            )
            
            package_updates = [
                {
                    'name': 'OldPackage',
                    'old_version': '1.0.0',
                    'new_version': '2.0.0'
                }
            ]
            
            result = action.execute(
                repository_path=self.repo_dir,
                strategy=strategy,
                scm_provider=mock_scm_provider,
                package_updates=package_updates,
                dry_run=False
            )
            
            # Should fail and trigger rollback
            assert result['success'] is False
            assert 'Migration failed' in result['error']
            
            # Verify rollback was called
            mock_rollback.assert_called_once()
            
    def test_workflow_with_api_strategy(self):
        """Test workflow using API strategy with temporary file handling."""
        # Mock SCM provider for file operations
        mock_scm_provider = Mock()
        mock_scm_provider.get_file_content.return_value = "sample file content"
        mock_scm_provider.update_file.return_value = None
        mock_scm_provider.create_merge_request.return_value = {'id': 123}
        
        strategy = ApiStrategy(mock_scm_provider, self.rollback_service)
        strategy.set_transaction(strategy._create_transaction())
        
        # Mock successful migration
        migration_result = MigrationResult(
            success=True,
            files_modified=['TestClass.cs'],
            rules_applied=['Remove DeprecatedMethod calls'],
            message='Migration completed'
        )
        
        with patch.object(self.code_migration_service, 'execute_migrations', return_value=migration_result), \
             patch.object(self.code_migration_service, 'is_tool_available', return_value=True):
            
            action = MultiPackageUpdateAction(
                migration_config_service=self.migration_config_service,
                code_migration_service=self.code_migration_service,
                rollback_service=self.rollback_service
            )
            
            package_updates = [
                {
                    'name': 'OldPackage',
                    'old_version': '1.0.0',
                    'new_version': '2.0.0'
                }
            ]
            
            result = action.execute(
                repository_path='remote/repo/path',
                strategy=strategy,
                scm_provider=mock_scm_provider,
                package_updates=package_updates,
                dry_run=False
            )
            
            # Verify successful execution
            assert result['success'] is True
            assert result['files_migrated'] == ['TestClass.cs']
            
            # Verify SCM provider methods were called
            mock_scm_provider.create_merge_request.assert_called()
            
    def test_dry_run_workflow(self):
        """Test workflow in dry-run mode."""
        mock_git_service = Mock()
        mock_scm_provider = Mock()
        
        strategy = LocalCloneStrategy(mock_git_service, self.rollback_service)
        
        with patch.object(self.code_migration_service, 'is_tool_available', return_value=True):
            
            action = MultiPackageUpdateAction(
                migration_config_service=self.migration_config_service,
                code_migration_service=self.code_migration_service,
                rollback_service=self.rollback_service
            )
            
            package_updates = [
                {
                    'name': 'OldPackage',
                    'old_version': '1.0.0',
                    'new_version': '2.0.0'
                }
            ]
            
            result = action.execute(
                repository_path=self.repo_dir,
                strategy=strategy,
                scm_provider=mock_scm_provider,
                package_updates=package_updates,
                dry_run=True
            )
            
            # Should succeed without making actual changes
            assert result['success'] is True
            assert result['dry_run'] is True
            
            # Should not call git operations
            mock_git_service.create_and_checkout_branch.assert_not_called()
            mock_git_service.add_and_commit.assert_not_called()
            
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
