"""
Code migration service for executing C# code transformations.
"""
import logging
import json
import subprocess
import tempfile
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class MigrationResult:
    """Result of executing code migrations."""
    success: bool
    modified_files: List[str]
    applied_rules: List[str]
    errors: List[str]
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'success': self.success,
            'modified_files': self.modified_files,
            'applied_rules': self.applied_rules,
            'errors': self.errors,
            'summary': self.summary
        }


class CodeMigrationService:
    """Service for executing C# code migrations using external tool."""
    
    def __init__(self, csharp_tool_path: str):
        self.csharp_tool_path = csharp_tool_path
        
    def execute_migrations(self, target_files: List[str], migration_rules: List[Dict[str, Any]], 
                          working_directory: str = None) -> MigrationResult:
        """Execute migrations on the specified C# files."""
        if not target_files:
            return MigrationResult(
                success=True,
                modified_files=[],
                applied_rules=[],
                errors=[],
                summary="No target files to process"
            )
            
        if not migration_rules:
            return MigrationResult(
                success=True,
                modified_files=[],
                applied_rules=[],
                errors=[],
                summary="No migration rules to apply"
            )
            
        try:
            # Create temporary rules file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as rules_file:
                json.dump({'rules': migration_rules}, rules_file, indent=2)
                rules_file_path = rules_file.name
                
            try:
                # Prepare command arguments
                cmd = [
                    'dotnet', 'run',
                    '--project', self.csharp_tool_path,
                    '--',
                    '--rules-file', rules_file_path,
                    '--target-files', ','.join(target_files)
                ]
                
                if working_directory:
                    cmd.extend(['--working-directory', working_directory])
                    
                logging.info(f"Executing C# migration tool: {' '.join(cmd)}")
                
                # Execute the C# migration tool
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    cwd=working_directory
                )
                
                if result.returncode == 0:
                    # Parse the JSON output from the C# tool
                    try:
                        output_data = json.loads(result.stdout)
                        return MigrationResult(
                            success=output_data.get('success', False),
                            modified_files=output_data.get('modified_files', []),
                            applied_rules=output_data.get('applied_rules', []),
                            errors=output_data.get('errors', []),
                            summary=output_data.get('summary', 'Migration completed')
                        )
                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to parse C# tool output: {e}")
                        logging.error(f"Tool output: {result.stdout}")
                        return MigrationResult(
                            success=False,
                            modified_files=[],
                            applied_rules=[],
                            errors=[f"Failed to parse tool output: {e}"],
                            summary="Migration failed due to output parsing error"
                        )
                else:
                    logging.error(f"C# migration tool failed with exit code {result.returncode}")
                    logging.error(f"Tool stderr: {result.stderr}")
                    return MigrationResult(
                        success=False,
                        modified_files=[],
                        applied_rules=[],
                        errors=[f"Tool execution failed: {result.stderr}"],
                        summary=f"Migration tool failed with exit code {result.returncode}"
                    )
                    
            finally:
                # Clean up temporary rules file
                try:
                    os.unlink(rules_file_path)
                except Exception as e:
                    logging.warning(f"Failed to clean up temporary rules file: {e}")
                    
        except subprocess.TimeoutExpired:
            logging.error("C# migration tool timed out")
            return MigrationResult(
                success=False,
                modified_files=[],
                applied_rules=[],
                errors=["Migration tool execution timed out"],
                summary="Migration failed due to timeout"
            )
        except Exception as e:
            logging.error(f"Failed to execute C# migration tool: {e}")
            return MigrationResult(
                success=False,
                modified_files=[],
                applied_rules=[],
                errors=[f"Execution error: {str(e)}"],
                summary="Migration failed due to execution error"
            )
            
    def validate_tool_availability(self) -> bool:
        """Check if the C# migration tool is available and functional."""
        try:
            # Check if dotnet is available
            result = subprocess.run(['dotnet', '--version'], capture_output=True, text=True)
            if result.returncode != 0:
                logging.error("dotnet CLI not available")
                return False
                
            # Check if the migration tool project exists
            if not os.path.exists(self.csharp_tool_path):
                logging.error(f"C# migration tool not found at: {self.csharp_tool_path}")
                return False
                
            # Try to build the tool
            build_result = subprocess.run(
                ['dotnet', 'build', self.csharp_tool_path],
                capture_output=True,
                text=True
            )
            
            if build_result.returncode != 0:
                logging.error(f"Failed to build C# migration tool: {build_result.stderr}")
                return False
                
            logging.info("C# migration tool is available and ready")
            return True
            
        except Exception as e:
            logging.error(f"Failed to validate C# migration tool: {e}")
            return False
            
    def generate_migration_report(self, results: MigrationResult) -> str:
        """Generate a human-readable migration report."""
        report_lines = [
            "=== CODE MIGRATION REPORT ===",
            ""
        ]
        
        if results.success:
            report_lines.append("✅ Migration completed successfully")
        else:
            report_lines.append("❌ Migration failed")
            
        report_lines.append(f"📋 Summary: {results.summary}")
        report_lines.append("")
        
        if results.applied_rules:
            report_lines.append("✅ Applied Rules:")
            for rule in results.applied_rules:
                report_lines.append(f"  • {rule}")
            report_lines.append("")
            
        if results.modified_files:
            report_lines.append("📝 Modified Files:")
            for file_path in results.modified_files:
                report_lines.append(f"  • {file_path}")
            report_lines.append("")
            
        if results.errors:
            report_lines.append("❌ Errors:")
            for error in results.errors:
                report_lines.append(f"  • {error}")
            report_lines.append("")
            
        return "\n".join(report_lines)
