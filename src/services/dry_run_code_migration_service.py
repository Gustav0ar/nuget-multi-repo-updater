"""
Dry-run code migration service for analyzing potential C# code transformations.
"""
import logging
import json
import subprocess
import tempfile
import os
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass

from src.services.code_migration_service import MigrationResult


@dataclass
class DryRunMigrationResult:
    """Result of analyzing potential code migrations without applying changes."""
    would_modify_files: List[str]
    potential_changes: List[Dict[str, Any]]
    applicable_rules: List[str]
    analysis_errors: List[str]
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'would_modify_files': self.would_modify_files,
            'potential_changes': self.potential_changes,
            'applicable_rules': self.applicable_rules,
            'analysis_errors': self.analysis_errors,
            'summary': self.summary
        }


class DryRunCodeMigrationService:
    """Service for analyzing potential C# code migrations without making changes."""
    
    def __init__(self, csharp_tool_path: str):
        self.csharp_tool_path = csharp_tool_path
        
    def analyze_potential_migrations(self, target_files: List[str], 
                                   migration_rules: List[Dict[str, Any]], 
                                   working_directory: str = None) -> DryRunMigrationResult:
        """Analyze what migrations would be applied without making changes."""
        if not target_files:
            return DryRunMigrationResult(
                would_modify_files=[],
                potential_changes=[],
                applicable_rules=[],
                analysis_errors=[],
                summary="No target files to analyze"
            )
            
        if not migration_rules:
            return DryRunMigrationResult(
                would_modify_files=[],
                potential_changes=[],
                applicable_rules=[],
                analysis_errors=[],
                summary="No migration rules to analyze"
            )
            
        try:
            # Check if C# migration tool exists and supports dry-run
            if not self._check_tool_availability():
                return self._fallback_analysis(target_files, migration_rules, working_directory)
                
            return self._execute_dry_run_analysis(target_files, migration_rules, working_directory)
            
        except Exception as e:
            logging.error(f"Error during migration analysis: {e}")
            return DryRunMigrationResult(
                would_modify_files=[],
                potential_changes=[],
                applicable_rules=[],
                analysis_errors=[str(e)],
                summary=f"Analysis failed: {str(e)}"
            )
    
    def _check_tool_availability(self) -> bool:
        """Check if the C# migration tool is available."""
        try:
            # Check if the tool directory exists
            if not os.path.exists(self.csharp_tool_path):
                logging.warning(f"C# migration tool not found at: {self.csharp_tool_path}")
                return False
                
            # Try to run the tool with --help to verify it works
            result = subprocess.run(
                ['dotnet', 'run', '--project', self.csharp_tool_path, '--', '--help'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logging.warning(f"Failed to verify C# migration tool: {e}")
            return False
    
    def _execute_dry_run_analysis(self, target_files: List[str], 
                                migration_rules: List[Dict[str, Any]], 
                                working_directory: str = None) -> DryRunMigrationResult:
        """Execute dry-run analysis using the C# migration tool."""
        try:
            # Create temporary rules file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as rules_file:
                json.dump({'rules': migration_rules}, rules_file, indent=2)
                rules_file_path = rules_file.name
                
            try:
                # Prepare command arguments for dry-run
                cmd = [
                    'dotnet', 'run',
                    '--project', self.csharp_tool_path,
                    '--',
                    '--rules-file', rules_file_path
                ]
                
                # Add each target file individually
                for target_file in target_files:
                    cmd.extend(['--target-file', target_file])
                    
                cmd.append('--dry-run')  # Add dry-run flag if supported
                
                if working_directory:
                    cmd.extend(['--working-directory', working_directory])
                    
                logging.info(f"Executing dry-run C# migration analysis: {' '.join(cmd)}")
                
                # Execute the C# migration tool in dry-run mode
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,  # 2 minute timeout for analysis
                    cwd=working_directory
                )
                
                # If dry-run flag is not supported, run normal mode and analyze output
                if result.returncode != 0 and '--dry-run' in result.stderr:
                    logging.info("Tool doesn't support --dry-run flag, using normal analysis")
                    return self._analyze_normal_mode_output(target_files, migration_rules, working_directory)
                
                if result.returncode == 0:
                    # Parse the JSON output from the C# tool
                    try:
                        output_data = json.loads(result.stdout)
                        return self._convert_tool_output_to_dry_run_result(output_data)
                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to parse C# tool output: {e}")
                        return self._fallback_analysis(target_files, migration_rules, working_directory)
                else:
                    logging.error(f"C# migration tool failed: {result.stderr}")
                    return self._fallback_analysis(target_files, migration_rules, working_directory)
                    
            finally:
                # Clean up temporary rules file
                try:
                    os.unlink(rules_file_path)
                except OSError:
                    pass
                    
        except Exception as e:
            logging.error(f"Error executing dry-run analysis: {e}")
            return self._fallback_analysis(target_files, migration_rules, working_directory)
    
    def _analyze_normal_mode_output(self, target_files: List[str], 
                                  migration_rules: List[Dict[str, Any]], 
                                  working_directory: str = None) -> DryRunMigrationResult:
        """Analyze what would happen by running the tool in a temporary copy."""
        import shutil
        import tempfile
        
        try:
            # Create a temporary directory for analysis
            with tempfile.TemporaryDirectory() as temp_dir:
                # Copy files to temporary directory for analysis
                temp_files = []
                for file_path in target_files:
                    if os.path.isabs(file_path):
                        source_path = file_path
                    else:
                        source_path = os.path.join(working_directory or '.', file_path)
                    
                    if os.path.exists(source_path):
                        temp_file = os.path.join(temp_dir, os.path.basename(file_path))
                        shutil.copy2(source_path, temp_file)
                        temp_files.append(temp_file)
                
                # Execute migration on temporary files
                from src.services.code_migration_service import CodeMigrationService
                migration_service = CodeMigrationService(self.csharp_tool_path)
                result = migration_service.execute_migrations(temp_files, migration_rules, temp_dir)
                
                # Analyze the differences
                potential_changes = []
                for i, temp_file in enumerate(temp_files):
                    original_file = target_files[i]
                    if os.path.exists(temp_file):
                        # Check if file was modified by comparing content
                        source_path = target_files[i]
                        if os.path.isabs(source_path):
                            original_path = source_path
                        else:
                            original_path = os.path.join(working_directory or '.', source_path)
                        
                        if os.path.exists(original_path):
                            with open(original_path, 'r', encoding='utf-8') as f:
                                original_content = f.read()
                            with open(temp_file, 'r', encoding='utf-8') as f:
                                modified_content = f.read()
                            
                            if original_content != modified_content:
                                potential_changes.append({
                                    'file': original_file,
                                    'type': 'content_change',
                                    'description': 'File content would be modified by migration rules'
                                })
                
                return DryRunMigrationResult(
                    would_modify_files=result.modified_files if result.success else [],
                    potential_changes=potential_changes,
                    applicable_rules=result.applied_rules,
                    analysis_errors=result.errors,
                    summary=f"Analysis complete - {len(potential_changes)} files would be modified"
                )
                
        except Exception as e:
            logging.error(f"Error in normal mode analysis: {e}")
            return self._fallback_analysis(target_files, migration_rules, working_directory)
    
    def _convert_tool_output_to_dry_run_result(self, output_data: Dict[str, Any]) -> DryRunMigrationResult:
        """Convert C# tool output to dry-run result format."""
        return DryRunMigrationResult(
            would_modify_files=output_data.get('modified_files', []),
            potential_changes=[
                {
                    'file': file_path,
                    'type': 'migration_change',
                    'description': 'File would be modified by migration rules'
                }
                for file_path in output_data.get('modified_files', [])
            ],
            applicable_rules=output_data.get('applied_rules', []),
            analysis_errors=output_data.get('errors', []),
            summary=output_data.get('summary', 'Dry-run analysis completed')
        )
    
    def _fallback_analysis(self, target_files: List[str], 
                         migration_rules: List[Dict[str, Any]], 
                         working_directory: str = None) -> DryRunMigrationResult:
        """Fallback analysis using static code analysis."""
        logging.info("Using fallback static analysis for migration dry-run")
        
        potential_changes = []
        applicable_rules = []
        
        try:
            # Simple static analysis - check if files contain patterns that rules target
            for file_path in target_files:
                if os.path.isabs(file_path):
                    full_path = file_path
                else:
                    full_path = os.path.join(working_directory or '.', file_path)
                
                if os.path.exists(full_path) and file_path.endswith('.cs'):
                    if self._analyze_file_for_migration_patterns(full_path, migration_rules):
                        potential_changes.append({
                            'file': file_path,
                            'type': 'potential_change',
                            'description': 'File contains patterns that may be affected by migration rules'
                        })
            
            # Extract rule names for reporting
            applicable_rules = [rule.get('name', 'Unnamed rule') for rule in migration_rules]
            
            return DryRunMigrationResult(
                would_modify_files=[change['file'] for change in potential_changes],
                potential_changes=potential_changes,
                applicable_rules=applicable_rules,
                analysis_errors=[],
                summary=f"Static analysis complete - {len(potential_changes)} files may be affected"
            )
            
        except Exception as e:
            logging.error(f"Error in fallback analysis: {e}")
            return DryRunMigrationResult(
                would_modify_files=[],
                potential_changes=[],
                applicable_rules=[],
                analysis_errors=[str(e)],
                summary=f"Fallback analysis failed: {str(e)}"
            )
    
    def _analyze_file_for_migration_patterns(self, file_path: str, 
                                           migration_rules: List[Dict[str, Any]]) -> bool:
        """Analyze a single file for patterns that migration rules might affect."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for patterns that rules might target
            for rule in migration_rules:
                target_nodes = rule.get('target_nodes', [])
                for target_node in target_nodes:
                    node_type = target_node.get('type', '').lower()
                    method_name = target_node.get('method_name', '')
                    containing_type = target_node.get('containing_type', '')
                    
                    # Simple pattern matching for common scenarios
                    if method_name and method_name in content:
                        return True
                    if containing_type and containing_type in content:
                        return True
                    if node_type == 'invocationexpression' and method_name:
                        # Look for method calls
                        import re
                        pattern = rf'\b{re.escape(method_name)}\s*\('
                        if re.search(pattern, content):
                            return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error analyzing file {file_path}: {e}")
            return False
