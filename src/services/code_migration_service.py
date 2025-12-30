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
import shutil
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
        self._cached_executable_mtime: Optional[float] = None
        
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

        We treat *any* relevant project input file change as requiring a rebuild.
        """
        try:
            if not tool_dir.exists() or not tool_dir.is_dir():
                return True

            if not executable_path.exists():
                return True

            exe_mtime = executable_path.stat().st_mtime

            ignore_dirs = {'bin', 'obj', '.git'}
            relevant_suffixes = {'.cs', '.csproj', '.props', '.targets'}

            for path in tool_dir.rglob('*'):
                try:
                    if not path.is_file():
                        continue
                    if any(part in ignore_dirs for part in path.parts):
                        continue
                    if path.suffix not in relevant_suffixes:
                        continue
                    if path.stat().st_mtime > exe_mtime:
                        return True
                except OSError:
                    # If a file disappears mid-scan, assume safe rebuild.
                    return True

            return False
        except Exception:
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
        tool_path = Path(self.csharp_tool_path)
        tool_dir = tool_path.parent if tool_path.is_file() else tool_path

        # Return cached path if we already found it, but only if still up-to-date.
        if self._cached_executable_path:
            try:
                cached_path = Path(self._cached_executable_path)
                if cached_path.exists() and not self._is_tool_outdated(tool_dir, cached_path):
                    if self._verify_executable_works(cached_path):
                        return self._cached_executable_path
            except Exception:
                pass
            # Cache is stale/broken; force rediscovery (and rebuild if needed).
            self._cached_executable_path = None
            self._cached_executable_mtime = None
        
        if not tool_dir.exists():
            logging.warning(f"CSharpMigrationTool directory not found: {tool_dir}")
            return None
            
        # Check for built executable in any .NET version
        bin_debug_dir = tool_dir / 'bin' / 'Debug'

        if bin_debug_dir.exists():
            # Find all target framework directories (e.g., net6.0, net7.0, net8.0, net9.0, etc.)
            # Be defensive: tests may patch os.path.exists, and file systems can change.
            try:
                target_framework_dirs = [
                    d for d in bin_debug_dir.iterdir()
                    if d.is_dir() and d.name.startswith('net')
                ]
            except (FileNotFoundError, NotADirectoryError):
                target_framework_dirs = []
            
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
                        try:
                            self._cached_executable_mtime = exe_path.stat().st_mtime
                        except OSError:
                            self._cached_executable_mtime = None
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
                try:
                    target_framework_dirs = [
                        d for d in bin_debug_dir.iterdir()
                        if d.is_dir() and d.name.startswith('net')
                    ]
                except (FileNotFoundError, NotADirectoryError):
                    target_framework_dirs = []
                
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

    @staticmethod
    def extract_search_terms(migration_rules: List[Dict[str, Any]]) -> List[str]:
        """Extract plain-text search terms from migration rules.

        The goal is to quickly pre-filter candidate files before invoking the C# tool.
        We intentionally keep this conservative: it prefers identifier-like strings
        (method/type/namespace names) and ignores obviously non-code values.
        """

        def is_useful_term(value: str) -> bool:
            if not value:
                return False
            if any(ch.isspace() for ch in value):
                return False
            if len(value) < 3 or len(value) > 200:
                return False
            if not any(ch.isalpha() for ch in value):
                return False
            return True

        terms: List[str] = []
        seen = set()

        def add_term(value: Optional[str]):
            if not isinstance(value, str):
                return
            if not is_useful_term(value):
                return
            if value in seen:
                return
            seen.add(value)
            terms.append(value)

        def walk(obj: Any):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    # Prefer known keys first
                    if k in {
                        'method_name',
                        'replacement_method',
                        'containing_type',
                        'containing_namespace',
                        'argument_name',
                        'type_name',
                        'namespace',
                        'old_namespace',
                        'new_namespace',
                        'old_type',
                        'new_type',
                    }:
                        add_term(v)
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        # Only collect from known keys; do not add every string leaf.
        # This keeps the prefilter precise and avoids matching unrelated files.

        walk(migration_rules)
        return terms

    def prefilter_target_files_local(
        self,
        target_files: List[str],
        migration_rules: List[Dict[str, Any]],
        repo_root: str,
        *,
        prefer_ripgrep: bool = True,
        max_patterns_per_call: int = 25,
    ) -> List[str]:
        """Prefilter local files by searching for migration-related terms.

        Uses ripgrep when available for speed; falls back to a Python substring scan.
        Returns a subset of target_files.
        """

        if not target_files:
            return []

        terms = self.extract_search_terms(migration_rules)
        if not terms:
            return target_files

        # Normalize target files to absolute paths for consistent matching.
        repo_root_path = Path(repo_root)
        target_abs = set()
        for file_path in target_files:
            p = Path(file_path)
            if not p.is_absolute():
                p = repo_root_path / p
            target_abs.add(str(p.resolve()))

        rg = shutil.which('rg') if prefer_ripgrep else None
        if rg:
            matched: set[str] = set()

            # Chunk patterns to avoid huge command lines.
            for i in range(0, len(terms), max_patterns_per_call):
                chunk = terms[i:i + max_patterns_per_call]
                cmd = [
                    rg,
                    '-l',
                    '-F',
                ]
                for term in chunk:
                    cmd.extend(['-e', term])
                cmd.extend([
                    '--glob', '*.cs',
                    str(repo_root_path),
                ])

                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(repo_root_path),
                    )
                except Exception:
                    rg = None
                    break

                # rg returns exit code 0 when matches exist, 1 when none.
                if result.returncode in (0, 1):
                    for line in (result.stdout or '').splitlines():
                        if not line:
                            continue
                        p = Path(line)
                        if not p.is_absolute():
                            p = (repo_root_path / p)
                        try:
                            matched.add(str(p.resolve()))
                        except Exception:
                            matched.add(str(p))
                else:
                    # Unexpected error; fall back.
                    rg = None
                    break

            if rg:
                filtered = [p for p in target_abs if p in matched]
                return sorted(filtered)

        grep = shutil.which('grep')
        if grep:
            matched: set[str] = set()

            for i in range(0, len(terms), max_patterns_per_call):
                chunk = terms[i:i + max_patterns_per_call]
                cmd = [
                    grep,
                    '-r',
                    '-l',
                    '-F',
                    '--include=*.cs',
                ]
                for term in chunk:
                    cmd.extend(['-e', term])
                cmd.append(str(repo_root_path))

                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(repo_root_path),
                    )
                except Exception:
                    grep = None
                    break

                # grep returns 0 when matches exist, 1 when none.
                if result.returncode in (0, 1):
                    for line in (result.stdout or '').splitlines():
                        if not line:
                            continue
                        p = Path(line)
                        if not p.is_absolute():
                            p = (repo_root_path / p)
                        try:
                            matched.add(str(p.resolve()))
                        except Exception:
                            matched.add(str(p))
                else:
                    grep = None
                    break

            if grep:
                filtered = [p for p in target_abs if p in matched]
                return sorted(filtered)

        # Fallback: substring scan
        filtered = []
        for abs_path in target_abs:
            try:
                text = Path(abs_path).read_text(encoding='utf-8', errors='ignore', newline='')
            except Exception:
                continue
            if any(term in text for term in terms):
                filtered.append(abs_path)
        return sorted(filtered)
        
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
        all_modified_files: List[str] = []
        all_applied_rules: List[str] = []
        all_errors: List[str] = []

        # Write rules once and execute the tool in batches to reduce process spawn overhead.
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as rules_file:
            json.dump({'rules': migration_rules}, rules_file, indent=2)
            rules_file_path = rules_file.name

        def chunk_files(files: List[str], size: int) -> List[List[str]]:
            return [files[i:i + size] for i in range(0, len(files), size)]

        # Conservative default to avoid command-line length limits on Windows.
        batch_size = 20 if platform.system().lower() == 'windows' else 50

        try:
            for batch in chunk_files(target_files, batch_size):
                try:
                    cmd, use_dotnet_run = self._prepare_command(rules_file_path, batch, working_directory)

                    if use_dotnet_run:
                        logging.info(f"Using 'dotnet run' for {len(batch)} files")
                    else:
                        logging.info(f"Using pre-built executable for {len(batch)} files")

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
                            logging.error(f"Failed to parse C# tool output: {e}")
                            logging.error(f"Tool output: {result.stdout}")
                            all_errors.append(f"Failed to parse tool output: {e}")
                    else:
                        overall_success = False
                        logging.error(f"C# migration tool failed with exit code {result.returncode}")
                        logging.error(f"Tool stderr: {result.stderr}")
                        all_errors.append(f"Tool execution failed: {result.stderr}")

                except subprocess.TimeoutExpired:
                    overall_success = False
                    all_errors.append(f"Migration tool execution timed out for batch of {len(batch)} files")
                except Exception as e:
                    overall_success = False
                    all_errors.append(f"Execution error for batch of {len(batch)} files: {str(e)}")

        finally:
            try:
                os.unlink(rules_file_path)
            except Exception as e:
                logging.warning(f"Failed to clean up temporary rules file: {e}")

        return MigrationResult(
            success=overall_success,
            modified_files=all_modified_files,
            applied_rules=all_applied_rules,
            errors=all_errors,
            summary="Migration process completed."
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
            report_lines.append("Migration completed successfully")
        else:
            report_lines.append("Migration failed")
            
        report_lines.append(f"Summary: {results.summary}")
        report_lines.append("")
        
        if results.applied_rules:
            report_lines.append("Applied Rules:")
            for rule in results.applied_rules:
                report_lines.append(f"  • {rule}")
            report_lines.append("")
            
        if results.modified_files:
            report_lines.append("Modified Files:")
            for file_path in results.modified_files:
                report_lines.append(f"  • {file_path}")
            report_lines.append("")
            
        if results.errors:
            report_lines.append("Errors:")
            for error in results.errors:
                report_lines.append(f"  • {error}")
            report_lines.append("")
            
        return "\n".join(report_lines)
