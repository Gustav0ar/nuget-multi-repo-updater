"""
Unit tests for RepositoryManager class.

Tests cover all repository management functionality:
- Loading repositories from files
- Repository filtering by patterns and fork status
- Repository discovery and validation
- Error handling for file operations
- Integration with SCM providers
"""

import pytest
from unittest.mock import Mock, patch, mock_open
import fnmatch

from src.services.repository_manager import RepositoryManager
from src.providers.scm_provider import ScmProvider


class TestRepositoryManager:

    @pytest.fixture
    def mock_scm_provider(self):
        """Create a mock SCM provider."""
        return Mock(spec=ScmProvider)

    @pytest.fixture
    def repository_manager(self, mock_scm_provider):
        """Create a RepositoryManager for testing."""
        return RepositoryManager(mock_scm_provider)

    @pytest.fixture
    def sample_repositories(self):
        """Sample repository data for testing."""
        return [
            {
                'id': 1,
                'name': 'project1',
                'path_with_namespace': 'group/project1',
                'forked_from_project': None
            },
            {
                'id': 2,
                'name': 'test-project',
                'path_with_namespace': 'group/test-project',
                'forked_from_project': None
            },
            {
                'id': 3,
                'name': 'fork-project',
                'path_with_namespace': 'user/fork-project',
                'forked_from_project': {'id': 1}
            },
            {
                'id': 4,
                'name': 'demo-app',
                'path_with_namespace': 'demos/demo-app',
                'forked_from_project': None
            },
            {
                'id': 5,
                'name': 'internal-tool',
                'path_with_namespace': 'internal/internal-tool',
                'forked_from_project': None
            }
        ]

    def test_init(self, repository_manager, mock_scm_provider):
        """Test RepositoryManager initialization."""
        assert repository_manager.scm_provider == mock_scm_provider

    def test_load_repositories_from_file_success(self, repository_manager):
        """Test successful loading of repositories from file."""
        file_content = """
# This is a comment
group/repo1
group/repo2

# Another comment
group/repo3
        """

        with patch('builtins.open', mock_open(read_data=file_content)):
            result = repository_manager.load_repositories_from_file('repos.txt')

        expected = ['group/repo1', 'group/repo2', 'group/repo3']
        assert result == expected

    def test_load_repositories_from_file_empty_file(self, repository_manager):
        """Test loading from empty file."""
        with patch('builtins.open', mock_open(read_data="")):
            result = repository_manager.load_repositories_from_file('empty.txt')

        assert result == []

    def test_load_repositories_from_file_only_comments(self, repository_manager):
        """Test loading from file with only comments."""
        file_content = """
# Comment 1
# Comment 2
        """

        with patch('builtins.open', mock_open(read_data=file_content)):
            result = repository_manager.load_repositories_from_file('comments.txt')

        assert result == []

    def test_load_repositories_from_file_mixed_content(self, repository_manager):
        """Test loading from file with mixed content."""
        file_content = """
# Header comment
group/repo1
  
group/repo2  

# Middle comment
group/repo3
        """

        with patch('builtins.open', mock_open(read_data=file_content)):
            result = repository_manager.load_repositories_from_file('mixed.txt')

        expected = ['group/repo1', 'group/repo2', 'group/repo3']
        assert result == expected

    def test_load_repositories_from_file_not_found(self, repository_manager):
        """Test handling of missing file."""
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            result = repository_manager.load_repositories_from_file('nonexistent.txt')

        assert result == []

    def test_load_repositories_from_file_permission_error(self, repository_manager):
        """Test handling of permission errors."""
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            result = repository_manager.load_repositories_from_file('protected.txt')

        assert result == []

    def test_filter_repositories_no_filters(self, repository_manager, sample_repositories):
        """Test filtering with no patterns or fork exclusion."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns=None,
            exclude_forks=False
        )

        assert result == sample_repositories

    def test_filter_repositories_exclude_forks(self, repository_manager, sample_repositories):
        """Test filtering to exclude forks."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns=None,
            exclude_forks=True
        )

        # Should exclude the fork-project
        expected = [repo for repo in sample_repositories if repo['id'] != 3]
        assert len(result) == 4
        assert all(repo.get('forked_from_project') is None for repo in result)

    def test_filter_repositories_ignore_patterns_by_name(self, repository_manager, sample_repositories):
        """Test filtering by repository name patterns."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="test-*,demo-*",
            exclude_forks=False
        )

        # Should exclude test-project and demo-app
        expected_names = ['project1', 'fork-project', 'internal-tool']
        result_names = [repo['name'] for repo in result]
        assert result_names == expected_names

    def test_filter_repositories_ignore_patterns_by_namespace(self, repository_manager, sample_repositories):
        """Test filtering by namespace patterns."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="demos/*,internal/*",
            exclude_forks=False
        )

        # Should exclude demos/demo-app and internal/internal-tool
        expected_namespaces = ['group/project1', 'group/test-project', 'user/fork-project']
        result_namespaces = [repo['path_with_namespace'] for repo in result]
        assert result_namespaces == expected_namespaces

    def test_filter_repositories_case_insensitive_patterns(self, repository_manager, sample_repositories):
        """Test that pattern matching is case insensitive."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="TEST-*,DEMO-*",
            exclude_forks=False
        )

        # Should exclude test-project and demo-app (case insensitive)
        expected_names = ['project1', 'fork-project', 'internal-tool']
        result_names = [repo['name'] for repo in result]
        assert result_names == expected_names

    def test_filter_repositories_combined_filters(self, repository_manager, sample_repositories):
        """Test combining ignore patterns and fork exclusion."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="test-*",
            exclude_forks=True
        )

        # Should exclude test-project (by pattern) and fork-project (by fork status)
        expected_names = ['project1', 'demo-app', 'internal-tool']
        result_names = [repo['name'] for repo in result]
        assert result_names == expected_names

    def test_filter_repositories_wildcard_patterns(self, repository_manager, sample_repositories):
        """Test various wildcard patterns."""
        # Test single character wildcard
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="project?",
            exclude_forks=False
        )

        # Should exclude project1 (matches project?)
        expected_names = ['test-project', 'fork-project', 'demo-app', 'internal-tool']
        result_names = [repo['name'] for repo in result]
        assert result_names == expected_names

    def test_filter_repositories_complex_patterns(self, repository_manager, sample_repositories):
        """Test complex pattern combinations."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="*test*,*demo*,*fork*",
            exclude_forks=False
        )

        # Should exclude anything with test, demo, or fork in the name
        expected_names = ['project1', 'internal-tool']
        result_names = [repo['name'] for repo in result]
        assert result_names == expected_names

    def test_filter_repositories_empty_patterns(self, repository_manager, sample_repositories):
        """Test filtering with empty pattern string."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="",
            exclude_forks=False
        )

        assert result == sample_repositories

    def test_filter_repositories_whitespace_patterns(self, repository_manager, sample_repositories):
        """Test filtering with whitespace in patterns."""
        result = repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="  test-* , demo-*  ",
            exclude_forks=False
        )

        # Should properly strip whitespace and apply patterns
        expected_names = ['project1', 'fork-project', 'internal-tool']
        result_names = [repo['name'] for repo in result]
        assert result_names == expected_names

    def test_filter_repositories_by_patterns_method(self, repository_manager, sample_repositories):
        """Test the filter_repositories_by_patterns method specifically."""
        patterns = ['test-*', 'demo-*']

        result = repository_manager.filter_repositories_by_patterns(
            sample_repositories,
            patterns
        )

        expected_names = ['project1', 'fork-project', 'internal-tool']
        result_names = [repo['name'] for repo in result]
        assert result_names == expected_names

    def test_filter_repositories_by_patterns_empty_list(self, repository_manager, sample_repositories):
        """Test filtering with empty pattern list."""
        result = repository_manager.filter_repositories_by_patterns(
            sample_repositories,
            []
        )

        assert result == sample_repositories

    def test_filter_repositories_by_patterns_none_input(self, repository_manager, sample_repositories):
        """Test filtering with None pattern list."""
        result = repository_manager.filter_repositories_by_patterns(
            sample_repositories,
            None
        )

        assert result == sample_repositories

    def test_repository_data_integrity(self, repository_manager, sample_repositories):
        """Test that filtering doesn't modify original repository data."""
        original_data = [repo.copy() for repo in sample_repositories]

        repository_manager.filter_repositories(
            sample_repositories,
            ignore_patterns="test-*",
            exclude_forks=True
        )

        # Original data should be unchanged
        assert sample_repositories == original_data

    def test_filter_repositories_missing_fields(self, repository_manager):
        """Test filtering with repositories missing expected fields."""
        repos_with_missing_fields = [
            {
                'id': 1,
                'name': 'project1',
                'path_with_namespace': 'group/project1'
                # Missing forked_from_project field
            },
            {
                'id': 2,
                'name': 'project2'
                # Missing path_with_namespace and forked_from_project
            }
        ]

        # Should not crash and handle missing fields gracefully
        result = repository_manager.filter_repositories(
            repos_with_missing_fields,
            ignore_patterns="project*",
            exclude_forks=True
        )

        # All should be filtered out by pattern
        assert len(result) == 0

    def test_filter_repositories_special_characters_in_names(self, repository_manager):
        """Test filtering with special characters in repository names."""
        special_repos = [
            {
                'id': 1,
                'name': 'my-project@2024',
                'path_with_namespace': 'group/my-project@2024',
                'forked_from_project': None
            },
            {
                'id': 2,
                'name': 'project.with.dots',
                'path_with_namespace': 'group/project.with.dots',
                'forked_from_project': None
            }
        ]

        result = repository_manager.filter_repositories(
            special_repos,
            ignore_patterns="*@*",
            exclude_forks=False
        )

        # Should exclude the project with @ in name
        assert len(result) == 1
        assert result[0]['name'] == 'project.with.dots'
