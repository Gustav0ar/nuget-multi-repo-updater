"""
API-based strategy for repository operations with rollback support.
"""
import logging
import tempfile
import os
import json
from typing import List, Dict, Optional

from src.core.repository_strategy import RepositoryStrategy
from src.providers.scm_provider import ScmProvider
from src.services.rollback_service import RepositoryUpdateTransaction


class ApiStrategy(RepositoryStrategy):
    """Strategy that uses API calls for repository operations without local cloning, with rollback support."""

    def __init__(self, scm_provider: ScmProvider):
        self.scm_provider = scm_provider
        self.transaction: Optional[RepositoryUpdateTransaction] = None

    def set_transaction(self, transaction: RepositoryUpdateTransaction):
        """Set the transaction for rollback support."""
        self.transaction = transaction

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

    def find_csharp_files(self, repo_id: str, default_branch: str) -> List[str]:
        """Find all C# files using API."""
        return self.find_target_files(repo_id, '.cs', default_branch)

    def get_file_content(self, repo_id: str, file_path: str, default_branch: str) -> Optional[str]:
        """Get the content of a file using API."""
        content = self.scm_provider.get_file_content(repo_id, file_path, ref=default_branch)
        if content is None:
            logging.warning(f"Could not get content for file {file_path}")
        return content

    def create_branch(self, repo_id: str, branch_name: str, default_branch: str) -> bool:
        """Create a new branch using API with rollback support."""
        success = self.scm_provider.create_branch(repo_id, branch_name, ref=default_branch)
        
        if success and self.transaction:
            # Register remote branch deletion rollback
            self.transaction.add_rollback_action(
                lambda: self._delete_remote_branch(repo_id, branch_name),
                f"Delete remote branch {branch_name}"
            )
            self.transaction.set_created_branch(branch_name)
            
        return success

    def update_file(self, repo_id: str, file_path: str, content: str,
                   commit_message: str, branch_name: str) -> bool:
        """Update a file using API with rollback support."""
        # Store original content for potential rollback
        original_content = self.get_file_content(repo_id, file_path, branch_name)
        
        success = self.scm_provider.update_file(repo_id, file_path, content, commit_message, branch_name)
        
        if success and self.transaction and original_content is not None:
            # Register file revert rollback
            self.transaction.add_rollback_action(
                lambda: self._revert_file_change(repo_id, file_path, original_content, branch_name),
                f"Revert file {file_path}"
            )
            
        return success

    def create_second_commit(self, repo_id: str, modified_files: List[str], commit_message: str, branch_name: str) -> bool:
        """Create a second commit for migration changes via API."""
        # For API strategy, files are committed individually, so this is mainly for logging
        if modified_files:
            logging.info(f"Second commit concept: {len(modified_files)} files modified with message: {commit_message}")
        return True

    def create_merge_request(self, repo_id: str, source_branch: str, target_branch: str,
                           title: str, description: str) -> Optional[Dict]:
        """Create a merge request using API."""
        return self.scm_provider.create_merge_request(repo_id, source_branch, target_branch, title, description)

    def cleanup_branch(self, repo_id: str, branch_name: str, default_branch: str) -> bool:
        """Clean up branch using API."""
        return self.scm_provider.delete_branch(repo_id, branch_name)

    def prepare_repository(self, repo_url: str, repo_id: str) -> bool:
        """Prepare repository for API operations (no cloning needed)."""
        # No preparation needed for API strategy
        return True

    def cleanup_repository(self, repo_id: str) -> None:
        """Clean up repository resources (no cleanup needed for API strategy)."""
        pass

    def commit_and_push_changes(self, modified_files: List[str], commit_message: str, branch_name: str) -> bool:
        """For API strategy, files are already committed individually."""
        logging.info(f"API strategy: Files already committed individually for branch {branch_name}")
        return True

    def execute_csharp_migration_tool(self, repo_id: str, rules_file: str, target_files: List[str], branch_name: str):
        """Execute C# migration tool for API strategy by downloading files, processing, and uploading."""
        from src.services.code_migration_service import CodeMigrationService
        import json

        def prefilter_remote_files(files: List[str], rules: List[dict]) -> List[str]:
            """Try to reduce the file set using the provider's code search, if available."""
            try:
                migration_service = CodeMigrationService("./CSharpMigrationTool")
                terms = migration_service.extract_search_terms(rules)
                if not terms:
                    return files

                search_fn = getattr(self.scm_provider, 'search_code_blobs', None)
                if not callable(search_fn):
                    return files

                file_set = set(files)
                matched: set[str] = set()
                for term in terms:
                    for path in search_fn(repo_id, term, ref=branch_name):
                        if path in file_set:
                            matched.add(path)

                return sorted(matched)
            except Exception:
                return files
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Load rules from file
                with open(rules_file, 'r') as f:
                    rules_data = json.load(f)
                rules = rules_data.get('rules', [])

                # Prefilter before downloading to avoid unnecessary API calls/tool runs
                filtered_target_files = prefilter_remote_files(target_files, rules)
                if not filtered_target_files:
                    from src.services.code_migration_service import MigrationResult
                    return MigrationResult(
                        success=True,
                        modified_files=[],
                        applied_rules=[],
                        errors=[],
                        summary="No candidate files matched migration search terms"
                    )

                if len(filtered_target_files) != len(target_files):
                    logging.info(
                        f"Code migration prefilter (API): {len(filtered_target_files)}/{len(target_files)} files selected"
                    )

                # Download all target files
                local_files = []
                local_to_remote: Dict[str, str] = {}
                for file_path in filtered_target_files:
                    content = self.scm_provider.get_file_content(repo_id, file_path, ref=branch_name)
                    if content:
                        # Preserve relative paths to avoid basename collisions
                        local_file_path = os.path.join(temp_dir, file_path)
                        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                        # newline='' disables platform newline translation (critical on Windows)
                        with open(local_file_path, 'w', encoding='utf-8', newline='') as f:
                            f.write(content)
                        local_files.append(local_file_path)
                        local_to_remote[local_file_path] = file_path
                
                # Execute migration tool
                migration_service = CodeMigrationService("./CSharpMigrationTool")
                result = migration_service.execute_migrations(local_files, rules, temp_dir)

                # If migrations succeeded, upload modified files back to the repository while temp_dir exists.
                if result.success and result.modified_files:
                    uploaded_remote_paths: List[str] = []
                    for local_file in result.modified_files:
                        remote_path = local_to_remote.get(local_file)
                        if not remote_path:
                            continue

                        try:
                            content = Path(local_file).read_text(encoding='utf-8', errors='strict', newline='')
                        except Exception as e:
                            logging.error(f"Failed to read migrated temp file {local_file}: {e}")
                            result.success = False
                            result.errors.append(f"Failed to read migrated temp file for {remote_path}: {e}")
                            continue

                        commit_message = f"Apply code migration to {os.path.basename(remote_path)}"
                        ok = self.scm_provider.update_file(repo_id, remote_path, content, commit_message, branch_name)
                        if ok:
                            uploaded_remote_paths.append(remote_path)
                        else:
                            result.success = False
                            result.errors.append(f"Failed to upload migrated file: {remote_path}")
                
                # For API strategy, report the repo paths that were uploaded.
                if result.modified_files:
                    result.modified_files = uploaded_remote_paths if 'uploaded_remote_paths' in locals() else []
                
                return result
                
            except Exception as e:
                logging.error(f"Failed to execute C# migration tool for API strategy: {e}")
                from src.services.code_migration_service import MigrationResult
                return MigrationResult(
                    success=False,
                    modified_files=[],
                    applied_rules=[],
                    errors=[f"API strategy migration failed: {str(e)}"],
                    summary="Migration failed in API strategy"
                )

    def _delete_remote_branch(self, repo_id: str, branch_name: str):
        """Rollback: Delete remote branch via API."""
        try:
            self.scm_provider.delete_branch(repo_id, branch_name)
            logging.info(f"Rollback: Deleted remote branch {branch_name}")
        except Exception as e:
            logging.warning(f"Failed to delete remote branch during rollback: {e}")

    def _revert_file_change(self, repo_id: str, file_path: str, original_content: str, branch_name: str):
        """Rollback: Revert file to original content via API."""
        try:
            self.scm_provider.update_file(
                repo_id, file_path, original_content, 
                "Rollback: Revert file changes", branch_name
            )
            logging.info(f"Rollback: Reverted file {file_path}")
        except Exception as e:
            logging.warning(f"Failed to revert file during rollback: {e}")
