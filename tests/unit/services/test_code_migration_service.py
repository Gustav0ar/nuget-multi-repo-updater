"""
Unit tests for code migration service.
"""
import pytest
import tempfile
import os
import json
import subprocess
from unittest.mock import Mock, patch, MagicMock
from src.services.code_migration_service import (
    CodeMigrationService,
    MigrationResult
)
from src.services.migration_configuration_service import MigrationConfiguration


class MigrationError(Exception):
    """Test exception for migration errors."""
    pass


class TestMigrationResult:
    """Test cases for MigrationResult dataclass."""
    
    def test_migration_result_creation(self):
        """Test creating a migration result."""
        result = MigrationResult(
            success=True,
            modified_files=['file1.cs', 'file2.cs'],
            applied_rules=['rule1', 'rule2'],
            errors=[],
            summary='Migration completed successfully'
        )
        
        assert result.success is True
        assert len(result.modified_files) == 2
        assert len(result.applied_rules) == 2
        assert result.summary == 'Migration completed successfully'
        
    def test_migration_result_to_dict(self):
        """Test converting migration result to dictionary."""
        result = MigrationResult(
            success=False,
            modified_files=[],
            applied_rules=[],
            errors=['Error occurred'],
            summary='Migration failed'
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['success'] is False
        assert result_dict['errors'] == ['Error occurred']
        assert result_dict['summary'] == 'Migration failed'


class TestCodeMigrationService:
    """Test cases for CodeMigrationService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = CodeMigrationService('/path/to/csharp-tool')
        
    def test_execute_migrations_empty_files(self):
        """Test migration execution with empty file list."""
        result = self.service.execute_migrations([], [])
        
        assert result.success is True
        assert result.modified_files == []
        assert result.applied_rules == []
        assert result.summary == "No target files to process"
        
    def test_execute_migrations_with_files(self):
        """Test migration execution with files."""
        target_files = ['test.cs']
        migration_rules = [
            {
                'name': 'Test Rule',
                'target_nodes': [{'type': 'InvocationExpression'}],
                'action': {'type': 'remove_invocation'}
            }
        ]
        
        # Mock successful subprocess execution
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'success': True,
            'modified_files': ['test.cs'],
            'applied_rules': ['Test Rule'],
            'errors': [],
            'summary': 'Migration completed'
        })
        mock_result.stderr = ''
        
        with patch('subprocess.run', return_value=mock_result), \
             patch('os.path.exists', return_value=True):
            
            result = self.service.execute_migrations(target_files, migration_rules)
            
            assert result.success is True
            assert result.modified_files == ['test.cs']
            assert result.applied_rules == ['Test Rule']
