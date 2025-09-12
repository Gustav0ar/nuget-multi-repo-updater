"""
API-based strategy for repository operations.
"""
import logging
from typing import List, Dict, Optional

from src.core.repository_strategy import RepositoryStrategy
from src.providers.scm_provider import ScmProvider


class ApiStrategy(RepositoryStrategy):
    """Strategy that uses API calls for repository operations without local cloning."""

    def __init__(self, scm_provider: ScmProvider):
        self.scm_provider = scm_provider

    def find_target_files(self, repo_id: str, file_extension: str, default_branch: str) -> List[str]:
        """Find all files with the given extension using API."""
        tree = self.scm_provider.get_repository_tree(repo_id, ref=default_branch)
        if not tree:
            logging.error(f"Could not get repository tree for {repo_id}")
            return []

        target_files = []
        for item in tree:
            if item['type'] == 'blob' and item['name'].endswith(file_extension):
                target_files.append(item['path'])

        logging.info(f"Found {len(target_files)} {file_extension} files")
        return target_files

    def get_file_content(self, repo_id: str, file_path: str, default_branch: str) -> Optional[str]:
        """Get the content of a file using API."""
        content = self.scm_provider.get_file_content(repo_id, file_path, ref=default_branch)
        if content is None:
            logging.warning(f"Could not get content for file {file_path}")
        return content

    def create_branch(self, repo_id: str, branch_name: str, default_branch: str) -> bool:
        """Create a new branch using API."""
        return self.scm_provider.create_branch(repo_id, branch_name, ref=default_branch)

    def update_file(self, repo_id: str, file_path: str, content: str,
                   commit_message: str, branch_name: str) -> bool:
        """Update a file using API."""
        return self.scm_provider.update_file(repo_id, file_path, content, commit_message, branch_name)

    def create_merge_request(self, repo_id: str, source_branch: str, target_branch: str,
                           title: str, description: str) -> Optional[Dict]:
        """Create a merge request using API."""
        return self.scm_provider.create_merge_request(repo_id, source_branch, target_branch, title, description)

    def cleanup_branch(self, repo_id: str, branch_name: str) -> bool:
        """Clean up branch using API - not all providers support this directly."""
        # Note: Not all SCM providers have a delete_branch method in the current interface
        # This could be implemented as needed by specific providers
        logging.info(f"Branch cleanup not implemented for {branch_name}")
        return True

    def prepare_repository(self, repo_url: str, repo_id: str) -> bool:
        """No preparation needed for API strategy."""
        return True

    def cleanup_repository(self, repo_id: str) -> None:
        """No cleanup needed for API strategy."""
        pass
