"""
Local clone strategy for repository operations with rollback support.
"""
import logging
import os
import shutil
from typing import List, Dict, Optional

from src.core.repository_strategy import RepositoryStrategy
from src.services.git_service import GitService
from src.providers.scm_provider import ScmProvider
from src.services.rollback_service import RepositoryUpdateTransaction


class LocalCloneStrategy(RepositoryStrategy):
    """Strategy that uses local git clones for repository operations with rollback support."""

    def __init__(self, git_service: GitService, scm_provider: ScmProvider):
        self.git_service = git_service
        self.scm_provider = scm_provider
        self.transaction: Optional[RepositoryUpdateTransaction] = None

    def set_transaction(self, transaction: RepositoryUpdateTransaction):
        """Set the transaction for rollback support."""
        self.transaction = transaction

    def find_target_files(self, repo_id: str, file_extension: str, default_branch: str) -> List[str]:
        """Find all files with the given extension in the local repository."""
        target_files = []
        if not self.git_service.local_path:
            logging.error("Local repository path not available")
            return target_files
            
        for root, dirs, files in os.walk(self.git_service.local_path):
            for file in files:
                if file.endswith(file_extension):
                    target_files.append(os.path.join(root, file))
        logging.info(f"Found {len(target_files)} {file_extension} files")
        return target_files

    def find_csharp_files(self, repo_id: str, default_branch: str) -> List[str]:
        """Find all C# files in the local repository."""
        return self.find_target_files(repo_id, '.cs', default_branch)

    def get_file_content(self, repo_id: str, file_path: str, default_branch: str) -> Optional[str]:
        """Get the content of a file from the local repository."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logging.error(f"Failed to read file {file_path}: {e}")
            return None

    def create_branch(self, repo_id: str, branch_name: str, default_branch: str) -> bool:
        """Create a new branch in the local repository with rollback support."""
        try:
            self.git_service.create_branch(branch_name)
            
            # Register branch deletion rollback
            if self.transaction:
                self.transaction.add_rollback_action(
                    lambda: self._delete_branch_if_exists(branch_name, default_branch),
                    f"Delete branch {branch_name}"
                )
                self.transaction.set_created_branch(branch_name)
                
            return True
        except Exception as e:
            logging.error(f"Failed to create branch {branch_name}: {e}")
            return False

    def update_file(self, repo_id: str, file_path: str, content: str,
                   commit_message: str, branch_name: str) -> bool:
        """Update a file in the local repository with rollback support."""
        # Store original content for potential rollback
        original_content = None
        file_existed = os.path.exists(file_path)
        
        if file_existed:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
            except Exception as e:
                logging.warning(f"Could not read original content of {file_path}: {e}")
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            # Register file revert rollback
            if self.transaction:
                if file_existed and original_content is not None:
                    self.transaction.add_rollback_action(
                        lambda: self._revert_file_change(file_path, original_content),
                        f"Revert file {file_path}"
                    )
                else:
                    # File didn't exist, so delete it on rollback
                    self.transaction.add_rollback_action(
                        lambda: self._delete_file_if_exists(file_path),
                        f"Delete created file {file_path}"
                    )
                    
            return True
        except Exception as e:
            logging.error(f"Failed to update file {file_path}: {e}")
            return False

    def create_second_commit(self, repo_id: str, modified_files: List[str], commit_message: str, branch_name: str) -> bool:
        """Create a second commit for migration changes."""
        try:
            if modified_files:
                self.git_service.add(modified_files)
                self.git_service.commit(commit_message)
                logging.info(f"Created second commit with {len(modified_files)} modified files")
            return True
        except Exception as e:
            logging.error(f"Failed to create second commit: {e}")
            return False

    def create_merge_request(self, repo_id: str, source_branch: str, target_branch: str,
                           title: str, description: str) -> Optional[Dict]:
        """Create a merge request using the SCM provider."""
        return self.scm_provider.create_merge_request(repo_id, source_branch, target_branch, title, description)

    def cleanup_branch(self, repo_id: str, branch_name: str, default_branch: str) -> bool:
        """Clean up branch - for local strategy, delete local and remote branch."""
        try:
            # Check if we're currently on the branch we want to delete
            current_branch = self.git_service.get_current_branch()
            if current_branch == branch_name:
                # Switch to default branch before deleting
                logging.info(f"Switching from {branch_name} to {default_branch} before cleanup")
                self.git_service.checkout_branch(default_branch)
            
            # Delete local branch if it exists
            if self.git_service.branch_exists(branch_name):
                logging.info(f"Deleting local branch {branch_name}")
                self.git_service.delete_branch(branch_name)
            else:
                logging.debug(f"Local branch {branch_name} does not exist")
            
            # Delete remote branch if it exists
            if self.scm_provider.branch_exists(repo_id, branch_name):
                logging.info(f"Deleting remote branch {branch_name}")
                self.scm_provider.delete_branch(repo_id, branch_name)
            else:
                logging.debug(f"Remote branch {branch_name} does not exist")
                
            return True
        except Exception as e:
            logging.error(f"Failed to cleanup branch {branch_name}: {e}")
            return False

    def prepare_repository(self, repo_url: str, repo_id: str) -> bool:
        """Clone the repository locally with rollback support."""
        try:
            clone_path = self.git_service.clone_repository(repo_url)
            
            # Register cleanup action
            if self.transaction:
                self.transaction.add_rollback_action(
                    lambda: self._cleanup_local_clone(),
                    f"Cleanup local clone at {clone_path}"
                )
                
            return True
        except Exception as e:
            logging.error(f"Failed to clone repository {repo_url}: {e}")
            return False

    def cleanup_repository(self, repo_id: str) -> None:
        """Clean up local repository resources."""
        self.git_service.cleanup_repository()

    def commit_changes(self, modified_files: List[str], commit_message: str) -> bool:
        """Commit changes locally."""
        try:
            self.git_service.add(modified_files)
            self.git_service.commit(commit_message)
            return True
        except Exception as e:
            logging.error(f"Failed to commit changes: {e}")
            return False

    def push_changes(self, branch_name: str) -> bool:
        """Push changes to the remote repository."""
        try:
            self.git_service.push('origin', branch_name)
            return True
        except Exception as e:
            logging.error(f"Failed to push changes: {e}")
            return False

    def execute_csharp_migration_tool(self, repo_id: str, rules_file: str, target_files: List[str], branch_name: str):
        """Execute C# migration tool on local files."""
        from src.services.code_migration_service import CodeMigrationService
        import json
        
        # Load rules from file
        try:
            with open(rules_file, 'r') as f:
                rules_data = json.load(f)
            rules = rules_data.get('rules', [])
        except Exception as e:
            logging.error(f"Failed to load migration rules: {e}")
            return None
        
        # Execute migration tool
        migration_service = CodeMigrationService("./CSharpMigrationTool")
        return migration_service.execute_migrations(target_files, rules, self.git_service.local_path)

    def _delete_branch_if_exists(self, branch_name: str, default_branch: str):
        """Rollback: Delete created branch and return to default branch."""
        try:
            # Switch to default branch first
            if self.git_service.get_current_branch() == branch_name:
                self.git_service.checkout_branch(default_branch)
            
            # Delete the created branch
            self.git_service.delete_branch(branch_name)
            
            logging.info(f"Rollback: Deleted branch {branch_name}")
        except Exception as e:
            logging.warning(f"Failed to delete branch during rollback: {e}")

    def _cleanup_local_clone(self):
        """Rollback: Remove entire local clone directory."""
        try:
            self.git_service.cleanup_repository()
            logging.info("Rollback: Cleaned up local clone")
        except Exception as e:
            logging.warning(f"Failed to cleanup local clone during rollback: {e}")

    def _revert_file_change(self, file_path: str, original_content: str):
        """Rollback: Revert file to original content."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            logging.info(f"Rollback: Reverted file {file_path}")
        except Exception as e:
            logging.warning(f"Failed to revert file during rollback: {e}")

    def _delete_file_if_exists(self, file_path: str):
        """Rollback: Delete file if it exists."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Rollback: Deleted file {file_path}")
        except Exception as e:
            logging.warning(f"Failed to delete file during rollback: {e}")
