"""
Code migration service for executing C# code transformations.
"""
import logging
import json
import subprocess
import tempfile
import os
import platform
import time
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path


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
        
    def _normalize_path_for_subprocess(self, path: str) -> str:
        """Normalize path for subprocess compatibility across platforms."""
        if not path:
            return path

        # Convert to Path object to handle separators properly
        path_obj = Path(path)

        # On Windows, convert backslashes to forward slashes for subprocess compatibility
        # Windows cmd.exe and PowerShell can handle forward slashes
        if platform.system().lower() == 'windows':
            return str(path_obj).replace('\\', '/')
        else:
            return str(path_obj)

    def _get_executable_candidates(self, bin_dir: Path) -> List[Path]:
        """Get executable candidates in priority order based on current OS."""
        base_name = 'CSharpMigrationTool'
        candidates = []

        # Determine OS and set priority order
        current_os = platform.system().lower()

        if current_os == 'windows':
            # Windows: prioritize .exe, then .dll, then no extension
            candidates = [
                bin_dir / f'{base_name}.exe',
                bin_dir / f'{base_name}.dll',
                bin_dir / base_name
            ]
        else:
            # Unix-like systems: prioritize .dll (runs via dotnet), then no extension
            candidates = [
                bin_dir / f'{base_name}.dll',
                bin_dir / base_name
            ]

        return candidates

    def _is_tool_outdated(self, tool_dir: Path, executable_path: Path) -> bool:
        """Return True if the tool binary is older than its sources.

        This prevents using stale binaries that can apply old/buggy transformations.
        """
        try:
            if not executable_path.exists():
                return True

            exe_mtime = executable_path.stat().st_mtime

            # Consider csproj + key source files. (Cheap and sufficient for this repo.)
            inputs = []
            inputs.extend(tool_dir.glob('*.csproj'))
            inputs.append(tool_dir / 'Program.cs')
            inputs.append(tool_dir / 'Services' / 'MigrationEngine.cs')
            inputs.append(tool_dir / 'Models' / 'MigrationModels.cs')

            for path in inputs:
                if path.exists() and path.stat().st_mtime > exe_mtime:
                    return True

            return False
        except Exception:
            # If we can't tell, err on the safe side and rebuild.
            return True

    def _verify_executable_works(self, executable_path: Path) -> bool:
        """Quickly verify the discovered executable can run on this machine."""
        try:
            if not executable_path.exists():
                return False

            if str(executable_path).endswith('.dll'):
                cmd = ['dotnet', self._normalize_path_for_subprocess(str(executable_path)), '--help']
            else:
                cmd = [self._normalize_path_for_subprocess(str(executable_path)), '--help']

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            return result.returncode == 0 and 'C# Code Migration Tool' in (result.stdout or '')
        except Exception:
            return False

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
                    # Extract version number from netX.Y format (compatible with older Python)
                    version_str = dirname.replace('net', '', 1) if dirname.startswith('net') else dirname
                    # Split on '.' and convert to tuple of ints for proper comparison
                    version_parts = tuple(int(x) for x in version_str.split('.'))
                    return version_parts
                except (ValueError, AttributeError):
                    # Fallback to string comparison for non-standard names
                    return (0, 0)  # Put unrecognized versions at the end
            
            target_framework_dirs.sort(key=lambda x: parse_net_version(x.name), reverse=True)
            
            for bin_dir in target_framework_dirs:
                # Get executable candidates in OS-appropriate priority order
                candidates = self._get_executable_candidates(bin_dir)
                
                for exe_path in candidates:
                    if exe_path.exists():
                        # If the binary is older than sources, rebuild and re-discover.
                        if self._is_tool_outdated(tool_dir, exe_path):
                            logging.info("C# tool binary is outdated; rebuilding...")
                            self._cached_executable_path = None
                            rebuilt = self._build_tool_if_needed(tool_dir)
                            if rebuilt:
                                return rebuilt

                        # Verify the executable actually runs (handles missing runtime / bad pick)
                        if not self._verify_executable_works(exe_path):
                            continue

                        self._cached_executable_path = self._normalize_path_for_subprocess(str(exe_path))
                        logging.info(f"Found C# migration tool executable: {self._cached_executable_path}")
                        return self._cached_executable_path
        
        # If no built binary found, try to build the tool
        return self._build_tool_if_needed(tool_dir)
        
    def _build_tool_if_needed(self, tool_dir: Path) -> Optional[str]:
        """Build the C# migration tool if it's not already built."""
        try:
            # Check if dotnet is available
            result = subprocess.run(['dotnet', '--info'],
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
                        # Extract version number from netX.Y format (compatible with older Python)
                        version_str = dirname.replace('net', '', 1) if dirname.startswith('net') else dirname
                        # Split on '.' and convert to tuple of ints for proper comparison
                        version_parts = tuple(int(x) for x in version_str.split('.'))
                        return version_parts
                    except (ValueError, AttributeError):
                        # Fallback to string comparison for non-standard names
                        return (0, 0)  # Put unrecognized versions at the end
                
                target_framework_dirs.sort(key=lambda x: parse_net_version(x.name), reverse=True)
                
                for bin_dir in target_framework_dirs:
                    # Get executable candidates in OS-appropriate priority order
                    candidates = self._get_executable_candidates(bin_dir)
                    
                    for exe_path in candidates:
                        if exe_path.exists():
                            self._cached_executable_path = self._normalize_path_for_subprocess(str(exe_path))
                            logging.info(f"Built and found executable: {self._cached_executable_path}")
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
                cmd = ['dotnet', self._normalize_path_for_subprocess(executable_path)]
            else:
                # Direct executable
                cmd = [self._normalize_path_for_subprocess(executable_path)]
                
            # Add the arguments
            cmd.extend([
                '--rules-file', self._normalize_path_for_subprocess(rules_file_path)
            ])
            
            # Add each target file as a separate argument to avoid command line length limits
            for target_file in target_files:
                cmd.extend(['--target-file', self._normalize_path_for_subprocess(target_file)])
            
            if working_directory:
                cmd.extend(['--working-directory', self._normalize_path_for_subprocess(working_directory)])
                
            return cmd, False
        else:
            # Fall back to dotnet run (which will build if needed)
            logging.warning("No built executable found, falling back to 'dotnet run'")
            cmd = [
                'dotnet', 'run',
                '--project', self._normalize_path_for_subprocess(self.csharp_tool_path),
                '--',
                '--rules-file', self._normalize_path_for_subprocess(rules_file_path)
            ]
            
            # Add each target file as a separate argument
            for target_file in target_files:
                cmd.extend(['--target-file', self._normalize_path_for_subprocess(target_file)])
            
            if working_directory:
                cmd.extend(['--working-directory', self._normalize_path_for_subprocess(working_directory)])
                
            return cmd, True
        
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

        if not self.validate_tool_availability():
            return MigrationResult(
                success=False,
                modified_files=[],
                applied_rules=[],
                errors=["C# migration tool is not available and could not be built"],
                summary="Migration failed: C# migration tool unavailable"
            )

        overall_success = True
        all_modified_files = []
        all_applied_rules = []
        all_errors = []

        # TODO: Implement batching for larger sets of files (e.g., 5 or 10 at a time)
        for target_file in target_files:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as rules_file:
                    json.dump({'rules': migration_rules}, rules_file, indent=2)
                    rules_file_path = rules_file.name

                try:
                    cmd, use_dotnet_run = self._prepare_command(rules_file_path, [target_file], working_directory)

                    if use_dotnet_run:
                        logging.info(f"Using 'dotnet run' for {target_file}: {' '.join(cmd)}")
                    else:
                        logging.info(f"Using pre-built executable for {target_file}: {' '.join(cmd)}")

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,
                        cwd=working_directory
                    )

                    if result.returncode == 0:
                        try:
                            output_data = json.loads(result.stdout)
                            if output_data.get('success', False):
                                all_modified_files.extend(output_data.get('modified_files', []))
                                all_applied_rules.extend(output_data.get('applied_rules', []))
                            else:
                                overall_success = False
                                all_errors.extend(output_data.get('errors', []))
                        except json.JSONDecodeError as e:
                            overall_success = False
                            logging.error(f"Failed to parse C# tool output for {target_file}: {e}")
                            logging.error(f"Tool output: {result.stdout}")
                            all_errors.append(f"Failed to parse tool output for {target_file}: {e}")
                    else:
                        overall_success = False
                        logging.error(f"C# migration tool failed for {target_file} with exit code {result.returncode}")
                        logging.error(f"Tool stderr: {result.stderr}")
                        all_errors.append(f"Tool execution failed for {target_file}: {result.stderr}")

                finally:
                    try:
                        os.unlink(rules_file_path)
                    except Exception as e:
                        logging.warning(f"Failed to clean up temporary rules file: {e}")

            except subprocess.TimeoutExpired:
                overall_success = False
                logging.error(f"C# migration tool timed out for {target_file}")
                all_errors.append(f"Migration tool execution timed out for {target_file}")
            except Exception as e:
                overall_success = False
                logging.error(f"Failed to execute C# migration tool for {target_file}: {e}")
                all_errors.append(f"Execution error for {target_file}: {str(e)}")

        return MigrationResult(
            success=overall_success,
            modified_files=all_modified_files,
            applied_rules=all_applied_rules,
            errors=all_errors,
            summary="Migration process completed for all files."
        )
            
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
