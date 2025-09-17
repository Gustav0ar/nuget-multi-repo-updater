"""
Enhanced action to update multiple NuGet packages and execute code migrations with rollback support.
"""
import logging
import tempfile
import os
import json
from typing import List, Dict, Optional

from src.core.action import Action
from src.core.repository_strategy import RepositoryStrategy
from src.core.package_file_updater import PackageFileUpdater
from src.services.git_service import GitService
from src.providers.scm_provider import ScmProvider
from src.strategies.local_clone_strategy import LocalCloneStrategy
from src.strategies.api_strategy import ApiStrategy
from src.services.rollback_service import RepositoryUpdateTransaction, TransactionException
from src.services.migration_configuration_service import MigrationConfigurationService
from src.services.code_migration_service import CodeMigrationService, MigrationResult


class MultiPackageUpdateAction(Action):
    """Enhanced action to update multiple NuGet packages and execute code migrations with rollback support."""

    def __init__(self, git_service: GitService, scm_provider: ScmProvider, packages: List[Dict[str, str]],
                 allow_downgrade: bool = False, use_local_clone: bool = False, 
                 migration_config_service: Optional[MigrationConfigurationService] = None,
                 enable_migrations: bool = False, strict_migration_mode: bool = False):
        self.git_service = git_service
        self.scm_provider = scm_provider
        self.packages = packages  # List of {'name': package_name, 'version': new_version, 'migration_rule': optional}
        self.allow_downgrade = allow_downgrade
        self.use_local_clone = use_local_clone
        self.migration_config_service = migration_config_service
        self.enable_migrations = enable_migrations
        self.strict_migration_mode = strict_migration_mode

        self.strategy: RepositoryStrategy = self._create_strategy()

    def _create_strategy(self) -> RepositoryStrategy:
        """Create the appropriate repository strategy based on configuration."""
        if self.use_local_clone:
            return LocalCloneStrategy(self.git_service, self.scm_provider)
        else:
            return ApiStrategy(self.scm_provider)

    def execute(self, repo_url: str, repo_id: str, default_branch: str) -> Optional[Dict]:
        """Execute the action with comprehensive rollback support."""
        transaction = RepositoryUpdateTransaction(repo_id, self.strategy)
        self.strategy.set_transaction(transaction)
        
        try:
            package_names = [pkg['name'] for pkg in self.packages]
            logging.info(f"Processing repository {repo_url or repo_id} for packages {package_names} using {'local clone' if self.use_local_clone else 'API'} strategy")

            # Check for existing merge request
            mr_title = self._generate_mr_title()
            existing_mr = self.scm_provider.check_existing_merge_request(
                repo_id, mr_title, target_branch=default_branch
            )

            if existing_mr:
                logging.info(f"Merge request already exists for package updates in repository {repo_id}: {existing_mr['web_url']}")
                return existing_mr

            # Step 1: Prepare repository
            if not self.strategy.prepare_repository(repo_url, repo_id):
                logging.error(f"Failed to prepare repository {repo_url or repo_id}")
                return None

            # Step 2: Find target files
            target_files = self.strategy.find_target_files(repo_id, '.csproj', default_branch)
            if not target_files:
                logging.info(f"No .csproj files found in repository {repo_id}")
                return None

            # Step 3: Create branch
            branch_name = self._generate_branch_name()
            if not self.strategy.create_branch(repo_id, branch_name, default_branch):
                logging.error(f"Failed to create branch {branch_name}")
                return None

            # Step 4: Execute package updates (Commit 1)
            package_result = self._execute_package_updates(repo_id, target_files, branch_name, default_branch)
            if not package_result['success']:
                logging.error("Package updates failed")
                return None

            # Step 5: Execute code migrations if applicable (Commit 2)
            migration_result = None
            if self.enable_migrations and self._has_applicable_migrations(package_result['updated_packages']):
                migration_result = self._execute_code_migrations(
                    repo_id, package_result['updated_packages'], branch_name, default_branch
                )
                
                # If migrations fail in strict mode, rollback everything
                if not migration_result.success and self.strict_migration_mode:
                    logging.error("Migration failed in strict mode, rolling back everything")
                    raise Exception("Migration failed in strict mode")

            # Step 6: Push changes and create merge request
            if self.use_local_clone:
                if not self.strategy.push_changes(branch_name):
                    raise Exception("Failed to push changes to remote")

            mr_result = self._create_merge_request_with_both_commits(
                repo_id, branch_name, default_branch, package_result, migration_result
            )

            if not mr_result:
                logging.error("Failed to create merge request")
                return None

            # Success! Clear rollback actions since everything worked
            transaction.clear_rollback_actions()
            
            # Add migration information to result
            if migration_result:
                mr_result['migration_result'] = migration_result.to_dict()
                
            return mr_result

        except Exception as e:
            logging.error(f"Repository update failed for {repo_id}: {e}")
            rollback_result = transaction.execute_rollback()
            
            # Create a TransactionException with rollback information
            raise TransactionException(f"Repository update failed: {e}", rollback_result)

    def _execute_package_updates(self, repo_id: str, target_files: List[str], 
                               branch_name: str, default_branch: str) -> Dict:
        """Execute package updates and create first commit."""
        modified_files, updated_packages = self._process_all_packages_in_files(
            repo_id, target_files, branch_name, default_branch
        )

        if not modified_files:
            return {'success': False, 'updated_packages': [], 'modified_files': []}

        # For local strategy, commit changes; for API strategy, files are already committed
        if self.use_local_clone:
            commit_message = self._generate_commit_message(updated_packages)
            if not self.strategy.commit_changes(modified_files, commit_message):
                raise Exception("Failed to commit package updates")

        logging.info(f"Package updates completed: {len(updated_packages)} packages updated in {len(modified_files)} files")
        
        return {
            'success': True,
            'updated_packages': updated_packages,
            'modified_files': modified_files
        }

    def _execute_code_migrations(self, repo_id: str, updated_packages: List[Dict[str, str]], 
                               branch_name: str, default_branch: str) -> MigrationResult:
        """Execute code migrations and create second commit."""
        # Determine applicable migrations
        applicable_migrations = self._determine_applicable_migrations(updated_packages)
        
        if not applicable_migrations:
            logging.info("No applicable migrations found")
            return MigrationResult(
                success=True,
                modified_files=[],
                applied_rules=[],
                errors=[],
                summary="No migrations applicable"
            )

        # Find C# files for migration
        csharp_files = self.strategy.find_csharp_files(repo_id, default_branch)
        if not csharp_files:
            logging.info("No C# files found for migration")
            return MigrationResult(
                success=True,
                modified_files=[],
                applied_rules=[],
                errors=[],
                summary="No C# files found"
            )

        # Create temporary rules file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as rules_file:
            migration_rules = []
            for migration in applicable_migrations:
                for rule in migration.rules:
                    migration_rules.append(rule.to_dict())
            
            json.dump({'rules': migration_rules}, rules_file, indent=2)
            rules_file_path = rules_file.name

        try:
            # Execute migration tool
            migration_result = self.strategy.execute_csharp_migration_tool(
                repo_id, rules_file_path, csharp_files, branch_name
            )

            if migration_result and migration_result.success and migration_result.modified_files:
                # Apply modified files and create second commit
                if self.use_local_clone:
                    commit_message = self._generate_migration_commit_message(migration_result.applied_rules)
                    self.strategy.create_second_commit(
                        repo_id, migration_result.modified_files, commit_message, branch_name
                    )
                else:
                    # For API strategy, upload modified files
                    self._upload_migrated_files(repo_id, migration_result.modified_files, branch_name)

                logging.info(f"Code migrations completed: {len(migration_result.applied_rules)} rules applied")

            return migration_result or MigrationResult(
                success=False,
                modified_files=[],
                applied_rules=[],
                errors=["Migration tool returned no result"],
                summary="Migration tool failed"
            )

        finally:
            # Clean up temporary rules file
            try:
                os.unlink(rules_file_path)
            except Exception as e:
                logging.warning(f"Failed to clean up temporary rules file: {e}")

    def _upload_migrated_files(self, repo_id: str, modified_files: List[str], branch_name: str):
        """Upload migrated files for API strategy."""
        for file_path in modified_files:
            try:
                # Read the modified file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Upload to repository
                commit_message = f"Apply code migration to {os.path.basename(file_path)}"
                self.strategy.update_file(repo_id, file_path, content, commit_message, branch_name)
                
            except Exception as e:
                logging.error(f"Failed to upload migrated file {file_path}: {e}")
                raise

    def _determine_applicable_migrations(self, updated_packages: List[Dict[str, str]]) -> List:
        """Determine which migrations should be applied based on updated packages."""
        if not self.migration_config_service:
            return []

        applicable_migrations = []

        for package in updated_packages:
            package_name = package['name']
            new_version = package['version']
            
            # Check if package has explicit migration rule mapping
            migration_rule_id = package.get('migration_rule')
            if migration_rule_id:
                migrations = self.migration_config_service.get_migrations_by_package_and_rule_id(
                    package_name, migration_rule_id
                )
                applicable_migrations.extend(migrations)
            else:
                # Check for version-based migrations
                # We need the old version for this, which we don't have in this context
                # This could be enhanced to track old versions during the update process
                pass

        return applicable_migrations

    def _has_applicable_migrations(self, updated_packages: List[Dict[str, str]]) -> bool:
        """Check if any updated packages have applicable migrations."""
        return len(self._determine_applicable_migrations(updated_packages)) > 0

    def _create_merge_request_with_both_commits(self, repo_id: str, branch_name: str, default_branch: str,
                                              package_result: Dict, migration_result: Optional[MigrationResult]) -> Optional[Dict]:
        """Create merge request with enhanced description including both commits."""
        mr_title = self._generate_enhanced_mr_title(package_result['updated_packages'], migration_result)
        mr_description = self._generate_enhanced_mr_description(package_result, migration_result, default_branch)

        return self.strategy.create_merge_request(repo_id, branch_name, default_branch, mr_title, mr_description)

    def _generate_enhanced_mr_title(self, updated_packages: List[Dict[str, str]], 
                                  migration_result: Optional[MigrationResult]) -> str:
        """Generate enhanced MR title including migration info."""
        base_title = self._generate_mr_title(updated_packages)
        
        if migration_result and migration_result.success and migration_result.applied_rules:
            return f"{base_title} + Code Migrations"
        
        return base_title

    def _generate_enhanced_mr_description(self, package_result: Dict, migration_result: Optional[MigrationResult], 
                                        default_branch: str) -> str:
        """Generate enhanced MR description with both package updates and migrations."""
        description_lines = [
            "## 📦 Package Updates",
            ""
        ]
        
        # Add package update details
        description_lines.extend([
            f"Updated {len(package_result['updated_packages'])} packages:",
            ""
        ])
        
        for package in package_result['updated_packages']:
            description_lines.append(f"- **{package['name']}** → `{package['version']}`")
        
        description_lines.extend([
            "",
            f"**Modified Files:** {len(package_result['modified_files'])} .csproj files",
            ""
        ])

        # Add migration details if applicable
        if migration_result and migration_result.success:
            description_lines.extend([
                "## 🔧 Code Migrations",
                ""
            ])
            
            if migration_result.applied_rules:
                description_lines.extend([
                    f"Applied {len(migration_result.applied_rules)} migration rules:",
                    ""
                ])
                for rule in migration_result.applied_rules:
                    description_lines.append(f"- {rule}")
                
                description_lines.extend([
                    "",
                    f"**Modified Files:** {len(migration_result.modified_files)} C# files",
                    ""
                ])
            else:
                description_lines.extend([
                    "No migration rules were applicable to this update.",
                    ""
                ])

        description_lines.extend([
            "---",
            "*This merge request was created automatically by the NuGet Package Updater.*"
        ])

        return "\n".join(description_lines)

    def _generate_migration_commit_message(self, applied_rules: List[str]) -> str:
        """Generate commit message for migration changes."""
        if len(applied_rules) == 1:
            return f"Apply code migration: {applied_rules[0]}"
        else:
            return f"Apply code migrations: {len(applied_rules)} rules"

    # Keep existing methods from original implementation
    def _process_all_packages_in_files(self, repo_id: str, target_files: List[str],
                                     branch_name: str, default_branch: str) -> tuple[List[str], List[Dict[str, str]]]:
        """Process all packages in all target files and return list of modified files and updated packages."""
        modified_files = []
        updated_package_names = set()

        for file_path in target_files:
            content = self.strategy.get_file_content(repo_id, file_path, default_branch)
            if content is None:
                continue

            file_modified, file_updated_packages = self._update_file_with_all_packages(
                repo_id, file_path, content, branch_name
            )

            if file_modified:
                modified_files.append(file_path)
                for package in file_updated_packages:
                    updated_package_names.add(package['name'])

        updated_packages = [pkg for pkg in self.packages if pkg['name'] in updated_package_names]

        return modified_files, updated_packages

    def _update_file_with_all_packages(self, repo_id: str, file_path: str, original_content: str,
                                     branch_name: str) -> tuple[bool, List[Dict[str, str]]]:
        """Update a single file with all package updates."""
        current_content = original_content
        file_modified = False
        file_updated_packages = []

        for package_info in self.packages:
            package_name = package_info['name']
            new_version = package_info['version']

            file_updater = PackageFileUpdater(package_name, new_version)
            updated_content, package_modified = file_updater.update_csproj_package_version(current_content, self.allow_downgrade)

            if package_modified:
                current_content = updated_content
                file_modified = True
                file_updated_packages.append(package_info)
                logging.info(f"Package {package_name} to version {new_version} will be updated in {file_path}")

        # If file was modified, update it once with all changes
        if file_modified:
            commit_message = self._generate_file_commit_message(file_updated_packages, file_path)
            if self.strategy.update_file(repo_id, file_path, current_content, commit_message, branch_name):
                logging.info(f"Updated file {file_path} with {len(file_updated_packages)} package changes")
            else:
                logging.error(f"Failed to update file {file_path}")
                return False, []

        return file_modified, file_updated_packages

    def _generate_branch_name(self) -> str:
        """Generate a unique branch name for the updates."""
        import time
        timestamp = int(time.time())
        package_names = "-".join([pkg['name'].split('.')[-1].lower() for pkg in self.packages[:2]])
        return f"update-{package_names}-{timestamp}"

    def _generate_mr_title(self, updated_packages: Optional[List[Dict[str, str]]] = None) -> str:
        """Generate merge request title."""
        packages = updated_packages or self.packages
        if len(packages) == 1:
            package = packages[0]
            return f"Update {package['name']} to version {package['version']}"
        else:
            return f"Update {len(packages)} NuGet packages"

    def _generate_commit_message(self, updated_packages: List[Dict[str, str]]) -> str:
        """Generate a commit message for the entire update."""
        if len(updated_packages) == 1:
            package = updated_packages[0]
            return f"Update {package['name']} to version {package['version']}"
        else:
            package_list = ", ".join([f"{pkg['name']} to {pkg['version']}" for pkg in updated_packages])
            return f"Update {len(updated_packages)} packages: {package_list}"

    def _generate_file_commit_message(self, updated_packages: List[Dict[str, str]], file_path: str) -> str:
        """Generate a commit message for file-specific updates."""
        if len(updated_packages) == 1:
            package = updated_packages[0]
            return f"Update {package['name']} to version {package['version']} in {file_path}"
        else:
            package_list = ", ".join([f"{pkg['name']} to {pkg['version']}" for pkg in updated_packages])
            return f"Update {len(updated_packages)} packages in {file_path}: {package_list}"
