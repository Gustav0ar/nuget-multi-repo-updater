"""
Unit tests for migration configuration service.
"""
import pytest
import tempfile
import os
import yaml
import json
from src.services.migration_configuration_service import (
    MigrationConfigurationService, 
    MigrationConfiguration, 
    MigrationRule
)


class TestMigrationRule:
    """Test cases for MigrationRule class."""
    
    def test_migration_rule_creation(self):
        """Test creating a migration rule."""
        rule_data = {
            'name': 'Test Rule',
            'target_nodes': [{'type': 'InvocationExpression', 'method_name': 'TestMethod'}],
            'action': {'type': 'remove_invocation', 'strategy': 'smart_chain_aware'}
        }
        
        rule = MigrationRule(rule_data)
        
        assert rule.name == 'Test Rule'
        assert len(rule.target_nodes) == 1
        assert rule.action['type'] == 'remove_invocation'
        
    def test_migration_rule_to_dict(self):
        """Test converting migration rule to dictionary."""
        rule_data = {
            'name': 'Test Rule',
            'target_nodes': [{'type': 'InvocationExpression'}],
            'action': {'type': 'remove_invocation'}
        }
        
        rule = MigrationRule(rule_data)
        result = rule.to_dict()
        
        assert result == rule_data


class TestMigrationConfiguration:
    """Test cases for MigrationConfiguration class."""
    
    def test_migration_configuration_creation(self):
        """Test creating a migration configuration."""
        config_data = {
            'id': 'test-migration',
            'package_name': 'Test.Package',
            'description': 'Test migration',
            'version_conditions': [{'type': 'greater_than', 'version': '1.0.0'}],
            'rules': [
                {
                    'name': 'Test Rule',
                    'target_nodes': [{'type': 'InvocationExpression'}],
                    'action': {'type': 'remove_invocation'}
                }
            ]
        }
        
        config = MigrationConfiguration(config_data)
        
        assert config.id == 'test-migration'
        assert config.package_name == 'Test.Package'
        assert len(config.rules) == 1
        assert len(config.version_conditions) == 1
        
    def test_is_applicable_greater_than(self):
        """Test version condition: greater_than."""
        config_data = {
            'id': 'test',
            'package_name': 'Test.Package',
            'version_conditions': [{'type': 'greater_than', 'version': '2.0.0'}],
            'rules': []
        }
        
        config = MigrationConfiguration(config_data)
        
        # Should apply when upgrading from 1.0.0 to 3.0.0
        assert config.is_applicable('1.0.0', '3.0.0')
        
        # Should not apply when both versions are above threshold
        assert not config.is_applicable('2.1.0', '3.0.0')
        
        # Should not apply when new version is not above threshold
        assert not config.is_applicable('1.0.0', '2.0.0')
        
    def test_is_applicable_greater_than_or_equal(self):
        """Test version condition: greater_than_or_equal."""
        config_data = {
            'id': 'test',
            'package_name': 'Test.Package',
            'version_conditions': [{'type': 'greater_than_or_equal', 'version': '2.0.0'}],
            'rules': []
        }
        
        config = MigrationConfiguration(config_data)
        
        # Should apply when upgrading to exactly the threshold
        assert config.is_applicable('1.0.0', '2.0.0')
        
        # Should apply when upgrading above the threshold
        assert config.is_applicable('1.0.0', '3.0.0')
        
        # Should not apply when old version is already above threshold
        assert not config.is_applicable('2.1.0', '3.0.0')
        
    def test_is_applicable_exact(self):
        """Test version condition: exact."""
        config_data = {
            'id': 'test',
            'package_name': 'Test.Package',
            'version_conditions': [{'type': 'exact', 'version': '2.0.0'}],
            'rules': []
        }
        
        config = MigrationConfiguration(config_data)
        
        # Should apply when upgrading to exact version
        assert config.is_applicable('1.0.0', '2.0.0')
        
        # Should not apply for other versions
        assert not config.is_applicable('1.0.0', '3.0.0')
        
    def test_is_applicable_range(self):
        """Test version condition: range."""
        config_data = {
            'id': 'test',
            'package_name': 'Test.Package',
            'version_conditions': [{'type': 'range', 'version': '2.0.0', 'max_version': '3.0.0'}],
            'rules': []
        }
        
        config = MigrationConfiguration(config_data)
        
        # Should apply when upgrading to version in range
        assert config.is_applicable('1.0.0', '2.5.0')
        
        # Should not apply when version is outside range
        assert not config.is_applicable('1.0.0', '4.0.0')
        
    def test_is_applicable_invalid_version(self):
        """Test handling of invalid version formats."""
        config_data = {
            'id': 'test',
            'package_name': 'Test.Package',
            'version_conditions': [{'type': 'greater_than', 'version': '2.0.0'}],
            'rules': []
        }
        
        config = MigrationConfiguration(config_data)
        
        # Should not crash with invalid versions
        assert not config.is_applicable('invalid', '3.0.0')
        assert not config.is_applicable('1.0.0', 'invalid')


class TestMigrationConfigurationService:
    """Test cases for MigrationConfigurationService class."""
    
    def create_temp_config_file(self, content: dict, format: str = 'yaml') -> str:
        """Create a temporary configuration file."""
        suffix = '.yml' if format == 'yaml' else '.json'
        fd, path = tempfile.mkstemp(suffix=suffix)
        
        try:
            with os.fdopen(fd, 'w') as f:
                if format == 'yaml':
                    yaml.dump(content, f)
                else:
                    json.dump(content, f)
        except:
            os.close(fd)
            raise
            
        return path
        
    def test_load_yaml_configuration(self):
        """Test loading YAML configuration."""
        config_content = {
            'migrations': [
                {
                    'id': 'test-migration',
                    'package_name': 'Test.Package',
                    'version_conditions': [{'type': 'greater_than', 'version': '1.0.0'}],
                    'rules': [
                        {
                            'name': 'Test Rule',
                            'target_nodes': [{'type': 'InvocationExpression'}],
                            'action': {'type': 'remove_invocation'}
                        }
                    ]
                }
            ]
        }
        
        config_file = self.create_temp_config_file(config_content, 'yaml')
        
        try:
            service = MigrationConfigurationService(config_file)
            
            assert len(service.migrations) == 1
            assert 'test-migration' in service.migrations
            
            migration = service.migrations['test-migration']
            assert migration.package_name == 'Test.Package'
            assert len(migration.rules) == 1
            
        finally:
            os.unlink(config_file)
            
    def test_load_json_configuration(self):
        """Test loading JSON configuration."""
        config_content = {
            'migrations': [
                {
                    'id': 'test-migration',
                    'package_name': 'Test.Package',
                    'version_conditions': [{'type': 'greater_than', 'version': '1.0.0'}],
                    'rules': []
                }
            ]
        }
        
        config_file = self.create_temp_config_file(config_content, 'json')
        
        try:
            service = MigrationConfigurationService(config_file)
            assert len(service.migrations) == 1
            
        finally:
            os.unlink(config_file)
            
    def test_nonexistent_config_file(self):
        """Test handling of nonexistent configuration file."""
        service = MigrationConfigurationService('/nonexistent/file.yml')
        assert len(service.migrations) == 0
        
    def test_get_migration_by_id(self):
        """Test getting migration by ID."""
        config_content = {
            'migrations': [
                {
                    'id': 'test-migration',
                    'package_name': 'Test.Package',
                    'version_conditions': [{'type': 'greater_than', 'version': '1.0.0'}],
                    'rules': []
                }
            ]
        }
        
        config_file = self.create_temp_config_file(config_content)
        
        try:
            service = MigrationConfigurationService(config_file)
            
            migration = service.get_migration_by_id('test-migration')
            assert migration is not None
            assert migration.package_name == 'Test.Package'
            
            non_existent = service.get_migration_by_id('non-existent')
            assert non_existent is None
            
        finally:
            os.unlink(config_file)
            
    def test_get_applicable_migrations(self):
        """Test getting applicable migrations for package update."""
        config_content = {
            'migrations': [
                {
                    'id': 'migration-1',
                    'package_name': 'Test.Package',
                    'version_conditions': [{'type': 'greater_than', 'version': '1.0.0'}],
                    'rules': []
                },
                {
                    'id': 'migration-2',
                    'package_name': 'Other.Package',
                    'version_conditions': [{'type': 'greater_than', 'version': '1.0.0'}],
                    'rules': []
                },
                {
                    'id': 'migration-3',
                    'package_name': 'Test.Package',
                    'version_conditions': [{'type': 'greater_than', 'version': '5.0.0'}],
                    'rules': []
                }
            ]
        }
        
        config_file = self.create_temp_config_file(config_content)
        
        try:
            service = MigrationConfigurationService(config_file)
            
            # Should find migration-1 but not migration-3 (version too high)
            applicable = service.get_applicable_migrations('Test.Package', '0.5.0', '2.0.0')
            assert len(applicable) == 1
            assert applicable[0].id == 'migration-1'
            
            # Should find no migrations for non-matching package
            applicable = service.get_applicable_migrations('NonExistent.Package', '0.5.0', '2.0.0')
            assert len(applicable) == 0
            
        finally:
            os.unlink(config_file)
            
    def test_validate_migration_rules(self):
        """Test validation of migration rules."""
        config_content = {
            'migrations': [
                {
                    'id': 'valid-migration',
                    'package_name': 'Test.Package',
                    'version_conditions': [{'type': 'greater_than', 'version': '1.0.0'}],
                    'rules': [
                        {
                            'name': 'Valid Rule',
                            'target_nodes': [{'type': 'InvocationExpression'}],
                            'action': {'type': 'remove_invocation'}
                        }
                    ]
                },
                {
                    'id': 'invalid-migration',
                    'package_name': '',  # Invalid: empty package name
                    'version_conditions': [],  # Invalid: no version conditions
                    'rules': []  # Invalid: no rules
                }
            ]
        }
        
        config_file = self.create_temp_config_file(config_content)
        
        try:
            service = MigrationConfigurationService(config_file)
            
            # Should detect validation errors
            assert not service.validate_migration_rules()
            
        finally:
            os.unlink(config_file)
