"""
Dry run simulation service for previewing package update operations.
"""
import logging
import sys
import re
from typing import List, Dict, Any
from packaging.version import parse as parse_version

from src.providers.scm_provider import ScmProvider
from src.services.report_generator import ReportGenerator


class DryRunService:
    """Handles dry run simulations of package update operations."""

    def __init__(self, scm_provider: ScmProvider):
        self.scm_provider = scm_provider

    def simulate_package_updates(self, repositories: List[Dict], packages_to_update: List[Dict],
                                allow_downgrade: bool = False, report_file: str = None) -> None:
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
            'total_repos': len(repositories),
            'would_create_mrs': 0,
            'existing_mrs': 0,
            'no_changes': 0,
            'errors': 0,
            'total_files_to_modify': 0
        }

        for repo in repositories:
            self._simulate_repository_processing(
                repo, packages_to_update, allow_downgrade, dry_run_report, dry_run_summary
            )

        self._print_dry_run_summary(dry_run_summary, dry_run_report, report_file)
        sys.exit(0)

    def _simulate_repository_processing(self, repo: Dict, packages_to_update: List[Dict],
                                      allow_downgrade: bool, dry_run_report: ReportGenerator,
                                      dry_run_summary: Dict[str, int]) -> None:
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

        print(f"\n{'─'*60}")
        print(f"🔍 Analyzing: {project['name']} ({project['path_with_namespace']})")
        print(f"   Default Branch: {project['default_branch']}")
        print(f"   Repository URL: {project['http_url_to_repo']}")

        for package_info in packages_to_update:
            self._simulate_package_processing(
                project, package_info, allow_downgrade, dry_run_report, dry_run_summary
            )

    def _simulate_package_processing(self, project: Dict, package_info: Dict,
                                   allow_downgrade: bool, dry_run_report: ReportGenerator,
                                   dry_run_summary: Dict[str, int]) -> None:
        """Simulate processing a single package in a repository."""
        package_name = package_info['name']
        new_version = package_info['version']

        print(f"\n   📦 Package: {package_name} → {new_version}")

        # Check for existing merge request
        mr_title = f"Update {package_name} to version {new_version}"
        try:
            existing_mr = self.scm_provider.check_existing_merge_request(
                project['id'], mr_title, target_branch=project['default_branch']
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

        # Simulate .csproj file analysis
        self._simulate_csproj_analysis(
            project, package_name, new_version, allow_downgrade,
            dry_run_report, dry_run_summary
        )

    def _simulate_csproj_analysis(self, project: Dict, package_name: str, new_version: str,
                                allow_downgrade: bool, dry_run_report: ReportGenerator,
                                dry_run_summary: Dict[str, int]) -> None:
        """Simulate .csproj file analysis."""
        print(f"   📄 Would scan for .csproj files...")

        # Try to get repository tree to find .csproj files
        try:
            tree = self.scm_provider.get_repository_tree(project['id'], ref=project['default_branch'])
            if tree:
                csproj_files = [item['path'] for item in tree
                              if item['type'] == 'blob' and item['path'].endswith('.csproj')]

                if csproj_files:
                    print(f"   📋 Found {len(csproj_files)} .csproj files:")
                    files_would_modify = self._analyze_csproj_files(
                        project, csproj_files, package_name, new_version, allow_downgrade
                    )

                    dry_run_summary['total_files_to_modify'] += files_would_modify

                    if files_would_modify > 0:
                        self._print_would_create_mr(project, package_name, new_version, files_would_modify)
                        dry_run_summary['would_create_mrs'] += 1
                        dry_run_report.add_entry(
                            project['name'], package_name, new_version,
                            'Would Create MR', f"Would modify {files_would_modify} files"
                        )
                    else:
                        print(f"   ➖ No changes needed")
                        dry_run_summary['no_changes'] += 1
                        dry_run_report.add_entry(
                            project['name'], package_name, new_version,
                            'No Changes', 'Package not found or already at correct version'
                        )
                else:
                    print(f"   ❌ No .csproj files found")
                    dry_run_summary['no_changes'] += 1
                    dry_run_report.add_entry(
                        project['name'], package_name, new_version,
                        'No .csproj Files', 'Repository contains no .csproj files'
                    )
            else:
                print(f"   ❌ Could not access repository tree")
                dry_run_summary['errors'] += 1
        except Exception as e:
            print(f"   ❌ Error analyzing repository: {e}")
            dry_run_summary['errors'] += 1
            dry_run_report.add_entry(
                project['name'], package_name, new_version,
                'Error', f"Could not analyze repository: {e}"
            )

    def _analyze_csproj_files(self, project: Dict, csproj_files: List[str],
                            package_name: str, new_version: str, allow_downgrade: bool) -> int:
        """Analyze .csproj files and return count of files that would be modified."""
        files_would_modify = 0

        for csproj_path in csproj_files:
            print(f"      • {csproj_path}")

            # Try to get file content and check if package exists
            try:
                content = self.scm_provider.get_file_content(
                    project['id'], csproj_path, project['default_branch']
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
                                    files_would_modify += 1
                            except:
                                print(f"        🔄 Would update: {old_version} → {new_version}")
                                files_would_modify += 1
                    else:
                        print(f"        ➖ Package not found in this file")
            except Exception as e:
                print(f"        ⚠️  Could not analyze file: {e}")

        return files_would_modify

    def _print_would_create_mr(self, project: Dict, package_name: str, new_version: str,
                             files_would_modify: int) -> None:
        """Print what would happen when creating a merge request."""
        print(f"   ✅ Would modify {files_would_modify} files")
        print(f"   📝 Would commit changes with message: 'Update {package_name} to version {new_version}'")
        print(f"   🚀 Would push branch to origin")
        print(f"   🔀 Would create merge request:")
        print(f"      Title: Update {package_name} to version {new_version}")
        print(f"      Target: {project['default_branch']}")
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

        # Generate dry run report if requested
        if report_file and isinstance(report_file, str):
            report_filename = dry_run_report.generate(report_file)
            print(f"\n📄 Dry run report saved to: {report_filename}")

        print(f"\n💡 To execute these changes, run the same command without --dry-run")
        print(f"{'='*80}")
