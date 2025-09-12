"""
Unit tests for GitService class.

Tests cover all Git operations:
- Repository cloning
- Branch creation and management
- File staging and commits
- Push operations
- Error handling scenarios
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import git

from src.services.git_service import GitService


class TestGitService:

    @pytest.fixture
    def git_service(self):
        """Create a GitService instance for testing."""
        return GitService("/tmp/test-repo")

    def test_init(self, git_service):
        """Test GitService initialization."""
        assert git_service.local_path == "/tmp/test-repo"
        assert git_service.repo is None

    @patch('git.Repo.clone_from')
    def test_clone_success(self, mock_clone_from, git_service):
        """Test successful repository cloning."""
        mock_repo = Mock()
        mock_clone_from.return_value = mock_repo

        git_service.clone("https://example.com/repo.git")

        mock_clone_from.assert_called_once_with("https://example.com/repo.git", "/tmp/test-repo")
        assert git_service.repo == mock_repo

    @patch('git.Repo.clone_from')
    def test_clone_failure(self, mock_clone_from, git_service):
        """Test repository cloning failure."""
        mock_clone_from.side_effect = git.GitCommandError("clone", "Clone failed")

        with pytest.raises(git.GitCommandError):
            git_service.clone("https://example.com/invalid-repo.git")

        assert git_service.repo is None

    def test_create_branch_no_repo(self, git_service):
        """Test branch creation when no repo is loaded."""
        git_service.create_branch("feature-branch")

        # Should handle gracefully when repo is None
        assert git_service.repo is None

    def test_create_branch_success(self, git_service):
        """Test successful branch creation."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_repo.git = mock_git
        git_service.repo = mock_repo

        git_service.create_branch("feature-branch")

        mock_git.checkout.assert_called_once_with('-b', 'feature-branch')

    def test_create_branch_git_error(self, git_service):
        """Test branch creation with Git error."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_git.checkout.side_effect = git.GitCommandError("checkout", "Branch exists")
        mock_repo.git = mock_git
        git_service.repo = mock_repo

        with pytest.raises(git.GitCommandError):
            git_service.create_branch("existing-branch")

    def test_add_no_repo(self, git_service):
        """Test adding files when no repo is loaded."""
        git_service.add(["file1.txt", "file2.txt"])

        # Should handle gracefully when repo is None
        assert git_service.repo is None

    def test_add_success(self, git_service):
        """Test successful file addition."""
        mock_repo = Mock()
        mock_index = Mock()
        mock_repo.index = mock_index
        git_service.repo = mock_repo

        files = ["file1.txt", "file2.txt"]
        git_service.add(files)

        mock_index.add.assert_called_once_with(files)

    def test_add_empty_list(self, git_service):
        """Test adding empty file list."""
        mock_repo = Mock()
        mock_index = Mock()
        mock_repo.index = mock_index
        git_service.repo = mock_repo

        git_service.add([])

        mock_index.add.assert_called_once_with([])

    def test_add_git_error(self, git_service):
        """Test file addition with Git error."""
        mock_repo = Mock()
        mock_index = Mock()
        mock_index.add.side_effect = git.GitCommandError("add", "File not found")
        mock_repo.index = mock_index
        git_service.repo = mock_repo

        with pytest.raises(git.GitCommandError):
            git_service.add(["nonexistent.txt"])

    def test_commit_no_repo(self, git_service):
        """Test commit when no repo is loaded."""
        git_service.commit("Test commit")

        # Should handle gracefully when repo is None
        assert git_service.repo is None

    def test_commit_success(self, git_service):
        """Test successful commit."""
        mock_repo = Mock()
        mock_index = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "abc123def456"
        mock_index.commit.return_value = mock_commit
        mock_repo.index = mock_index
        git_service.repo = mock_repo

        git_service.commit("Test commit message")

        mock_index.commit.assert_called_once_with("Test commit message")

    def test_commit_empty_message(self, git_service):
        """Test commit with empty message."""
        mock_repo = Mock()
        mock_index = Mock()
        mock_repo.index = mock_index
        git_service.repo = mock_repo

        git_service.commit("")

        mock_index.commit.assert_called_once_with("")

    def test_commit_git_error(self, git_service):
        """Test commit with Git error."""
        mock_repo = Mock()
        mock_index = Mock()
        mock_index.commit.side_effect = git.GitCommandError("commit", "Nothing to commit")
        mock_repo.index = mock_index
        git_service.repo = mock_repo

        with pytest.raises(git.GitCommandError):
            git_service.commit("Test commit")

    def test_push_no_repo(self, git_service):
        """Test push when no repo is loaded."""
        git_service.push("origin", "main")

        # Should handle gracefully when repo is None
        assert git_service.repo is None

    def test_push_success(self, git_service):
        """Test successful push."""
        mock_repo = Mock()
        mock_remote = Mock()
        mock_remotes = {"origin": mock_remote}
        mock_repo.remotes = mock_remotes
        git_service.repo = mock_repo

        git_service.push("origin", "feature-branch")

        mock_remote.push.assert_called_once_with("feature-branch")

    def test_push_nonexistent_remote(self, git_service):
        """Test push to nonexistent remote."""
        mock_repo = Mock()
        mock_remotes = {}
        mock_repo.remotes = mock_remotes
        git_service.repo = mock_repo

        with pytest.raises(KeyError):
            git_service.push("nonexistent", "main")

    def test_push_git_error(self, git_service):
        """Test push with Git error."""
        mock_repo = Mock()
        mock_remote = Mock()
        mock_remote.push.side_effect = git.GitCommandError("push", "Permission denied")
        mock_remotes = {"origin": mock_remote}
        mock_repo.remotes = mock_remotes
        git_service.repo = mock_repo

        with pytest.raises(git.GitCommandError):
            git_service.push("origin", "main")

    def test_workflow_integration(self, git_service):
        """Test complete workflow integration."""
        # Mock the repo and its components
        mock_repo = Mock()
        mock_git = Mock()
        mock_index = Mock()
        mock_remote = Mock()
        mock_commit = Mock()
        mock_commit.hexsha = "abc123"

        mock_repo.git = mock_git
        mock_repo.index = mock_index
        mock_repo.remotes = {"origin": mock_remote}
        mock_index.commit.return_value = mock_commit

        with patch('git.Repo.clone_from', return_value=mock_repo):
            # Execute complete workflow
            git_service.clone("https://example.com/repo.git")
            git_service.create_branch("feature-branch")
            git_service.add(["file1.txt", "file2.txt"])
            git_service.commit("Add new features")
            git_service.push("origin", "feature-branch")

        # Verify all operations were called
        mock_git.checkout.assert_called_once_with('-b', 'feature-branch')
        mock_index.add.assert_called_once_with(["file1.txt", "file2.txt"])
        mock_index.commit.assert_called_once_with("Add new features")
        mock_remote.push.assert_called_once_with("feature-branch")

    def test_multiple_operations_after_clone(self, git_service):
        """Test multiple operations on the same repo instance."""
        mock_repo = Mock()
        mock_git = Mock()
        mock_index = Mock()
        mock_remote = Mock()

        mock_repo.git = mock_git
        mock_repo.index = mock_index
        mock_repo.remotes = {"origin": mock_remote}

        with patch('git.Repo.clone_from', return_value=mock_repo):
            git_service.clone("https://example.com/repo.git")

            # Multiple branch operations
            git_service.create_branch("branch1")
            git_service.create_branch("branch2")

            # Multiple file operations
            git_service.add(["file1.txt"])
            git_service.add(["file2.txt"])

            # Multiple commits
            git_service.commit("First commit")
            git_service.commit("Second commit")

        # Verify all operations used the same repo instance
        assert mock_git.checkout.call_count == 2
        assert mock_index.add.call_count == 2
        assert mock_index.commit.call_count == 2

    @patch('git.Repo.clone_from')
    def test_clone_overwrites_existing_repo(self, mock_clone_from, git_service):
        """Test that cloning overwrites existing repo instance."""
        # First clone
        mock_repo1 = Mock()
        mock_clone_from.return_value = mock_repo1
        git_service.clone("https://example.com/repo1.git")
        assert git_service.repo == mock_repo1

        # Second clone should overwrite
        mock_repo2 = Mock()
        mock_clone_from.return_value = mock_repo2
        git_service.clone("https://example.com/repo2.git")
        assert git_service.repo == mock_repo2
        assert git_service.repo != mock_repo1
