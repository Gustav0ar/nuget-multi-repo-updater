from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class ScmProvider(ABC):
    """Abstract base class for Source Code Management providers."""

    @abstractmethod
    def create_merge_request(self, project_id: str, source_branch: str, target_branch: str, title: str, description: str) -> Optional[Dict]:
        """Create a merge request."""
        pass

    @abstractmethod
    def get_merge_request_status(self, project_id: str, mr_iid: str) -> Optional[str]:
        """Get the status of a merge request."""
        pass

    @abstractmethod
    def check_existing_merge_request(self, project_id: str, title: str,
                                     source_branch: str = None, target_branch: str = None) -> Optional[Dict]:
        """Check if a merge request with the same title already exists."""
        pass

    @abstractmethod
    def get_project(self, project_id: str) -> Optional[Dict]:
        """Get project information."""
        pass

    @abstractmethod
    def get_repository_tree(self, project_id: str, path: str = "", ref: str = "main") -> List[Dict]:
        """Get repository tree structure."""
        pass

    @abstractmethod
    def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> Optional[str]:
        """Get the content of a file from the repository."""
        pass

    @abstractmethod
    def update_file(self, project_id: str, file_path: str, content: str, commit_message: str,
                   branch_name: str) -> bool:
        """Update a file in the repository."""
        pass

    @abstractmethod
    def create_branch(self, project_id: str, branch_name: str, ref: str = "main") -> bool:
        """Create a new branch in the repository."""
        pass
