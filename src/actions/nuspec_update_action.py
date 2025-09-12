import logging
from typing import List, Dict, Optional

from src.core.action import Action
from src.core.repository_strategy import RepositoryStrategy
from src.core.package_file_updater import PackageFileUpdater
from src.services.git_service import GitService
from src.providers.scm_provider import ScmProvider
from src.strategies.local_clone_strategy import LocalCloneStrategy
from src.strategies.api_strategy import ApiStrategy


class NuspecUpdateAction(Action):
    """Action to update a NuGet package in a repository using configurable strategies."""

    def __init__(self, git_service: GitService, scm_provider: ScmProvider, package_name: str, new_version: str,
                 allow_downgrade: bool = False, use_local_clone: bool = False):
        self.git_service = git_service
        self.scm_provider = scm_provider
        self.package_name = package_name
        self.new_version = new_version
        self.allow_downgrade = allow_downgrade
        self.use_local_clone = use_local_clone

        # Initialize the strategy based on configuration
        self.strategy: RepositoryStrategy = self._create_strategy()
        self.file_updater = PackageFileUpdater(package_name, new_version)

    def _create_strategy(self) -> RepositoryStrategy:
        """Create the appropriate repository strategy based on configuration."""
        if self.use_local_clone:
            return LocalCloneStrategy(self.git_service, self.scm_provider)
        else:
            return ApiStrategy(self.scm_provider)

    def execute(self, repo_url: str, repo_id: str, default_branch: str) -> Optional[Dict]:
        """Execute the action using the configured strategy."""
        try:
            logging.info(f"Processing repository {repo_url or repo_id} using {'local clone' if self.use_local_clone else 'API'} strategy")

            # Prepare repository (clone if needed)
            if not self.strategy.prepare_repository(repo_url, repo_id):
                logging.error(f"Failed to prepare repository {repo_url or repo_id}")
                return None

            # Find target files (.csproj files for NuGet packages)
            target_files = self.strategy.find_target_files(repo_id, '.csproj', default_branch)
            if not target_files:
                logging.info(f"No .csproj files found in repository {repo_id}")
                return None

            # Create branch for the update
            branch_name = f"update-{self.package_name.lower().replace('.', '-')}-to-{self.new_version.replace('.', '_')}"
            if not self.strategy.create_branch(repo_id, branch_name, default_branch):
                logging.error(f"Failed to create branch {branch_name} in repository {repo_id}")
                return None

            # Process each target file
            modified_files = self._process_target_files(repo_id, target_files, branch_name, default_branch)

            # Handle results
            result = self._handle_processing_results(repo_id, modified_files, branch_name, default_branch)

            # Cleanup repository resources
            self.strategy.cleanup_repository(repo_id)

            return result

        except Exception as e:
            logging.error(f"Error processing repository {repo_url or repo_id}: {e}")
            self.strategy.cleanup_repository(repo_id)
            return None

    def _process_target_files(self, repo_id: str, target_files: List[str],
                            branch_name: str, default_branch: str) -> List[str]:
        """Process each target file and return list of modified files."""
        modified_files = []

        for file_path in target_files:
            # Get file content
            content = self.strategy.get_file_content(repo_id, file_path, default_branch)
            if content is None:
                continue

            # Update package version
            updated_content, modified = self.file_updater.update_csproj_package_version(content, self.allow_downgrade)
            if not modified:
                continue

            # Update the file using the strategy
            commit_message = f"Update {self.package_name} to version {self.new_version} in {file_path}"
            if self.strategy.update_file(repo_id, file_path, updated_content, commit_message, branch_name):
                modified_files.append(file_path)
                logging.info(f"Updated {file_path} in repository {repo_id}")
            else:
                logging.error(f"Failed to update {file_path} in repository {repo_id}")

        return modified_files

    def _handle_processing_results(self, repo_id: str, modified_files: List[str],
                                 branch_name: str, default_branch: str) -> Optional[Dict]:
        """Handle the results of file processing and create merge request if needed."""
        if not modified_files:
            # Clean up branch if no changes were made
            self.strategy.cleanup_branch(repo_id, branch_name)
            logging.info(f"No changes needed for {self.package_name} in repository {repo_id}")
            return None

        # For local clone strategy, we need to commit and push changes
        if self.use_local_clone and hasattr(self.strategy, 'commit_and_push_changes'):
            commit_message = f"Update {self.package_name} to version {self.new_version}"
            if not self.strategy.commit_and_push_changes(modified_files, commit_message, branch_name):
                logging.error(f"Failed to commit and push changes for repository {repo_id}")
                return None

        # Create merge request
        mr_title = f"Update {self.package_name} to version {self.new_version}"
        mr_description = self._generate_mr_description(modified_files, default_branch)

        mr_result = self.strategy.create_merge_request(repo_id, branch_name, default_branch, mr_title, mr_description)

        # Enhance the result with branch information
        if mr_result:
            mr_result['target_branch'] = default_branch
            mr_result['source_branch'] = branch_name
            logging.info(f"Created merge request: {mr_result.get('web_url', 'N/A')}")

        return mr_result

    def _generate_mr_description(self, modified_files: List[str], default_branch: str) -> str:
        """Generate merge request description."""
        return f"""
## NuGet Package Update

This merge request updates the following NuGet package:
- **Package**: {self.package_name}
- **New Version**: {self.new_version}

### Files Modified:
{chr(10).join(f'- `{file_path}`' for file_path in modified_files)}
        """.strip()


# Legacy compatibility - keep the old CSProjUpdater class for backward compatibility
class CSProjUpdater:
    """Legacy class for backward compatibility. Use PackageFileUpdater instead."""

    def __init__(self, package_name: str, new_version: str):
        self._updater = PackageFileUpdater(package_name, new_version)
        self.package_name = package_name
        self.new_version = new_version

    def find_csproj_files(self, start_dir: str) -> List[str]:
        """Legacy method - use strategy.find_target_files instead."""
        import os
        csproj_files = []
        for root, dirs, files in os.walk(start_dir):
            for file in files:
                if file.endswith('.csproj'):
                    csproj_files.append(os.path.join(root, file))
        logging.info(f"Found {len(csproj_files)} .csproj files")
        return csproj_files

    def find_csproj_files_from_tree(self, tree: List[Dict]) -> List[str]:
        """Legacy method - use strategy.find_target_files instead."""
        csproj_files = []
        for item in tree:
            if item['type'] == 'blob' and item['name'].endswith('.csproj'):
                csproj_files.append(item['path'])
        logging.info(f"Found {len(csproj_files)} .csproj files")
        return csproj_files

    def update_package_version(self, csproj_content: str, allow_downgrade: bool):
        """Legacy method - delegates to PackageFileUpdater."""
        return self._updater.update_csproj_package_version(csproj_content, allow_downgrade)
