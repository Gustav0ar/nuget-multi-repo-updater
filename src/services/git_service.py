import git
import logging
import tempfile
import shutil
import os
from git import Repo
from typing import Optional


class GitService:
    """Service for handling local Git operations with rollback support."""

    def __init__(self, base_dir: str = "./temp"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.local_path = None
        self.repo = None
        self.original_branch = None

    def clone_repository(self, repo_url: str) -> str:
        """Clone repository and track for cleanup."""
        clone_dir = tempfile.mkdtemp(prefix="nuget-updater-", dir=self.base_dir)
        
        try:
            self.repo = Repo.clone_from(repo_url, clone_dir)
            self.local_path = clone_dir
            self.original_branch = self.repo.active_branch.name
            
            logging.info(f"Cloned repository to {clone_dir}")
            return clone_dir
            
        except Exception as e:
            # Cleanup on failure
            shutil.rmtree(clone_dir, ignore_errors=True)
            raise e

    def clone(self, repo_url: str):
        """Legacy method - use clone_repository instead."""
        self.clone_repository(repo_url)

    def create_branch(self, branch_name: str):
        """Create branch and track original state."""
        if not self.repo:
            raise ValueError("Repository not initialized")
            
        self.repo.git.checkout('-b', branch_name)
        logging.info(f"Created and switched to branch {branch_name}")

    def checkout_branch(self, branch_name: str):
        """Switch to specified branch."""
        if not self.repo:
            raise ValueError("Repository not initialized")
            
        self.repo.git.checkout(branch_name)
        logging.info(f"Switched to branch {branch_name}")

    def delete_branch(self, branch_name: str):
        """Delete specified branch."""
        if not self.repo:
            raise ValueError("Repository not initialized")
            
        try:
            self.repo.git.branch('-D', branch_name)
            logging.info(f"Deleted branch {branch_name}")
        except Exception as e:
            logging.warning(f"Could not delete branch {branch_name}: {e}")

    def reset_to_clean_state(self):
        """Reset repository to clean state and original branch."""
        if not self.repo or not self.original_branch:
            return
            
        try:
            # Discard all changes
            self.repo.git.reset('--hard')
            self.repo.git.clean('-fd')
            
            # Return to original branch
            self.checkout_branch(self.original_branch)
            
            logging.info("Reset repository to clean state")
        except Exception as e:
            logging.warning(f"Failed to reset repository state: {e}")

    def cleanup_repository(self):
        """Clean up the entire repository clone."""
        if self.local_path:
            try:
                shutil.rmtree(self.local_path, ignore_errors=True)
                logging.info(f"Cleaned up repository clone at {self.local_path}")
                self.local_path = None
                self.repo = None
                self.original_branch = None
            except Exception as e:
                logging.warning(f"Failed to cleanup repository: {e}")

    def add(self, files: list):
        """Add files to the index."""
        if self.repo:
            self.repo.index.add(files)

    def commit(self, message: str):
        """Commit changes."""
        if self.repo:
            self.repo.index.commit(message)

    def push(self, remote_name: str, branch_name: str):
        """Push changes to a remote."""
        if self.repo:
            self.repo.remotes[remote_name].push(branch_name)

    def get_current_branch(self) -> Optional[str]:
        """Get the current active branch name."""
        if self.repo:
            try:
                return self.repo.active_branch.name
            except Exception:
                return None
        return None

    def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists locally."""
        if not self.repo:
            return False
            
        try:
            self.repo.heads[branch_name]
            return True
        except Exception:
            return False
