import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from src.strategies.local_clone_strategy import LocalCloneStrategy
from src.services.git_service import GitService
from src.providers.gitlab_provider import GitLabProvider


class TestLocalCloneStrategy:
    """Test suite for LocalCloneStrategy."""

    @pytest.fixture
    def mock_git_service(self):
        """Mock GitService for testing."""
        return Mock(spec=GitService)

    @pytest.fixture
    def mock_scm_provider(self):
        """Mock SCM provider for testing."""
        return Mock(spec=GitLabProvider)

    @pytest.fixture
    def strategy(self, mock_git_service, mock_scm_provider):
        """Create LocalCloneStrategy instance with mocked dependencies."""
        return LocalCloneStrategy(mock_git_service, mock_scm_provider)

    def test_cleanup_branch_successful_cleanup(self, strategy, mock_git_service, mock_scm_provider):
        """Test successful cleanup of both local and remote branches."""
        # Setup mocks
        mock_git_service.get_current_branch.return_value = "feature-branch"
        mock_git_service.branch_exists.return_value = True
        mock_scm_provider.branch_exists.return_value = True
        mock_scm_provider.delete_branch.return_value = True

        # Execute cleanup
        result = strategy.cleanup_branch("123", "feature-branch", "main")

        # Verify results
        assert result is True
        mock_git_service.get_current_branch.assert_called_once()
        mock_git_service.checkout_branch.assert_called_once_with("main")
        mock_git_service.branch_exists.assert_called_once_with("feature-branch")
        mock_git_service.delete_branch.assert_called_once_with("feature-branch")
        mock_scm_provider.branch_exists.assert_called_once_with("123", "feature-branch")
        mock_scm_provider.delete_branch.assert_called_once_with("123", "feature-branch")

    def test_cleanup_branch_not_on_branch_to_delete(self, strategy, mock_git_service, mock_scm_provider):
        """Test cleanup when not currently on the branch being deleted."""
        # Setup mocks
        mock_git_service.get_current_branch.return_value = "main"
        mock_git_service.branch_exists.return_value = True
        mock_scm_provider.branch_exists.return_value = True
        mock_scm_provider.delete_branch.return_value = True

        # Execute cleanup
        result = strategy.cleanup_branch("123", "feature-branch", "main")

        # Verify results
        assert result is True
        mock_git_service.get_current_branch.assert_called_once()
        mock_git_service.checkout_branch.assert_not_called()  # Should not switch branches
        mock_git_service.branch_exists.assert_called_once_with("feature-branch")
        mock_git_service.delete_branch.assert_called_once_with("feature-branch")
        mock_scm_provider.branch_exists.assert_called_once_with("123", "feature-branch")
        mock_scm_provider.delete_branch.assert_called_once_with("123", "feature-branch")

    def test_cleanup_branch_local_branch_not_exists(self, strategy, mock_git_service, mock_scm_provider):
        """Test cleanup when local branch doesn't exist."""
        # Setup mocks
        mock_git_service.get_current_branch.return_value = "main"
        mock_git_service.branch_exists.return_value = False
        mock_scm_provider.branch_exists.return_value = True
        mock_scm_provider.delete_branch.return_value = True

        # Execute cleanup
        result = strategy.cleanup_branch("123", "feature-branch", "main")

        # Verify results
        assert result is True
        mock_git_service.get_current_branch.assert_called_once()
        mock_git_service.checkout_branch.assert_not_called()
        mock_git_service.branch_exists.assert_called_once_with("feature-branch")
        mock_git_service.delete_branch.assert_not_called()  # Should not try to delete non-existent local branch
        mock_scm_provider.branch_exists.assert_called_once_with("123", "feature-branch")
        mock_scm_provider.delete_branch.assert_called_once_with("123", "feature-branch")

    def test_cleanup_branch_remote_branch_not_exists(self, strategy, mock_git_service, mock_scm_provider):
        """Test cleanup when remote branch doesn't exist."""
        # Setup mocks
        mock_git_service.get_current_branch.return_value = "main"
        mock_git_service.branch_exists.return_value = True
        mock_scm_provider.branch_exists.return_value = False

        # Execute cleanup
        result = strategy.cleanup_branch("123", "feature-branch", "main")

        # Verify results
        assert result is True
        mock_git_service.get_current_branch.assert_called_once()
        mock_git_service.checkout_branch.assert_not_called()
        mock_git_service.branch_exists.assert_called_once_with("feature-branch")
        mock_git_service.delete_branch.assert_called_once_with("feature-branch")
        mock_scm_provider.branch_exists.assert_called_once_with("123", "feature-branch")
        mock_scm_provider.delete_branch.assert_not_called()  # Should not try to delete non-existent remote branch

    def test_cleanup_branch_git_service_failure(self, strategy, mock_git_service, mock_scm_provider):
        """Test cleanup when git service operations fail."""
        # Setup mocks to raise exceptions
        mock_git_service.get_current_branch.return_value = "feature-branch"
        mock_git_service.checkout_branch.side_effect = Exception("Git checkout failed")

        # Execute cleanup
        result = strategy.cleanup_branch("123", "feature-branch", "main")

        # Verify results
        assert result is False
        mock_git_service.get_current_branch.assert_called_once()
        mock_git_service.checkout_branch.assert_called_once_with("main")

    def test_cleanup_branch_scm_provider_failure(self, strategy, mock_git_service, mock_scm_provider):
        """Test cleanup when SCM provider operations fail."""
        # Setup mocks
        mock_git_service.get_current_branch.return_value = "main"
        mock_git_service.branch_exists.return_value = True
        mock_scm_provider.branch_exists.return_value = True
        mock_scm_provider.delete_branch.side_effect = Exception("SCM delete failed")

        # Execute cleanup
        result = strategy.cleanup_branch("123", "feature-branch", "main")

        # Verify results
        assert result is False
        mock_git_service.get_current_branch.assert_called_once()
        mock_git_service.checkout_branch.assert_not_called()
        mock_git_service.branch_exists.assert_called_once_with("feature-branch")
        mock_git_service.delete_branch.assert_called_once_with("feature-branch")
        mock_scm_provider.branch_exists.assert_called_once_with("123", "feature-branch")
        mock_scm_provider.delete_branch.assert_called_once_with("123", "feature-branch")