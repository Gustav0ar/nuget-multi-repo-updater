"""
Abstract repository strategy interface for different repository access methods with migration support.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class RepositoryStrategy(ABC):
    """Abstract base class for repository access strategies with migration support."""

    @abstractmethod
    def find_target_files(self, repo_id: str, file_extension: str, default_branch: str) -> List[str]:
        """Find all files with the given extension in the repository."""
        pass

    @abstractmethod
    def find_csharp_files(self, repo_id: str, default_branch: str) -> List[str]:
        """Find all C# files in the repository."""
        pass

    @abstractmethod
    def get_file_content(self, repo_id: str, file_path: str, default_branch: str) -> Optional[str]:
        """Get the content of a file from the repository."""
        pass

    @abstractmethod
    def create_branch(self, repo_id: str, branch_name: str, default_branch: str) -> bool:
        """Create a new branch in the repository."""
        pass

    @abstractmethod
    def update_file(self, repo_id: str, file_path: str, content: str,
                   commit_message: str, branch_name: str) -> bool:
        """Update a file in the repository."""
        pass

    @abstractmethod
    def create_second_commit(self, repo_id: str, modified_files: List[str], commit_message: str, branch_name: str) -> bool:
        """Create a second commit for migration changes."""
        pass

    @abstractmethod
    def create_merge_request(self, repo_id: str, source_branch: str, target_branch: str,
                           title: str, description: str) -> Optional[Dict]:
        """Create a merge request in the repository."""
        pass

    @abstractmethod
    def cleanup_branch(self, repo_id: str, branch_name: str) -> bool:
        """Clean up (delete) a branch if no changes were made."""
        pass

    @abstractmethod
    def prepare_repository(self, repo_url: str, repo_id: str) -> bool:
        """Prepare the repository for operations (e.g., clone for local strategy)."""
        pass

    @abstractmethod
    def cleanup_repository(self, repo_id: str) -> None:
        """Clean up repository resources after operations."""
        pass

    @abstractmethod
    def execute_csharp_migration_tool(self, repo_id: str, rules_file: str, target_files: List[str]):
        """Execute C# migration tool on target files."""
        pass

    def set_transaction(self, transaction):
        """Set the transaction for rollback support. Optional implementation."""
        pass
