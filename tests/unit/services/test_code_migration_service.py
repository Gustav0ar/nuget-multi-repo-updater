"""
Unit tests for code migration service.
"""
import pytest
import tempfile
import os
import json
import subprocess
from unittest.mock import Mock, patch, MagicMock, call
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
             patch('os.path.exists', return_value=True), \
             patch.object(self.service, 'validate_tool_availability', return_value=True):
            
            result = self.service.execute_migrations(target_files, migration_rules)
            
            assert result.success is True
            assert result.modified_files == ['test.cs']
            assert result.applied_rules == ['Test Rule']

    def test_get_executable_path_rebuilds_when_any_source_changes(self, tmp_path):
        """If any C# source file changes, we must rebuild instead of running a stale DLL."""
        tool_dir = tmp_path / 'CSharpMigrationTool'
        (tool_dir / 'Services').mkdir(parents=True)
        (tool_dir / 'Models').mkdir(parents=True)
        (tool_dir / 'bin' / 'Debug' / 'net10.0').mkdir(parents=True)

        # Minimal project layout expected by CodeMigrationService
        csproj = tool_dir / 'CSharpMigrationTool.csproj'
        program_cs = tool_dir / 'Program.cs'
        engine_cs = tool_dir / 'Services' / 'MigrationEngine.cs'
        models_cs = tool_dir / 'Models' / 'MigrationModels.cs'

        csproj.write_text('<Project></Project>')
        program_cs.write_text('class Program {}')
        engine_cs.write_text('class MigrationEngine {}')
        models_cs.write_text('class MigrationModels {}')

        # This file is NOT one of the previously hard-coded inputs; changes here must still trigger rebuild.
        extra_source = tool_dir / 'Services' / 'Extra.cs'
        extra_source.write_text('class Extra {}')

        dll_path = tool_dir / 'bin' / 'Debug' / 'net10.0' / 'CSharpMigrationTool.dll'
        dll_path.write_text('stub')

        # Set deterministic mtimes so DLL looks older than the sources.
        # We must set mtimes for *all* relevant inputs, otherwise the local filesystem clock
        # will make them appear newer than our synthetic timestamps.
        base = 1_000_000_000
        sources_mtime = base + 10
        changed_source_mtime = base + 20
        os.utime(csproj, (sources_mtime, sources_mtime))
        os.utime(program_cs, (sources_mtime, sources_mtime))
        os.utime(engine_cs, (sources_mtime, sources_mtime))
        os.utime(models_cs, (sources_mtime, sources_mtime))
        os.utime(extra_source, (changed_source_mtime, changed_source_mtime))
        os.utime(dll_path, (base + 5, base + 5))

        svc = CodeMigrationService(str(tool_dir))

        def fake_run(cmd, *args, **kwargs):
            # dotnet availability check
            if cmd == ['dotnet', '--info']:
                r = Mock(); r.returncode = 0; r.stdout = 'info'; r.stderr = ''
                return r
            # build
            if cmd[:3] == ['dotnet', 'build', '--configuration']:
                # Simulate that a successful build produces a fresh DLL newer than sources.
                latest = max(
                    csproj.stat().st_mtime,
                    program_cs.stat().st_mtime,
                    engine_cs.stat().st_mtime,
                    models_cs.stat().st_mtime,
                    extra_source.stat().st_mtime,
                )
                os.utime(dll_path, (latest + 1, latest + 1))
                r = Mock(); r.returncode = 0; r.stdout = 'build ok'; r.stderr = ''
                return r
            # verify DLL runs
            if cmd[0] == 'dotnet' and cmd[-1] == '--help':
                r = Mock(); r.returncode = 0; r.stdout = 'C# Code Migration Tool'; r.stderr = ''
                return r
            raise AssertionError(f"Unexpected subprocess call: {cmd}")

        with patch('subprocess.run', side_effect=fake_run) as run_mock:
            exe1 = svc._get_executable_path()
            assert exe1 is not None
            assert exe1.endswith('CSharpMigrationTool.dll')
            assert any(c.args[0][:3] == ['dotnet', 'build', '--configuration'] for c in run_mock.mock_calls)

            # Calling again without changes should reuse cache and not rebuild
            run_mock.reset_mock()
            exe2 = svc._get_executable_path()
            assert exe2 == exe1
            assert not any(c.args[0][:3] == ['dotnet', 'build', '--configuration'] for c in run_mock.mock_calls)

            # Touch a source file; next call must rebuild
            newer = changed_source_mtime + 10
            os.utime(extra_source, (newer, newer))
            run_mock.reset_mock()
            exe3 = svc._get_executable_path()
            assert exe3 == exe1
            assert any(c.args[0][:3] == ['dotnet', 'build', '--configuration'] for c in run_mock.mock_calls)
