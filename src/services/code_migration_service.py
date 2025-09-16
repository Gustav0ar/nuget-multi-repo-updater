"""
Code migration service for executing C# code transformations.
"""
import logging
import json
import subprocess
import tempfile
import os
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import math






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
        self._cached_executable_path: Optional[str] = None
        
    def _get_executable_path(self) -> Optional[str]:
        """Get the path to the executable, building if necessary."""
        # Return cached path if we already found it
        if self._cached_executable_path:
            return self._cached_executable_path
            
        tool_dir = Path(self.csharp_tool_path)
        
        if not tool_dir.exists():
            logging.warning(f"CSharpMigrationTool directory not found: {tool_dir}")
            return None
            
        # Check for built executable in any .NET version
        bin_debug_dir = tool_dir / 'bin' / 'Debug'
        
        if bin_debug_dir.exists():
            # Find all target framework directories (e.g., net6.0, net7.0, net8.0, net9.0, etc.)
            target_framework_dirs = [d for d in bin_debug_dir.iterdir() 
                                   if d.is_dir() and d.name.startswith('net')]
            
            # Sort by version number (newest first) - properly handle numeric versions
            def parse_net_version(dirname):
                try:
                    # Extract version number from netX.Y format
                    version_str = dirname.removeprefix('net')
                    # Split on '.' and convert to tuple of ints for proper comparison
                    version_parts = tuple(int(x) for x in version_str.split('.'))
                    return version_parts
                except (ValueError, AttributeError):
                    # Fallback to string comparison for non-standard names
                    return (0, 0)  # Put unrecognized versions at the end
            
            target_framework_dirs.sort(key=lambda x: parse_net_version(x.name), reverse=True)
            
            for bin_dir in target_framework_dirs:
                exe_path = bin_dir / 'CSharpMigrationTool'  # Linux executable
                exe_path_win = bin_dir / 'CSharpMigrationTool.exe'  # Windows executable
                dll_path = bin_dir / 'CSharpMigrationTool.dll'
                
                if exe_path.exists():
                    self._cached_executable_path = str(exe_path)
                    logging.info(f"Found C# migration tool executable: {self._cached_executable_path}")
                    return self._cached_executable_path
                elif exe_path_win.exists():
                    self._cached_executable_path = str(exe_path_win)
                    logging.info(f"Found C# migration tool executable: {self._cached_executable_path}")
                    return self._cached_executable_path
                elif dll_path.exists():
                    self._cached_executable_path = str(dll_path)
                    logging.info(f"Found C# migration tool DLL: {self._cached_executable_path}")
                    return self._cached_executable_path
        
        # If no built binary found, try to build the tool
        return self._build_tool_if_needed(tool_dir)
        
    def _build_tool_if_needed(self, tool_dir: Path) -> Optional[str]:
        """Build the C# migration tool if it's not already built."""
        try:
            # Check if dotnet is available
            result = subprocess.run(['dotnet', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logging.warning(".NET SDK not available, cannot build C# migration tool")
                return None
            
            # Check if the tool directory has a .csproj file
            csproj_files = list(tool_dir.glob('*.csproj'))
            if not csproj_files:
                logging.warning(f"No .csproj file found in {tool_dir}, cannot build")
                return None
            
            logging.info(f"Building C# migration tool in {tool_dir}...")
            
            # Build the tool
            build_result = subprocess.run(
                ['dotnet', 'build', '--configuration', 'Debug'],
                cwd=str(tool_dir),
                capture_output=True,
                text=True,
                timeout=120  # Allow up to 2 minutes for build
            )
            
            if build_result.returncode != 0:
                logging.error(f"Failed to build C# migration tool: {build_result.stderr}")
                return None
            
            logging.info("C# migration tool built successfully")
            
            # Now check again for the built executable using dynamic discovery
            bin_debug_dir = tool_dir / 'bin' / 'Debug'
            
            if bin_debug_dir.exists():
                # Find all target framework directories
                target_framework_dirs = [d for d in bin_debug_dir.iterdir() 
                                       if d.is_dir() and d.name.startswith('net')]
                
                # Sort by version number (newest first) - properly handle numeric versions
                def parse_net_version(dirname):
                    try:
                        # Extract version number from netX.Y format
                        version_str = dirname.removeprefix('net')
                        # Split on '.' and convert to tuple of ints for proper comparison
                        version_parts = tuple(int(x) for x in version_str.split('.'))
                        return version_parts
                    except (ValueError, AttributeError):
                        # Fallback for non-standard names
                        return (0, 0)  # Put unrecognized versions at the end
                
                target_framework_dirs.sort(key=lambda x: parse_net_version(x.name), reverse=True)
                
                for bin_dir in target_framework_dirs:
                    exe_path = bin_dir / 'CSharpMigrationTool'
                    exe_path_win = bin_dir / 'CSharpMigrationTool.exe'
                    dll_path = bin_dir / 'CSharpMigrationTool.dll'
                    
                    if exe_path.exists():
                        self._cached_executable_path = str(exe_path)
                        logging.info(f"Built and found executable: {self._cached_executable_path}")
                        return self._cached_executable_path
                    elif exe_path_win.exists():
                        self._cached_executable_path = str(exe_path_win)
                        logging.info(f"Built and found executable: {self._cached_executable_path}")
                        return self._cached_executable_path
                    elif dll_path.exists():
                        self._cached_executable_path = str(dll_path)
                        logging.info(f"Built and found DLL: {self._cached_executable_path}")
                        return self._cached_executable_path
            
            logging.warning("Built C# migration tool, but executable not found in expected location")
            return None
            
        except FileNotFoundError:
            logging.warning("dotnet command not found, cannot build C# migration tool")
            return None
        except subprocess.TimeoutExpired:
            logging.error("Timeout while building C# migration tool")
            return None
        except Exception as e:
            logging.error(f"Error building C# migration tool: {e}")
            return None
            
    def _prepare_command(self, rules_file_path: str, target_files: List[str], 
                        working_directory: str = None) -> Tuple[List[str], bool]:
        """Prepare the command to execute the migration tool.
        
        Returns:
            Tuple of (command_args, use_dotnet_run)
        """
        executable_path = self._get_executable_path()
        
        if executable_path:
            # We have a built executable/DLL, use it directly
            if executable_path.endswith('.dll'):
                # Use dotnet to run the DLL
                cmd = ['dotnet', executable_path]
            else:
                # Direct executable
                cmd = [executable_path]
                
            # Add the arguments
            cmd.extend([
                '--rules-file', rules_file_path
            ])
            
            # Add each target file as a separate argument to avoid command line length limits
            for target_file in target_files:
                cmd.extend(['--target-file', target_file])
            
            if working_directory:
                cmd.extend(['--working-directory', working_directory])
                
            return cmd, False
        else:
            # Fall back to dotnet run (which will build if needed)
            logging.warning("No built executable found, falling back to 'dotnet run'")
            cmd = [
                'dotnet', 'run',
                '--project', self.csharp_tool_path,
                '--',
                '--rules-file', rules_file_path
            ]
            
            # Add each target file as a separate argument
            for target_file in target_files:
                cmd.extend(['--target-file', target_file])
            
            if working_directory:
                cmd.extend(['--working-directory', working_directory])
                
            return cmd, True
        
    def _create_rules_file(self, migration_rules: List[Dict[str, Any]]) -> str:
        """Create a temporary file for migration rules and return its path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as rules_file:
            json.dump({'rules': migration_rules}, rules_file, indent=2)
            return rules_file.name

    def execute_migrations(self, target_files: List[str], migration_rules: List[Dict[str, Any]],
                           working_directory: str = None) -> MigrationResult:
        """Execute migrations on the specified C# files in parallel batches."""
        if not target_files:
            return MigrationResult(success=True, modified_files=[], applied_rules=[], errors=[],
                                   summary="No target files to process")

        if not migration_rules:
            return MigrationResult(success=True, modified_files=[], applied_rules=[], errors=[],
                                   summary="No migration rules to apply")

        # Validate that the C# migration tool is available before proceeding
        if not self.validate_tool_availability():
            return MigrationResult(
                success=False,
                modified_files=[],
                applied_rules=[],
                errors=["C# migration tool is not available and could not be built"],
                summary="Migration failed: C# migration tool unavailable"
            )

        rules_file_path = self._create_rules_file(migration_rules)
        try:
            batch_size = 10
            num_batches = math.ceil(len(target_files) / batch_size)
            file_batches = [target_files[i:i + batch_size] for i in range(0, len(target_files), batch_size)]

            max_workers = os.cpu_count() or 1
            logging.info(f"Processing {len(target_files)} files in {num_batches} batches using up to {max_workers} workers.")

            all_modified_files = set()
            all_applied_rules = set()
            all_errors = []
            overall_success = True

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_batch = {executor.submit(self._execute_batch, rules_file_path, batch, working_directory):
                                   batch for batch in file_batches}

                for future in as_completed(future_to_batch):
                    batch_result = future.result()
                    if not batch_result.success:
                        overall_success = False
                    all_modified_files.update(batch_result.modified_files)
                    all_applied_rules.update(batch_result.applied_rules)
                    all_errors.extend(batch_result.errors)

            summary = f"Overall migration completed. Success: {overall_success}. "
            summary += f"Modified files: {len(all_modified_files)}. Applied rules: {len(all_applied_rules)}. "
            summary += f"Errors: {len(all_errors)}."

            return MigrationResult(
                success=overall_success,
                modified_files=sorted(list(all_modified_files)),
                applied_rules=sorted(list(all_applied_rules)),
                errors=all_errors,
                summary=summary
            )
        finally:
            try:
                os.unlink(rules_file_path)
            except Exception as e:
                logging.warning(f"Failed to clean up temporary rules file: {e}")

    def _execute_batch(self, rules_file_path: str, batch_files: List[str], working_directory: Optional[str]) -> MigrationResult:
        """Execute migration for a single batch of files."""
        try:
            cmd, use_dotnet_run = self._prepare_command(rules_file_path, batch_files, working_directory)

            if use_dotnet_run:
                logging.info(f"Executing batch with 'dotnet run': {' '.join(cmd)}")
            else:
                logging.info(f"Executing batch with pre-built executable: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5-minute timeout per batch
                cwd=working_directory
            )

            if result.returncode == 0:
                try:
                    output_data = json.loads(result.stdout)
                    return MigrationResult(
                        success=output_data.get('success', False),
                        modified_files=output_data.get('modified_files', []),
                        applied_rules=output_data.get('applied_rules', []),
                        errors=output_data.get('errors', []),
                        summary=output_data.get('summary', 'Batch completed')
                    )
                except json.JSONDecodeError as e:
                    logging.error(f"Failed to parse C# tool output for batch: {e}")
                    return MigrationResult(success=False, modified_files=[], applied_rules=[],
                                           errors=[f"Failed to parse tool output: {e}"],
                                           summary="Batch failed due to output parsing error")
            else:
                logging.error(f"C# migration tool failed for batch with exit code {result.returncode}")
                logging.error(f"Tool stderr: {result.stderr}")
                return MigrationResult(success=False, modified_files=[], applied_rules=[],
                                       errors=[f"Tool execution failed: {result.stderr}"],
                                       summary=f"Batch failed with exit code {result.returncode}")

        except subprocess.TimeoutExpired:
            logging.error("C# migration tool timed out for a batch")
            return MigrationResult(success=False, modified_files=[], applied_rules=[],
                                   errors=["Migration tool execution timed out for a batch"],
                                   summary="Batch failed due to timeout")
        except Exception as e:
            logging.error(f"Failed to execute C# migration tool for a batch: {e}")
            return MigrationResult(success=False, modified_files=[], applied_rules=[],
                                   errors=[f"Execution error: {str(e)}"],
                                   summary="Batch failed due to execution error")
            
    def validate_tool_availability(self) -> bool:
        """Check if the C# migration tool is available and functional."""
        try:
            # First try to get an executable path (will build if needed)
            executable_path = self._get_executable_path()
            
            if executable_path:
                logging.info(f"C# migration tool is available at: {executable_path}")
                return True
            else:
                logging.error("C# migration tool is not available and could not be built")
                return False
                
        except Exception as e:
            logging.error(f"Error validating C# migration tool availability: {e}")
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
