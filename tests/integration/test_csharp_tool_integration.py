"""
End-to-end tests for the C# migration tool.
"""
import pytest
import tempfile
import os
import shutil
import json
import subprocess
from pathlib import Path


class TestCSharpMigrationTool:
    """End-to-end tests for the C# migration tool."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.temp_dir, 'TestProject')
        os.makedirs(self.project_dir)
        
        # Create sample C# project
        self.create_sample_project()
        
        # Build the C# tool if it exists
        self.tool_path = self.get_tool_path()
        
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            
    def get_tool_path(self):
        """Get the path to the C# migration tool."""
        # Assumes the tool is built in the workspace
        workspace_root = Path(__file__).parent.parent.parent
        tool_dir = workspace_root / 'CSharpMigrationTool'
        
        if not tool_dir.exists():
            return None
            
        # Check for built executable
        bin_dir = tool_dir / 'bin' / 'Debug' / 'net7.0'
        exe_path = bin_dir / 'CSharpMigrationTool.exe'
        dll_path = bin_dir / 'CSharpMigrationTool.dll'
        
        if exe_path.exists():
            return str(exe_path)
        elif dll_path.exists():
            return str(dll_path)
        else:
            return None
            
    def create_sample_project(self):
        """Create a sample C# project for testing."""
        # Create .csproj file
        csproj_content = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net7.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="TestPackage" Version="2.0.0" />
  </ItemGroup>
</Project>'''
        
        with open(os.path.join(self.project_dir, 'TestProject.csproj'), 'w') as f:
            f.write(csproj_content)
            
        # Create test C# file with various scenarios
        cs_content = '''using System;
using TestPackage;

namespace TestProject
{
    public class TestClass
    {
        public void TestRemoveInvocation()
        {
            // Simple method call that should be removed
            TestPackage.DeprecatedMethod();
            
            Console.WriteLine("This should remain");
        }
        
        public void TestChainedRemoval()
        {
            // Method chaining scenario
            var builder = new StringBuilder()
                .Append("Hello")
                .DeprecatedMethod()  // This should be removed
                .Append("World");
        }
        
        public void TestMethodRename()
        {
            // Method that should be renamed
            var result = TestPackage.OldMethod("parameter");
            
            // Multiple calls
            OldMethod();
            var x = OldMethod("test");
        }
        
        public void TestComplexScenario()
        {
            // Nested scenarios
            if (true)
            {
                TestPackage.DeprecatedMethod();
                var result = OldMethod("nested");
            }
        }
    }
}'''
        
        with open(os.path.join(self.project_dir, 'TestClass.cs'), 'w') as f:
            f.write(cs_content)
            
    def create_migration_rules_file(self, rules):
        """Create a temporary migration rules file."""
        rules_content = {
            'migrations': [
                {
                    'id': 'test-migration',
                    'package_name': 'TestPackage',
                    'rules': rules
                }
            ]
        }
        
        rules_file = os.path.join(self.temp_dir, 'migration-rules.json')
        with open(rules_file, 'w') as f:
            json.dump(rules_content, f, indent=2)
            
        return rules_file
        
    @pytest.mark.skipif(True, reason="Requires built C# tool")
    def test_remove_invocation_rule(self):
        """Test removing method invocations."""
        if not self.tool_path:
            pytest.skip("C# migration tool not available")
            
        # Create rules for removing DeprecatedMethod calls
        rules = [
            {
                'name': 'Remove DeprecatedMethod',
                'target_nodes': [
                    {
                        'type': 'InvocationExpression',
                        'method_name': 'DeprecatedMethod'
                    }
                ],
                'action': {
                    'type': 'remove_invocation',
                    'strategy': 'smart_chain_aware'
                }
            }
        ]
        
        rules_file = self.create_migration_rules_file(rules)
        
        try:
            # Run the C# migration tool
            if self.tool_path.endswith('.dll'):
                cmd = ['dotnet', self.tool_path, self.project_dir, rules_file]
            else:
                cmd = [self.tool_path, self.project_dir, rules_file]
                
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            assert result.returncode == 0, f"Tool failed: {result.stderr}"
            
            # Parse the JSON output
            output_data = json.loads(result.stdout)
            
            assert output_data['success'] is True
            assert 'TestClass.cs' in output_data['files_modified']
            assert 'Remove DeprecatedMethod' in output_data['rules_applied']
            
            # Verify the file was actually modified
            with open(os.path.join(self.project_dir, 'TestClass.cs'), 'r') as f:
                modified_content = f.read()
                
            # DeprecatedMethod calls should be removed
            assert 'DeprecatedMethod()' not in modified_content
            # Other content should remain
            assert 'Console.WriteLine' in modified_content
            assert 'StringBuilder' in modified_content
            
        finally:
            if os.path.exists(rules_file):
                os.unlink(rules_file)
                
    @pytest.mark.skipif(True, reason="Requires built C# tool")
    def test_replace_method_name_rule(self):
        """Test replacing method names."""
        if not self.tool_path:
            pytest.skip("C# migration tool not available")
            
        # Create rules for renaming OldMethod to NewMethod
        rules = [
            {
                'name': 'Rename OldMethod',
                'target_nodes': [
                    {
                        'type': 'InvocationExpression',
                        'method_name': 'OldMethod'
                    }
                ],
                'action': {
                    'type': 'replace_method_name',
                    'new_name': 'NewMethod'
                }
            }
        ]
        
        rules_file = self.create_migration_rules_file(rules)
        
        try:
            # Run the migration tool
            if self.tool_path.endswith('.dll'):
                cmd = ['dotnet', self.tool_path, self.project_dir, rules_file]
            else:
                cmd = [self.tool_path, self.project_dir, rules_file]
                
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            assert result.returncode == 0, f"Tool failed: {result.stderr}"
            
            # Parse output
            output_data = json.loads(result.stdout)
            
            assert output_data['success'] is True
            assert 'TestClass.cs' in output_data['files_modified']
            
            # Verify the file was modified
            with open(os.path.join(self.project_dir, 'TestClass.cs'), 'r') as f:
                modified_content = f.read()
                
            # OldMethod should be replaced with NewMethod
            assert 'OldMethod(' not in modified_content
            assert 'NewMethod(' in modified_content
            
        finally:
            if os.path.exists(rules_file):
                os.unlink(rules_file)
                
    @pytest.mark.skipif(True, reason="Requires built C# tool")
    def test_multiple_rules(self):
        """Test applying multiple migration rules."""
        if not self.tool_path:
            pytest.skip("C# migration tool not available")
            
        # Create multiple rules
        rules = [
            {
                'name': 'Remove DeprecatedMethod',
                'target_nodes': [
                    {
                        'type': 'InvocationExpression',
                        'method_name': 'DeprecatedMethod'
                    }
                ],
                'action': {
                    'type': 'remove_invocation',
                    'strategy': 'smart_chain_aware'
                }
            },
            {
                'name': 'Rename OldMethod',
                'target_nodes': [
                    {
                        'type': 'InvocationExpression',
                        'method_name': 'OldMethod'
                    }
                ],
                'action': {
                    'type': 'replace_method_name',
                    'new_name': 'NewMethod'
                }
            }
        ]
        
        rules_file = self.create_migration_rules_file(rules)
        
        try:
            # Run the migration tool
            if self.tool_path.endswith('.dll'):
                cmd = ['dotnet', self.tool_path, self.project_dir, rules_file]
            else:
                cmd = [self.tool_path, self.project_dir, rules_file]
                
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            assert result.returncode == 0, f"Tool failed: {result.stderr}"
            
            # Parse output
            output_data = json.loads(result.stdout)
            
            assert output_data['success'] is True
            assert len(output_data['rules_applied']) == 2
            
            # Verify both transformations were applied
            with open(os.path.join(self.project_dir, 'TestClass.cs'), 'r') as f:
                modified_content = f.read()
                
            assert 'DeprecatedMethod()' not in modified_content
            assert 'OldMethod(' not in modified_content
            assert 'NewMethod(' in modified_content
            
        finally:
            if os.path.exists(rules_file):
                os.unlink(rules_file)
                
    def test_tool_error_handling(self):
        """Test tool error handling with invalid inputs."""
        if not self.tool_path:
            pytest.skip("C# migration tool not available")
            
        # Test with non-existent directory
        if self.tool_path.endswith('.dll'):
            cmd = ['dotnet', self.tool_path, '/nonexistent/directory', 'rules.json']
        else:
            cmd = [self.tool_path, '/nonexistent/directory', 'rules.json']
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should exit with error code
        assert result.returncode != 0
        
    def test_tool_with_invalid_rules_file(self):
        """Test tool with invalid rules file."""
        if not self.tool_path:
            pytest.skip("C# migration tool not available")
            
        # Create invalid JSON file
        invalid_rules_file = os.path.join(self.temp_dir, 'invalid.json')
        with open(invalid_rules_file, 'w') as f:
            f.write('invalid json content')
            
        try:
            if self.tool_path.endswith('.dll'):
                cmd = ['dotnet', self.tool_path, self.project_dir, invalid_rules_file]
            else:
                cmd = [self.tool_path, self.project_dir, invalid_rules_file]
                
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Should handle the error gracefully
            assert result.returncode != 0
            
        finally:
            if os.path.exists(invalid_rules_file):
                os.unlink(invalid_rules_file)
