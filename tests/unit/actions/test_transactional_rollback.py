from unittest.mock import Mock, patch

import pytest

from src.actions.multi_package_update_action import MultiPackageUpdateAction
from src.services.code_migration_service import MigrationResult
from src.services.rollback_service import TransactionException


def test_api_mode_migration_failure_rolls_back_and_does_not_create_mr():
    scm = Mock()
    scm.check_existing_merge_request.return_value = None
    scm.create_branch.return_value = True
    scm.delete_branch.return_value = True

    action = MultiPackageUpdateAction(
        git_service=Mock(),
        scm_provider=scm,
        packages=[{"name": "X", "version": "1.2.3"}],
        use_local_clone=False,
        enable_migrations=True,
        strict_migration_mode=False,
        migration_config_service=Mock(),
    )

    with patch.object(action, "_generate_branch_name", return_value="feature/test"), \
         patch.object(action, "_generate_mr_title", return_value="MR"), \
         patch.object(action.strategy, "prepare_repository", return_value=True), \
         patch.object(action.strategy, "find_target_files", return_value=["a.csproj"]), \
         patch.object(action, "_execute_package_updates", return_value={
             "success": True,
             "updated_packages": [{"name": "X", "version": "1.2.3"}],
             "modified_files": ["a.csproj"],
         }), \
         patch.object(action, "_execute_code_migrations", return_value=MigrationResult(
             success=False,
             modified_files=[],
             applied_rules=[],
             errors=["boom"],
             summary="failed",
         )), \
         patch.object(action.strategy, "create_merge_request", return_value={"iid": 1}) as create_mr:

        with pytest.raises(TransactionException):
            action.execute(repo_url="url", repo_id="proj", default_branch="main")

        create_mr.assert_not_called()
        scm.delete_branch.assert_called_once_with("proj", "feature/test")
