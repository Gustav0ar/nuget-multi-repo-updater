"""
Dry run simulation service for previewing package update operations.
"""
import logging
import sys
import re
import os
from typing import List, Dict, Any
from packaging.version import parse as parse_version

from src.providers.scm_provider import ScmProvider
from src.services.report_generator import ReportGenerator
from src.services.dry_run_code_migration_service import DryRunCodeMigrationService
from src.services.migration_configuration_service import MigrationConfigurationService


class DryRunService:
    """Handles dry run simulations of package update operations."""

    def __init__(self, scm_provider: ScmProvider, migration_config_service: MigrationConfigurationService = None):
        self.scm_provider = scm_provider
        self.migration_config_service = migration_config_service
        self.migration_service = DryRunCodeMigrationService("./CSharpMigrationTool")

    def simulate_package_updates(self, repositories: List[Dict], packages_to_update: List[Dict],
                                allow_downgrade: bool = False, report_file: str = None, use_local_clone: bool = False) -> None:
        """Simulate the entire package update process without making changes."""
        print(f"\n{'='*80}")
        print("DRY RUN MODE - SIMULATION REPORT")
        print(f"{'='*80}")
        print(f"The following operations would be performed:")
        print(f"Total repositories to process: {len(repositories)}")
        print(f"Packages to update: {', '.join([f'{p['name']}@{p['version']}' for p in packages_to_update])}")
        print()

        # Create a dry-run report generator
        dry_run_report = ReportGenerator()
        dry_run_summary = {
            'total_repos': 0,
            'would_create_mrs': 0,
            'existing_mrs': 0,
            'no_changes': 0,
            'errors': 0,
            'total_files_to_modify': 0,
            'total_migration_files': 0,
            'migration_errors': 0
        }

        for repo in repositories:
            self._simulate_repository_processing(
                repo, packages_to_update, allow_downgrade, dry_run_report, dry_run_summary, use_local_clone
            )

        self._print_dry_run_summary(dry_run_summary, dry_run_report, report_file)
        # Allow tests to disable exit behavior
        if not hasattr(self, '_disable_exit') or not self._disable_exit:
            sys.exit(0)

    def perform_local_dry_run(self, repositories: List[Dict], packages_to_update: List[Dict], 
                            args: Any, migration_config_service: MigrationConfigurationService,
                            enable_migrations: bool) -> None:
        """Perform a dry run by cloning locally and applying changes without pushing."""
        from src.actions.multi_package_update_action import MultiPackageUpdateAction
        from src.services.git_service import GitService
        
        print(f"\n{'='*80}")
        print("LOCAL DRY RUN MODE - CLONE & APPLY")
        print(f"{'='*80}")
        print(f"The following operations will be performed locally:")
        print(f"Total repositories to process: {len(repositories)}")
        print(f"Packages to update: {', '.join([f'{p['name']}@{p['version']}' for p in packages_to_update])}")
        if enable_migrations:
            print(f"Code migration: Enabled")
        else:
            print(f"Code migration: Disabled")
        print()

        git_service = GitService()
        
        for repo in repositories:
            print(f"\n{'-'*60}")
            print(f"🔍 Processing: {repo['name']} ({repo['path_with_namespace']})")
            
            try:
                action = MultiPackageUpdateAction(
                    git_service=git_service,
                    scm_provider=self.scm_provider,
                    packages=packages_to_update,
                    allow_downgrade=args.allow_downgrade,
                    use_local_clone=True,
                    migration_config_service=migration_config_service,
                    enable_migrations=enable_migrations,
                    strict_migration_mode=getattr(args, 'strict_migration_mode', False),
                    dry_run=True
                )
                
                target_branch = repo.get('target_branch', repo['default_branch'])
                result = action.execute(repo['ssh_url_to_repo'], str(repo['id']), target_branch)
                
                if result:
                    self._print_local_dry_run_result(result)
                else:
                    print("❌ Failed to process repository (check logs)")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                logging.error(f"Local dry run failed for {repo['id']}: {e}")

        # Allow tests to disable exit behavior
        if not hasattr(self, '_disable_exit') or not self._disable_exit:
            sys.exit(0)

    def _print_local_dry_run_result(self, result: Dict) -> None:
        """Print the result of a local dry run."""
        package_result = result.get('package_result', {})
        migration_result = result.get('migration_result', {})
        
        print("\n   ✅ Changes applied successfully (Dry Run)")
        
        if package_result.get('updated_packages'):
            print(f"   📦 Updated Packages ({len(package_result['updated_packages'])}):")
            for pkg in package_result['updated_packages']:
                print(f"      - {pkg['name']} to {pkg['version']}")
        
        if migration_result and migration_result.get('applied_rules'):
            print(f"   🛠️  Applied Migration Rules ({len(migration_result['applied_rules'])}):")
            for rule in migration_result['applied_rules']:
                print(f"      - {rule}")
        
        # Combine modified files from both package updates and migrations
        modified_files = set(package_result.get('modified_files', []) or [])
        if migration_result:
            modified_files.update(migration_result.get('modified_files', []) or [])
            
        if modified_files:
            print(f"   📝 Modified Files ({len(modified_files)}):")
            for file in sorted(modified_files):
                print(f"      - {file}")

    def _simulate_repository_processing(self, repo: Dict, packages_to_update: List[Dict],
                                      allow_downgrade: bool, dry_run_report: ReportGenerator,
                                      dry_run_summary: Dict[str, int], use_local_clone: bool = False) -> None:
        """Simulate processing a single repository."""
        # Handle both repository objects and IDs
        if isinstance(repo, dict):
            project = repo
        else:
            project = self.scm_provider.get_project(repo)

        if not project:
            print(f"❌ Repository not found: {repo}")
            dry_run_summary['errors'] += 1
            return

        # Use target_branch if available, otherwise fall back to default_branch
        target_branch = project.get('target_branch', project['default_branch'])

        print(f"\n{'-'*60}")
        print(f"🔍 Analyzing: {project['name']} ({project['path_with_namespace']})")
        print(f"   Default Branch: {project['default_branch']}")
        if target_branch != project['default_branch']:
            print(f"   Target Branch: {target_branch} (using most recent branch)")
        print(f"   Repository URL: {project['http_url_to_repo']}")

        # Process all packages together in single transaction (matches actual execution)
        self._simulate_multi_package_transaction(
            project, packages_to_update, allow_downgrade, dry_run_report, dry_run_summary, use_local_clone
        )

    def _simulate_package_processing(self, project: Dict, package_info: Dict,
                                   allow_downgrade: bool, dry_run_report: ReportGenerator,
                                   dry_run_summary: Dict[str, int]) -> None:
        """Simulate processing a single package in a repository."""
        package_name = package_info['name']
        new_version = package_info['version']

        # Use target_branch if available, otherwise fall back to default_branch
        target_branch = project.get('target_branch', project['default_branch'])

        print(f"\n   📦 Package: {package_name} → {new_version}")

        # Check for existing merge request
        mr_title = f"Update {package_name} to version {new_version}"
        try:
            existing_mr = self.scm_provider.check_existing_merge_request(
                project['id'], mr_title, target_branch=target_branch
            )

            if existing_mr:
                print(f"   ✅ Existing MR found: {existing_mr['web_url']}")
                print(f"      Status: {existing_mr.get('state', 'unknown')}")
                dry_run_summary['existing_mrs'] += 1
                dry_run_report.add_entry(
                    project['name'], package_name, new_version,
                    'Existing MR', f"Would skip - MR exists: {existing_mr['web_url']}"
                )
                return
        except Exception as e:
            print(f"   ⚠️  Error checking existing MR: {e}")

        # Simulate repository analysis (without cloning)
        print(f"   🔄 Would clone repository to: ./temp/{project['name']}")
        print(f"   🌿 Would create branch: update-{package_name.lower().replace('.', '-')}-to-{new_version.replace('.', '_')}")

        # Simulate .csproj file analysis and migration analysis
        migration_info = self._simulate_csproj_and_migration_analysis(
            project, package_name, new_version, allow_downgrade,
            dry_run_report, dry_run_summary
        )

    def _simulate_csproj_and_migration_analysis(self, project: Dict, package_name: str, new_version: str,
                                              allow_downgrade: bool, dry_run_report: ReportGenerator,
                                              dry_run_summary: Dict[str, int]) -> Dict[str, Any]:
        """Simulate .csproj file analysis and migration rule analysis."""
        print(f"   📄 Would scan for .csproj files...")
        migration_info = None

        # Use target_branch if available, otherwise fall back to default_branch
        target_branch = project.get('target_branch', project['default_branch'])

        # Try to get repository tree to find .csproj files
        try:
            tree = self.scm_provider.get_repository_tree(project['id'], ref=target_branch)
            if tree:
                csproj_files = [item['path'] for item in tree
                              if item['type'] == 'blob' and item['path'].endswith('.csproj')]
                cs_files = [item['path'] for item in tree
                           if item['type'] == 'blob' and item['path'].endswith('.cs')]

                if csproj_files:
                    print(f"   📋 Found {len(csproj_files)} .csproj files and {len(cs_files)} .cs files")
                    
                    # Analyze .csproj files for package updates
                    old_versions = self._analyze_csproj_files(
                        project, csproj_files, package_name, new_version, allow_downgrade
                    )
                    files_would_modify = len(old_versions)

                    # Analyze potential migrations
                    migration_info = self._analyze_potential_migrations(
                        project, package_name, new_version, cs_files, dry_run_summary
                    )

                    dry_run_summary['total_files_to_modify'] += files_would_modify

                    if files_would_modify > 0 or (migration_info and migration_info.get('would_modify_files')):
                        total_changes = files_would_modify + len(migration_info.get('would_modify_files', []))
                        self._print_would_create_mr(project, package_name, new_version, total_changes)
                        dry_run_summary['would_create_mrs'] += 1
                        
                        details = f"Would modify {files_would_modify} .csproj files"
                        if migration_info and migration_info.get('would_modify_files'):
                            details += f" and {len(migration_info['would_modify_files'])} code files"
                        
                        old_version_str = ', '.join(list(set(old_versions))) if old_versions else None
                        dry_run_report.add_entry(
                            project['name'], package_name, new_version,
                            'Would Create MR', details, migration_info, old_version=old_version_str,
                            target_branch=target_branch
                        )
                    else:
                        print(f"   ➖ No changes needed")
                        dry_run_summary['no_changes'] += 1
                        dry_run_report.add_entry(
                            project['name'], package_name, new_version,
                            'No Changes', 'Package not found or already at correct version',
                            target_branch=target_branch
                        )
                else:
                    print(f"   ❌ No .csproj files found")
                    dry_run_summary['no_changes'] += 1
                    dry_run_report.add_entry(
                        project['name'], package_name, new_version,
                        'No Changes', 'No .csproj files found in repository',
                        target_branch=target_branch
                    )
        except Exception as e:
            print(f"   ❌ Error analyzing repository: {e}")
            dry_run_summary['errors'] += 1
            dry_run_report.add_entry(
                project['name'], package_name, new_version,
                'Error', f"Failed to analyze repository: {str(e)}",
                target_branch=target_branch
            )

        return migration_info

    def _analyze_potential_migrations(self, project: Dict, package_name: str, new_version: str,
                                    cs_files: list, dry_run_summary: Dict[str, int]) -> Dict[str, Any]:
        """Analyze potential code migrations for the package update."""
        try:
            # Get migration rules for this package
            migration_rules = []
            if self.migration_config_service:
                # Get applicable migrations for this package version upgrade
                applicable_migrations = self.migration_config_service.get_applicable_migrations(
                    package_name, "0.0.0", new_version  # From any version to new version
                )
                
                # Convert to rules format
                for migration in applicable_migrations:
                    for rule in migration.rules:
                        migration_rules.append(rule.to_dict())
            
            # If no migrations found, return early
            if not migration_rules:
                print(f"   ➖ No migration rules applicable")
                return {
                    'has_migrations': False,
                    'rules_applied': [],
                    'would_modify_files': []
                }
            
            # Analyze potential migrations
            migration_result = self.migration_service.analyze_potential_migrations(
                target_files=cs_files, 
                migration_rules=migration_rules
            )
            
            # Convert result to expected format
            migration_info = {
                'has_migrations': len(migration_result.applicable_rules) > 0,
                'rules_applied': migration_result.applicable_rules,
                'would_modify_files': migration_result.would_modify_files,
                'potential_changes': migration_result.potential_changes,
                'analysis_errors': migration_result.analysis_errors,
                'summary': migration_result.summary
            }
            
            if migration_info and migration_info.get('has_migrations'):
                print(f"   🔧 Found {len(migration_info.get('rules_applied', []))} migration rules")
                files_to_modify = migration_info.get('would_modify_files', [])
                potential_changes = migration_info.get('potential_changes', [])
                
                if files_to_modify:
                    print(f"   📝 Would modify {len(files_to_modify)} code files for migrations")
                    dry_run_summary['total_migration_files'] += len(files_to_modify)
                    
                    for file_path in files_to_modify[:3]:  # Show first 3 files
                        print(f"      • {file_path}")
                    if len(files_to_modify) > 3:
                        print(f"      • ... and {len(files_to_modify) - 3} more files")
                
                # Show code change preview
                if potential_changes:
                    print(f"   🔍 Code changes preview (first {min(2, len(potential_changes))} changes):")
                    for i, change in enumerate(potential_changes[:2], 1):
                        file_path = change.get('file', 'Unknown file')
                        line_num = change.get('line', '?')
                        rule_name = change.get('rule', 'Unknown rule')
                        original = change.get('original', '')
                        replacement = change.get('replacement', '')
                        
                        print(f"      Change {i} - {rule_name}")
                        print(f"         File: {file_path}:{line_num}")
                        if original and replacement:
                            # Truncate long lines for console display
                            original_short = original[:60] + "..." if len(original) > 60 else original
                            replacement_short = replacement[:60] + "..." if len(replacement) > 60 else replacement
                            print(f"         Before: {original_short}")
                            print(f"         After:  {replacement_short}")
                    
                    if len(potential_changes) > 2:
                        print(f"      ... and {len(potential_changes) - 2} more changes (see report for details)")
                
                if not files_to_modify:
                    print(f"   ℹ️  Migration rules found but no files would be modified")
            else:
                print(f"   ➖ No migration rules applicable")
                
            return migration_info
            
        except Exception as e:
            print(f"   ⚠️  Error analyzing migrations: {e}")
            dry_run_summary['migration_errors'] += 1
            return {
                'has_migrations': False,
                'error': str(e),
                'rules_applied': [],
                'would_modify_files': []
            }

    def _analyze_csproj_files(self, project: Dict, csproj_files: List[str],
                            package_name: str, new_version: str, allow_downgrade: bool) -> List[str]:
        """Analyze .csproj files and return a list of old versions that would be modified."""
        versions_found = []

        # Use target_branch if available, otherwise fall back to default_branch
        target_branch = project.get('target_branch', project['default_branch'])

        for csproj_path in csproj_files:
            print(f"      • {csproj_path}")

            # Try to get file content and check if package exists
            try:
                content = self.scm_provider.get_file_content(
                    project['id'], csproj_path, target_branch
                )
                if content:
                    # Simulate package version check
                    pattern = rf'<PackageReference\s+Include="{re.escape(package_name)}"\s+Version="([^"]*)"'
                    multiline_pattern = rf'<PackageReference\s+Include="{re.escape(package_name)}"\s*>\s*<Version>([^<]*)</Version>'

                    match = re.search(pattern, content, re.IGNORECASE)
                    if not match:
                        match = re.search(multiline_pattern, content, re.IGNORECASE | re.DOTALL)

                    if match:
                        old_version = match.group(1)
                        if old_version == new_version:
                            print(f"        ✓ Already at version {new_version}")
                        else:
                            # Check for downgrade
                            try:
                                if not allow_downgrade and parse_version(new_version) < parse_version(old_version):
                                    print(f"        ⚠️  Would skip downgrade: {old_version} → {new_version}")
                                else:
                                    print(f"        🔄 Would update: {old_version} → {new_version}")
                                    versions_found.append(old_version)
                            except:
                                print(f"        🔄 Would update: {old_version} → {new_version}")
                                versions_found.append(old_version)
                    else:
                        print(f"        ➖ Package not found in this file")
            except Exception as e:
                print(f"        ⚠️  Could not analyze file: {e}")

        return versions_found

    def _print_would_create_mr(self, project: Dict, package_name: str, new_version: str,
                             files_would_modify: int) -> None:
        """Print what would happen when creating a merge request."""
        # Use target_branch if available, otherwise fall back to default_branch
        target_branch = project.get('target_branch', project['default_branch'])
        
        print(f"   ✅ Would modify {files_would_modify} files")
        print(f"   📝 Would commit changes with message: 'Update {package_name} to version {new_version}'")
        print(f"   🚀 Would push branch to origin")
        print(f"   🔀 Would create merge request:")
        print(f"      Title: Update {package_name} to version {new_version}")
        print(f"      Target: {target_branch}")
        print(f"      Source: update-{package_name.lower().replace('.', '-')}-to-{new_version.replace('.', '_')}")

    def _print_dry_run_summary(self, dry_run_summary: Dict[str, int],
                             dry_run_report: ReportGenerator, report_file: str = None) -> None:
        """Print the dry run summary."""
        print(f"\n{'='*80}")
        print("DRY RUN SUMMARY")
        print(f"{'='*80}")
        print(f"📊 Total repositories analyzed: {dry_run_summary['total_repos']}")
        print(f"🆕 Would create new MRs: {dry_run_summary['would_create_mrs']}")
        print(f"♻️  Existing MRs found: {dry_run_summary['existing_mrs']}")
        print(f"➖ No changes needed: {dry_run_summary['no_changes']}")
        print(f"❌ Errors encountered: {dry_run_summary['errors']}")
        print(f"📝 Total files that would be modified: {dry_run_summary['total_files_to_modify']}")
        
        # Migration-specific statistics
        if dry_run_summary.get('total_migration_files', 0) > 0:
            print(f"🔧 Code files that would be migrated: {dry_run_summary['total_migration_files']}")
        if dry_run_summary.get('migration_errors', 0) > 0:
            print(f"⚠️  Migration analysis errors: {dry_run_summary['migration_errors']}")

        # Generate dry run report if requested
        if report_file and isinstance(report_file, str):
            report_filename = dry_run_report.generate_markdown_report(report_file)
            print(f"\n📄 Dry run report saved to: {report_filename}")

        print(f"\n💡 To execute these changes, run the same command without --dry-run")
        print(f"{'='*80}")

    def _simulate_multi_package_transaction(self, project: Dict, packages_to_update: List[Dict],
                                          allow_downgrade: bool, dry_run_report: ReportGenerator,
                                          dry_run_summary: Dict[str, int], use_local_clone: bool = False) -> None:
        """Simulate processing multiple packages as single transaction (matches actual execution)."""
        # Generate single branch and MR title for all packages (same as MultiPackageUpdateAction)
        if len(packages_to_update) == 1:
            package_name = packages_to_update[0]['name'].lower().replace('.', '-')
            version = packages_to_update[0]['version'].replace('.', '_')
            branch_name = f"update-{package_name}-to-{version}"
            mr_title = f"Update {packages_to_update[0]['name']} to version {packages_to_update[0]['version']}"
        else:
            import time
            timestamp = int(time.time())
            package_names = "-".join([pkg['name'].split('.')[-1].lower() for pkg in packages_to_update[:2]])
            branch_name = f"update-{package_names}-{timestamp}"
            mr_title = f"Update {len(packages_to_update)} NuGet packages"
        
        print(f"\n   📦 Packages: {', '.join([f'{p['name']}@{p['version']}' for p in packages_to_update])}")

        # Use target_branch if available, otherwise fall back to default_branch
        target_branch = project.get('target_branch', project['default_branch'])

        # Check for existing MR for the combined update
        try:
            existing_mr = self.scm_provider.check_existing_merge_request(
                project['id'], mr_title, target_branch=target_branch
            )
            if existing_mr:
                print(f"   ✅ Existing MR found: {existing_mr['web_url']}")
                print(f"      Status: {existing_mr.get('state', 'unknown')}")
                dry_run_summary['existing_mrs'] += 1
                return
        except Exception as e:
            print(f"   ⚠️  Error checking existing MR: {e}")

        # Simulate single transaction workflow
        if use_local_clone:
            print(f"   🔄 Would clone repository to: ./temp/{project['name']}")
        else:
            print(f"   🔄 Would use GitLab API to access repository content")
        print(f"   🌿 Would create branch: {branch_name}")
        print(f"   📄 Would scan for .csproj files...")
        
        # Simulate finding files and analyzing packages together
        try:
            tree = self.scm_provider.get_repository_tree(project['id'], ref=target_branch)
            if tree:
                csproj_files = [item['path'] for item in tree if item['type'] == 'blob' and item['path'].endswith('.csproj')]
                cs_files = [item['path'] for item in tree if item['type'] == 'blob' and item['path'].endswith('.cs')]
                
                if csproj_files:
                    print(f"   📋 Found {len(csproj_files)} .csproj files and {len(cs_files)} .cs files")
                    
                    # Simulate analyzing all packages together
                    total_modified_files = 0
                    has_migrations = False
                    all_migration_info = {}
                    all_old_versions = {}
                    
                    for package_info in packages_to_update:
                        # Simulate package analysis
                        old_versions = self._analyze_csproj_files(
                            project, csproj_files, package_info['name'], package_info['version'], allow_downgrade
                        )
                        if old_versions:
                            all_old_versions[package_info['name']] = list(set(old_versions))
                        
                        total_modified_files += len(old_versions)
                        
                        # Simulate migration analysis
                        migration_info = self._analyze_potential_migrations(
                            project, package_info['name'], package_info['version'], cs_files, dry_run_summary
                        )
                        if migration_info and migration_info.get('has_migrations'):
                            has_migrations = True
                            all_migration_info[package_info['name']] = migration_info

                    # Simulate the two-commit workflow
                    if total_modified_files > 0 or has_migrations:
                        print(f"   ✅ Would modify {total_modified_files} files")
                        
                        # Commit 1: Package updates
                        if len(packages_to_update) == 1:
                            package_commit = f"Update {packages_to_update[0]['name']} to version {packages_to_update[0]['version']}"
                        else:
                            package_list = ", ".join([f"{pkg['name']} to {pkg['version']}" for pkg in packages_to_update])
                            package_commit = f"Update {len(packages_to_update)} packages: {package_list}"
                        print(f"   📝 Would commit package updates with message: '{package_commit}'")
                        
                        # Commit 2: Migrations (if applicable)
                        if has_migrations:
                            print(f"   🔧 Would commit migrations with message: 'Apply code migrations for updated packages'")
                        
                        print(f"   🚀 Would push branch to origin")
                        print(f"   🔀 Would create merge request:")
                        print(f"      Title: {mr_title}")
                        print(f"      Target: {target_branch}")
                        print(f"      Source: {branch_name}")

                        # Update summary
                        dry_run_summary['would_create_mrs'] += 1
                        dry_run_summary['total_files_to_modify'] += total_modified_files
                        
                        # Add report entries
                        for package_info in packages_to_update:
                            # Get migration info for this specific package
                            package_migration_info = all_migration_info.get(package_info['name'])
                            package_old_versions = all_old_versions.get(package_info['name'])
                            old_version_str = ', '.join(package_old_versions) if package_old_versions else None
                            
                            dry_run_report.add_entry(
                                project['name'], package_info['name'], package_info['version'],
                                'Would Create MR', f"Single transaction with {len(packages_to_update)} packages",
                                package_migration_info,
                                old_version=old_version_str,
                                target_branch=target_branch
                            )
                    else:
                        print(f"   ➖ No changes needed")
                        dry_run_summary['no_changes'] += 1
                else:
                    print(f"   ➖ No .csproj files found")
                    dry_run_summary['no_changes'] += 1
        except Exception as e:
            print(f"   ❌ Error analyzing repository: {e}")
            dry_run_summary['errors'] += 1
