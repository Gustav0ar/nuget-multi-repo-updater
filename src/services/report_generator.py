from datetime import datetime
from typing import List, Dict, Any, Optional

class ReportGenerator:
    """Service for generating reports."""

    def __init__(self):
        self.report_data = []

    def add_entry(self, repo_name: str, package_name: str, new_version: str, status: str, details: str, migration_info: Optional[Dict[str, Any]] = None, old_version: Optional[str] = None):
        """Add an entry to the report."""
        entry = {
            'repo_name': repo_name,
            'package_name': package_name,
            'new_version': new_version,
            'status': status,
            'details': details,
            'old_version': old_version
        }
        
        if migration_info:
            entry['migration_info'] = migration_info
            
        self.report_data.append(entry)

    def generate(self, output_file: str):
        """Generate the report file."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{output_file}_{timestamp}.md"

        with open(filename, 'w') as f:
            f.write(f"# NuGet Package Update Report\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Generate summary
            self._write_summary(f)

            for entry in self.report_data:
                f.write(f"## Repository: {entry['repo_name']}\n")
                f.write(f"- **Package**: {entry['package_name']}\n")
                if entry.get('old_version'):
                    f.write(f"  - **Version**: {entry['old_version']} → {entry['new_version']}\n")
                else:
                    f.write(f"  - **Version**: {entry['new_version']}\n")
                f.write(f"  - **Status**: {entry['status']}\n")
                f.write(f"  - **Details**: {entry['details']}\n")
                
                # Add migration information if available
                if 'migration_info' in entry:
                    self._write_migration_info(f, entry['migration_info'])
                
                f.write("\n")
        
        return filename
    
    def _write_summary(self, f):
        """Write summary section of the report."""
        total_repos = len(set(entry['repo_name'] for entry in self.report_data))
        total_packages = len(self.report_data)
        
        migration_entries = [entry for entry in self.report_data if 'migration_info' in entry]
        repos_with_migrations = len(set(entry['repo_name'] for entry in migration_entries))
        total_migration_changes = sum(
            len(entry['migration_info'].get('would_modify_files', [])) 
            for entry in migration_entries
        )
        
        f.write("## Summary\n")
        f.write(f"- **Total Repositories**: {total_repos}\n")
        f.write(f"- **Total Package Updates**: {total_packages}\n")
        f.write(f"- **Repositories with Migrations**: {repos_with_migrations}\n")
        f.write(f"- **Total Files with Migration Changes**: {total_migration_changes}\n")
        f.write("\n")
    
    def _write_migration_info(self, f, migration_info: Dict[str, Any]):
        """Write migration information to the report."""
        f.write(f"  - **Migration Analysis**:\n")
        
        would_modify_files = migration_info.get('would_modify_files', [])
        potential_changes = migration_info.get('potential_changes', [])
        applicable_rules = migration_info.get('applicable_rules', [])
        analysis_errors = migration_info.get('analysis_errors', [])
        summary = migration_info.get('summary', '')
        
        if would_modify_files:
            f.write(f"    - **Files that would be modified** ({len(would_modify_files)}):\n")
            for file_path in would_modify_files:
                f.write(f"      - `{file_path}`\n")
        
        if applicable_rules:
            f.write(f"    - **Applicable migration rules** ({len(applicable_rules)}):\n")
            for rule in applicable_rules:
                f.write(f"      - {rule}\n")
        
        if potential_changes:
            f.write(f"    - **Code Changes Preview** ({len(potential_changes)} changes):\n")
            for i, change in enumerate(potential_changes, 1):
                file_path = change.get('file', 'Unknown file')
                line_num = change.get('line', 'Unknown line')
                rule_name = change.get('rule', 'Unknown rule')
                original = change.get('original', '')
                replacement = change.get('replacement', '')
                
                f.write(f"      **Change {i}: {rule_name}**\n")
                f.write(f"      - **File**: `{file_path}` (line {line_num})\n")
                
                if original and replacement:
                    f.write(f"      - **Before**:\n")
                    f.write(f"        ```csharp\n")
                    f.write(f"        {original}\n")
                    f.write(f"        ```\n")
                    f.write(f"      - **After**:\n")
                    f.write(f"        ```csharp\n")
                    f.write(f"        {replacement}\n")
                    f.write(f"        ```\n")
                elif change.get('description'):
                    f.write(f"      - **Description**: {change.get('description')}\n")
                
                f.write(f"\n")
        
        if analysis_errors:
            f.write(f"    - **Analysis errors** ({len(analysis_errors)}):\n")
            for error in analysis_errors:
                f.write(f"      - {error}\n")
        
        if summary:
            f.write(f"    - **Summary**: {summary}\n")
