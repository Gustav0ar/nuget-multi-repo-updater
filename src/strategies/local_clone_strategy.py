"""
Local clone strategy for repository operations.
"""
import logging
import os
from typing import List, Dict, Optional

from src.core.repository_strategy import RepositoryStrategy
from src.services.git_service import GitService
from src.providers.scm_provider import ScmProvider


class LocalCloneStrategy(RepositoryStrategy):
    """Strategy that uses local git clones for repository operations."""

    def __init__(self, git_service: GitService, scm_provider: ScmProvider):
        self.git_service = git_service
        self.scm_provider = scm_provider

    def find_target_files(self, repo_id: str, file_extension: str, default_branch: str) -> List[str]:
        """Find all files with the given extension in the local repository."""
        target_files = []
        for root, dirs, files in os.walk(self.git_service.local_path):
            for file in files:
                if file.endswith(file_extension):
                    target_files.append(os.path.join(root, file))
        logging.info(f"Found {len(target_files)} {file_extension} files")
        return target_files

    def get_file_content(self, repo_id: str, file_path: str, default_branch: str) -> Optional[str]:
        """Get the content of a file from the local repository."""
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception as e:
            logging.error(f"Failed to read file {file_path}: {e}")
            return None

    def create_branch(self, repo_id: str, branch_name: str, default_branch: str) -> bool:
        """Create a new branch in the local repository."""
        try:
            self.git_service.create_branch(branch_name)
            return True
        except Exception as e:
            logging.error(f"Failed to create branch {branch_name}: {e}")
            return False

    def update_file(self, repo_id: str, file_path: str, content: str,
                   commit_message: str, branch_name: str) -> bool:
        """Update a file in the local repository."""
        try:
            with open(file_path, 'w') as f:
                f.write(content)
            return True
        except Exception as e:
            logging.error(f"Failed to update file {file_path}: {e}")
            return False

    def create_merge_request(self, repo_id: str, source_branch: str, target_branch: str,
                           title: str, description: str) -> Optional[Dict]:
        """Create a merge request using the SCM provider."""
        return self.scm_provider.create_merge_request(repo_id, source_branch, target_branch, title, description)

    def cleanup_branch(self, repo_id: str, branch_name: str) -> bool:
        """Clean up branch - for local strategy, this would require additional implementation."""
        # Note: Branch cleanup for local repositories would require additional git operations
        # This could be implemented by deleting the local branch and optionally the remote branch
        logging.info(f"Branch cleanup not fully implemented for local strategy: {branch_name}")
        return True

    def prepare_repository(self, repo_url: str, repo_id: str) -> bool:
        """Clone the repository locally."""
        try:
            self.git_service.clone(repo_url)
            return True
        except Exception as e:
            logging.error(f"Failed to clone repository {repo_url}: {e}")
            return False

    def cleanup_repository(self, repo_id: str) -> None:
        """Clean up local repository resources."""
        # Git service should handle cleanup of local files
        pass

    def commit_and_push_changes(self, modified_files: List[str], commit_message: str, branch_name: str) -> bool:
        """Commit and push changes for local strategy."""
        try:
            self.git_service.add(modified_files)
            self.git_service.commit(commit_message)
            self.git_service.push('origin', branch_name)
            return True
        except Exception as e:
            logging.error(f"Failed to commit and push changes: {e}")
            return False
