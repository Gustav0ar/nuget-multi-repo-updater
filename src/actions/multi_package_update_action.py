"""
Action to update multiple NuGet packages in a repository in a single transaction.
"""
import logging
from typing import List, Dict, Optional

from src.core.action import Action
from src.core.repository_strategy import RepositoryStrategy
from src.core.package_file_updater import PackageFileUpdater
from src.services.git_service import GitService
from src.providers.scm_provider import ScmProvider
from src.strategies.local_clone_strategy import LocalCloneStrategy
from src.strategies.api_strategy import ApiStrategy


class MultiPackageUpdateAction(Action):
    """Action to update multiple NuGet packages in a repository using configurable strategies."""

    def __init__(self, git_service: GitService, scm_provider: ScmProvider, packages: List[Dict[str, str]],
                 allow_downgrade: bool = False, use_local_clone: bool = False):
        self.git_service = git_service
        self.scm_provider = scm_provider
        self.packages = packages  # List of {'name': package_name, 'version': new_version}
        self.allow_downgrade = allow_downgrade
        self.use_local_clone = use_local_clone

        # Initialize the strategy based on configuration
        self.strategy: RepositoryStrategy = self._create_strategy()

    def _create_strategy(self) -> RepositoryStrategy:
        """Create the appropriate repository strategy based on configuration."""
        if self.use_local_clone:
            return LocalCloneStrategy(self.git_service, self.scm_provider)
        else:
            return ApiStrategy(self.scm_provider)

    def execute(self, repo_url: str, repo_id: str, default_branch: str) -> Optional[Dict]:
        """Execute the action using the configured strategy."""
        try:
            package_names = [pkg['name'] for pkg in self.packages]
            logging.info(f"Processing repository {repo_url or repo_id} for packages {package_names} using {'local clone' if self.use_local_clone else 'API'} strategy")

            # Check for existing merge request with combined package updates
            mr_title = self._generate_mr_title()
            existing_mr = self.scm_provider.check_existing_merge_request(
                repo_id, mr_title, target_branch=default_branch
            )

            if existing_mr:
                logging.info(f"Merge request already exists for package updates in repository {repo_id}: {existing_mr['web_url']}")
                return existing_mr

            # Prepare repository (clone if needed)
            if not self.strategy.prepare_repository(repo_url, repo_id):
                logging.error(f"Failed to prepare repository {repo_url or repo_id}")
                return None

            # Find target files (.csproj files for NuGet packages)
            target_files = self.strategy.find_target_files(repo_id, '.csproj', default_branch)
            if not target_files:
                logging.info(f"No .csproj files found in repository {repo_id}")
                return None

            # Create branch for all package updates
            branch_name = self._generate_branch_name()
            if not self.strategy.create_branch(repo_id, branch_name, default_branch):
                logging.error(f"Failed to create branch {branch_name} in repository {repo_id}")
                return None

            # Process all packages in all target files
            modified_files, updated_packages = self._process_all_packages_in_files(repo_id, target_files, branch_name, default_branch)

            # Handle results
            result = self._handle_processing_results(repo_id, modified_files, updated_packages, branch_name, default_branch)

            # Cleanup repository resources
            self.strategy.cleanup_repository(repo_id)

            return result

        except Exception as e:
            logging.error(f"Error processing repository {repo_url or repo_id}: {e}")
            self.strategy.cleanup_repository(repo_id)
            return None

    def _process_all_packages_in_files(self, repo_id: str, target_files: List[str],
                                     branch_name: str, default_branch: str) -> tuple[List[str], List[Dict[str, str]]]:
        """Process all packages in all target files and return list of modified files and updated packages."""
        modified_files = []
        updated_packages = []

        for file_path in target_files:
            # Get file content
            content = self.strategy.get_file_content(repo_id, file_path, default_branch)
            if content is None:
                continue

            # Process all packages for this file
            file_modified, file_updated_packages = self._update_file_with_all_packages(
                repo_id, file_path, content, branch_name
            )

            if file_modified:
                modified_files.append(file_path)
                updated_packages.extend(file_updated_packages)

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
                logging.info(f"Updated {file_path} with {len(file_updated_packages)} package updates in repository {repo_id}")
                return True, file_updated_packages
            else:
                logging.error(f"Failed to update {file_path} in repository {repo_id}")
                return False, []

        return False, []

    def _handle_processing_results(self, repo_id: str, modified_files: List[str], updated_packages: List[Dict[str, str]],
                                 branch_name: str, default_branch: str) -> Optional[Dict]:
        """Handle the results of file processing and create merge request if needed."""
        if not modified_files or not updated_packages:
            # Clean up branch if no changes were made
            self.strategy.cleanup_branch(repo_id, branch_name)
            logging.info(f"No changes needed for any packages in repository {repo_id}")
            return None

        # For local clone strategy, we need to commit and push changes
        if self.use_local_clone and hasattr(self.strategy, 'commit_and_push_changes'):
            commit_message = self._generate_commit_message(updated_packages)
            if not self.strategy.commit_and_push_changes(modified_files, commit_message, branch_name):
                logging.error(f"Failed to commit and push changes for repository {repo_id}")
                return None

        # Create merge request
        mr_title = self._generate_mr_title(updated_packages)
        mr_description = self._generate_mr_description(modified_files, updated_packages, default_branch)

        mr_result = self.strategy.create_merge_request(repo_id, branch_name, default_branch, mr_title, mr_description)

        if mr_result:
            # Add information about all updated packages to the result
            mr_result['updated_packages'] = updated_packages
            logging.info(f"Created merge request for {len(updated_packages)} package updates in repository {repo_id}: {mr_result.get('web_url', 'URL not available')}")

        return mr_result

    def _generate_branch_name(self) -> str:
        """Generate a branch name for multi-package updates."""
        if len(self.packages) == 1:
            package = self.packages[0]
            return f"update-{package['name'].lower().replace('.', '-')}-to-{package['version'].replace('.', '_')}"
        else:
            return f"update-multiple-packages-{len(self.packages)}-packages"

    def _generate_mr_title(self, updated_packages: Optional[List[Dict[str, str]]] = None) -> str:
        """Generate a merge request title for multi-package updates."""
        # Use updated_packages if provided, otherwise fall back to all packages
        packages_to_use = updated_packages if updated_packages is not None else self.packages

        if len(packages_to_use) == 1:
            package = packages_to_use[0]
            return f"Update {package['name']} to version {package['version']}"
        else:
            package_names = [pkg['name'] for pkg in packages_to_use]

    def _generate_commit_message(self, updated_packages: List[Dict[str, str]]) -> str:
        """Generate a commit message for multi-package updates."""
        if len(updated_packages) == 1:
            package = updated_packages[0]
            return f"Update {package['name']} to version {package['version']}"
        else:
            package_list = ", ".join([f"{pkg['name']} to {pkg['version']}" for pkg in updated_packages])
            return f"Update packages: {', '.join(package_names)}"

    def _generate_file_commit_message(self, updated_packages: List[Dict[str, str]], file_path: str) -> str:
        """Generate a commit message for file-specific updates."""
        if len(updated_packages) == 1:
            package = updated_packages[0]
            return f"Update {package['name']} to version {package['version']} in {file_path}"
        else:
            package_list = ", ".join([f"{pkg['name']} to {pkg['version']}" for pkg in updated_packages])
            return f"Update {len(updated_packages)} packages in {file_path}: {package_list}"

    def _generate_mr_description(self, modified_files: List[str], updated_packages: List[Dict[str, str]], default_branch: str) -> str:
        """Generate a comprehensive merge request description."""
        description_parts = []

        if len(updated_packages) == 1:
            package = updated_packages[0]
            description_parts.append(f"This merge request updates **{package['name']}** to version **{package['version']}**.")
        else:
            description_parts.append(f"This merge request updates **{len(updated_packages)} NuGet packages**:")
            description_parts.append("")
            for package in updated_packages:
                description_parts.append(f"- **{package['name']}** → {package['version']}")

        description_parts.append("")
        description_parts.append("### Modified Files:")
        for file_path in modified_files:
            description_parts.append(f"- `{file_path}`")

        description_parts.append("")
        description_parts.append(f"**Target Branch:** `{default_branch}`")
        description_parts.append("")
        description_parts.append("Please review the changes and merge when ready.")

        return "\n".join(description_parts)
