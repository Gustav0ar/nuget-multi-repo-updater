"""
Unit tests for GitLabProvider and related classes.

Tests cover all business logic for:
- Rate limiting functionality
- API retry handling with exponential backoff
- GitLab API operations (projects, merge requests, repositories, etc.)
- Error handling and recovery scenarios
- Authentication and SSL handling
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
import requests
import base64
from urllib.parse import quote

from src.providers.gitlab_provider import (
    GitLabProvider,
    RateLimiter,
    APIRetryHandler,
    RateLimitExceeded
)


class TestRateLimitExceeded:

    def test_init_with_message_only(self):
        """Test RateLimitExceeded initialization with message only."""
        exception = RateLimitExceeded("Rate limit exceeded")

        assert str(exception) == "Rate limit exceeded"
        assert exception.retry_after is None

    def test_init_with_retry_after(self):
        """Test RateLimitExceeded initialization with retry_after."""
        exception = RateLimitExceeded("Rate limit exceeded", retry_after=60)

        assert str(exception) == "Rate limit exceeded"
        assert exception.retry_after == 60


class TestRateLimiter:

    @pytest.fixture
    def rate_limiter(self):
        """Create a RateLimiter for testing."""
        return RateLimiter(requests_per_minute=60, burst_limit=5)

    def test_init(self, rate_limiter):
        """Test RateLimiter initialization."""
        assert rate_limiter.requests_per_minute == 60
        assert rate_limiter.burst_limit == 5
        assert rate_limiter.min_delay == 1.0  # 60/60
        assert rate_limiter.request_times == []
        assert rate_limiter.burst_count == 0
        assert rate_limiter.last_request_time == 0

    def test_init_zero_requests_per_minute(self):
        """Test initialization with zero requests per minute."""
        limiter = RateLimiter(requests_per_minute=0)
        assert limiter.min_delay == 0.1  # Default fallback

    @patch('time.time')
    @patch('time.sleep')
    def test_wait_if_needed_no_previous_requests(self, mock_sleep, mock_time, rate_limiter):
        """Test wait_if_needed with no previous requests."""
        mock_time.return_value = 100.0

        rate_limiter.wait_if_needed()

        mock_sleep.assert_not_called()
        assert len(rate_limiter.request_times) == 1
        assert rate_limiter.last_request_time == 100.0

    @patch('time.time')
    @patch('time.sleep')
    def test_wait_if_needed_approaching_rate_limit(self, mock_sleep, mock_time, rate_limiter):
        """Test waiting when approaching rate limit."""
        current_time = 100.0
        mock_time.return_value = current_time

        # Fill request_times to 90% of limit (54 out of 60)
        rate_limiter.request_times = [current_time - 59 + i for i in range(54)]

        rate_limiter.wait_if_needed()

        # Should wait for the oldest request to age out
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] > 0

    @patch('time.time')
    @patch('time.sleep')
    def test_wait_if_needed_burst_limit(self, mock_sleep, mock_time, rate_limiter):
        """Test burst limiting functionality."""
        # Provide enough time values for all the calls that will be made
        time_values = [100.0 + i * 0.1 for i in range(20)]  # Generate enough values
        mock_time.side_effect = time_values

        # Make requests rapidly to trigger burst limit
        for i in range(6):  # One more than burst_limit
            rate_limiter.wait_if_needed()

        # Should have triggered burst limiting on the 6th request
        mock_sleep.assert_called()

    @patch('time.time')
    @patch('time.sleep')
    def test_wait_if_needed_minimum_delay(self, mock_sleep, mock_time, rate_limiter):
        """Test minimum delay enforcement."""
        # Provide enough time values for all the calls that will be made
        mock_time.side_effect = [100.0, 100.0, 100.5, 100.5, 101.0, 101.0]

        rate_limiter.wait_if_needed()  # First request
        rate_limiter.wait_if_needed()  # Second request too soon

        # The actual implementation enforces the full min_delay
        mock_sleep.assert_called_with(1.0)  # min_delay value

    @patch('time.time')
    def test_cleanup_old_requests(self, mock_time, rate_limiter):
        """Test cleanup of old request times."""
        current_time = 200.0
        mock_time.return_value = current_time

        # Add some old and recent request times
        rate_limiter.request_times = [
            current_time - 120,  # 2 minutes ago (should be removed)
            current_time - 90,   # 1.5 minutes ago (should be removed)
            current_time - 30,   # 30 seconds ago (should remain)
            current_time - 10    # 10 seconds ago (should remain)
        ]

        rate_limiter.wait_if_needed()

        # Should only keep requests from the last minute
        assert len([t for t in rate_limiter.request_times if t > current_time - 60]) == 3  # 2 old + 1 new


class TestAPIRetryHandler:

    @pytest.fixture
    def retry_handler(self):
        """Create an APIRetryHandler for testing."""
        return APIRetryHandler(max_retries=3, base_delay=0.1, max_delay=1.0)

    def test_init(self, retry_handler):
        """Test APIRetryHandler initialization."""
        assert retry_handler.max_retries == 3
        assert retry_handler.base_delay == 0.1
        assert retry_handler.max_delay == 1.0

    def test_execute_with_retry_success_first_attempt(self, retry_handler):
        """Test successful execution on first attempt."""
        mock_func = Mock(return_value="success")

        result = retry_handler.execute_with_retry(mock_func, "arg1", kwarg1="value1")

        assert result == "success"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    @patch('time.sleep')
    def test_execute_with_retry_429_error_with_retry_after(self, mock_sleep, retry_handler):
        """Test handling 429 error with Retry-After header."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '5'}

        mock_exception = requests.RequestException()
        mock_exception.response = mock_response

        mock_func = Mock(side_effect=[mock_exception, "success"])

        result = retry_handler.execute_with_retry(mock_func)

        assert result == "success"
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(1.0)  # Limited by max_delay

    @patch('time.sleep')
    def test_execute_with_retry_server_error(self, mock_sleep, retry_handler):
        """Test handling server errors (5xx)."""
        mock_response = Mock()
        mock_response.status_code = 500

        mock_exception = requests.RequestException()
        mock_exception.response = mock_response

        mock_func = Mock(side_effect=[mock_exception, "success"])

        result = retry_handler.execute_with_retry(mock_func)

        assert result == "success"
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once_with(0.1)  # base_delay

    @patch('time.sleep')
    def test_execute_with_retry_network_errors(self, mock_sleep, retry_handler):
        """Test handling network errors (502, 503, 504)."""
        for status_code in [502, 503, 504]:
            mock_response = Mock()
            mock_response.status_code = status_code

            mock_exception = requests.RequestException()
            mock_exception.response = mock_response

            mock_func = Mock(side_effect=[mock_exception, "success"])

            result = retry_handler.execute_with_retry(mock_func)

            assert result == "success"
            assert mock_func.call_count == 2
            mock_sleep.assert_called_with(0.1)

            # Reset mocks for next iteration
            mock_func.reset_mock()
            mock_sleep.reset_mock()

    def test_execute_with_retry_non_recoverable_error(self, retry_handler):
        """Test handling non-recoverable errors."""
        mock_response = Mock()
        mock_response.status_code = 404

        mock_exception = requests.RequestException()
        mock_exception.response = mock_response

        mock_func = Mock(side_effect=mock_exception)

        with pytest.raises(requests.RequestException):
            retry_handler.execute_with_retry(mock_func)

        # The retry handler tries all retries even for non-recoverable errors
        assert mock_func.call_count == 4  # Initial + 3 retries

    @patch('time.sleep')
    def test_execute_with_retry_max_retries_exceeded(self, mock_sleep, retry_handler):
        """Test behavior when max retries are exceeded."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {}

        mock_exception = requests.RequestException()
        mock_exception.response = mock_response

        mock_func = Mock(side_effect=mock_exception)

        with pytest.raises(RateLimitExceeded):
            retry_handler.execute_with_retry(mock_func)

        assert mock_func.call_count == 4  # Initial + 3 retries

    def test_get_retry_after_valid_header(self, retry_handler):
        """Test extracting valid Retry-After header."""
        mock_response = Mock()
        mock_response.headers = {'Retry-After': '30'}

        result = retry_handler._get_retry_after(mock_response)

        assert result == 30

    def test_get_retry_after_invalid_header(self, retry_handler):
        """Test handling invalid Retry-After header."""
        mock_response = Mock()
        mock_response.headers = {'Retry-After': 'invalid'}

        result = retry_handler._get_retry_after(mock_response)

        assert result is None

    def test_get_retry_after_missing_header(self, retry_handler):
        """Test handling missing Retry-After header."""
        mock_response = Mock()
        mock_response.headers = {}

        result = retry_handler._get_retry_after(mock_response)

        assert result is None

    @patch('builtins.input', return_value='1')
    def test_ask_user_continue_yes(self, mock_input, retry_handler):
        """Test user choosing to continue."""
        result = retry_handler._ask_user_continue(120.0)

        assert result is True
        mock_input.assert_called()

    @patch('builtins.input', return_value='2')
    def test_ask_user_continue_no(self, mock_input, retry_handler):
        """Test user choosing to cancel."""
        result = retry_handler._ask_user_continue(120.0)

        assert result is False
        mock_input.assert_called()

    @patch('builtins.input', side_effect=['invalid', '3', '1'])
    def test_ask_user_continue_invalid_then_valid(self, mock_input, retry_handler):
        """Test handling invalid input then valid choice."""
        result = retry_handler._ask_user_continue(120.0)

        assert result is True
        assert mock_input.call_count == 3

    @patch('builtins.input', side_effect=KeyboardInterrupt())
    def test_ask_user_continue_keyboard_interrupt(self, mock_input, retry_handler):
        """Test handling keyboard interrupt."""
        result = retry_handler._ask_user_continue(120.0)

        assert result is False


class TestGitLabProvider:

    @pytest.fixture
    def gitlab_provider(self):
        """Create a GitLabProvider for testing."""
        return GitLabProvider(
            gitlab_url="https://gitlab.example.com",
            access_token="test-token",
            verify_ssl=True
        )

    def test_init(self, gitlab_provider):
        """Test GitLabProvider initialization."""
        assert gitlab_provider.gitlab_url == "https://gitlab.example.com"
        assert gitlab_provider.access_token == "test-token"
        assert gitlab_provider.verify_ssl is True
        assert "Bearer test-token" in gitlab_provider.headers['Authorization']
        assert isinstance(gitlab_provider.rate_limiter, RateLimiter)
        assert isinstance(gitlab_provider.retry_handler, APIRetryHandler)

    def test_init_url_trailing_slash_removal(self):
        """Test URL trailing slash removal."""
        provider = GitLabProvider(
            gitlab_url="https://gitlab.example.com/",
            access_token="test-token"
        )
        assert provider.gitlab_url == "https://gitlab.example.com"

    @patch('urllib3.disable_warnings')
    def test_init_ssl_verification_disabled(self, mock_disable_warnings):
        """Test initialization with SSL verification disabled."""
        provider = GitLabProvider(
            gitlab_url="https://gitlab.example.com",
            access_token="test-token",
            verify_ssl=False
        )

        assert provider.verify_ssl is False
        assert provider.session.verify is False
        mock_disable_warnings.assert_called_once()

    @patch('requests.Session.get')
    def test_make_request_success(self, mock_get, gitlab_provider):
        """Test successful API request."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": 1, "name": "test"}
        mock_get.return_value = mock_response

        response = gitlab_provider._make_request('get', 'https://test.com/api')

        assert response == mock_response
        mock_get.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @patch('requests.Session.get')
    def test_make_request_with_rate_limiting(self, mock_get, gitlab_provider):
        """Test API request with rate limiting."""
        mock_response = Mock()
        mock_get.return_value = mock_response

        with patch.object(gitlab_provider.rate_limiter, 'wait_if_needed') as mock_wait:
            gitlab_provider._make_request('get', 'https://test.com/api')

            mock_wait.assert_called_once()

    @patch('requests.Session.get')
    def test_get_project_success(self, mock_get, gitlab_provider):
        """Test successful project retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 123,
            "name": "test-project",
            "path_with_namespace": "group/test-project"
        }
        mock_get.return_value = mock_response

        result = gitlab_provider.get_project("group/test-project")

        assert result["id"] == 123
        assert result["name"] == "test-project"

        # Verify URL encoding
        expected_url = "https://gitlab.example.com/api/v4/projects/group%2Ftest-project"
        mock_get.assert_called_once_with(expected_url)

    @patch('requests.Session.get')
    def test_get_project_not_found(self, mock_get, gitlab_provider):
        """Test project retrieval when project doesn't exist."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        result = gitlab_provider.get_project("nonexistent/project")

        assert result is None

    @patch('requests.Session.get')
    def test_get_project_rate_limit_exceeded(self, mock_get, gitlab_provider):
        """Test project retrieval with rate limit exceeded."""
        mock_get.side_effect = RateLimitExceeded("Rate limit exceeded")

        result = gitlab_provider.get_project("group/project")

        assert result is None

    def test_url_encoding_special_characters(self, gitlab_provider):
        """Test URL encoding handles special characters correctly."""
        # Test with project path containing special characters
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"id": 1}
            mock_get.return_value = mock_response

            gitlab_provider.get_project("group/project-with-special@chars")

            # Verify proper URL encoding
            expected_url = "https://gitlab.example.com/api/v4/projects/group%2Fproject-with-special%40chars"
            mock_get.assert_called_once_with(expected_url)

    @patch('requests.Session.get')
    def test_get_repository_tree_success(self, mock_get, gitlab_provider):
        """Test successful repository tree retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"name": "file1.txt", "type": "blob", "path": "file1.txt"},
            {"name": "dir1", "type": "tree", "path": "dir1"}
        ]
        mock_get.return_value = mock_response

        result = gitlab_provider.get_repository_tree("group/project")

        assert len(result) == 2
        assert result[0]["name"] == "file1.txt"
        assert result[1]["name"] == "dir1"

    @patch('requests.Session.get')
    def test_get_repository_tree_pagination(self, mock_get, gitlab_provider):
        """Test repository tree retrieval with pagination."""
        # First page - full 100 items
        page1_response = Mock()
        page1_response.json.return_value = [{"name": f"file{i}.txt"} for i in range(100)]

        # Second page - partial items (indicates last page)
        page2_response = Mock()
        page2_response.json.return_value = [{"name": f"file{i}.txt"} for i in range(100, 150)]

        mock_get.side_effect = [page1_response, page2_response]

        result = gitlab_provider.get_repository_tree("group/project")

        assert len(result) == 150
        assert mock_get.call_count == 2

    @patch('requests.Session.get')
    def test_get_file_content_success(self, mock_get, gitlab_provider):
        """Test successful file content retrieval."""
        content = "Hello, World!"
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

        mock_response = Mock()
        mock_response.json.return_value = {"content": encoded_content}
        mock_get.return_value = mock_response

        result = gitlab_provider.get_file_content("group/project", "README.md")

        assert result == content

    @patch('requests.Session.get')
    def test_get_file_content_not_found(self, mock_get, gitlab_provider):
        """Test file content retrieval when file doesn't exist."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        result = gitlab_provider.get_file_content("group/project", "nonexistent.txt")

        assert result is None

    @patch('requests.Session.post')
    def test_create_merge_request_success(self, mock_post, gitlab_provider):
        """Test successful merge request creation."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 456,
            "iid": 1,
            "web_url": "https://gitlab.example.com/group/project/-/merge_requests/1",
            "title": "Test MR"
        }
        mock_post.return_value = mock_response

        result = gitlab_provider.create_merge_request(
            "group/project", "feature-branch", "main", "Test MR", "Test description"
        )

        assert result["id"] == 456
        assert result["title"] == "Test MR"

        # Verify the request data
        call_args = mock_post.call_args
        assert call_args[1]['json']['source_branch'] == 'feature-branch'
        assert call_args[1]['json']['target_branch'] == 'main'
        assert call_args[1]['json']['title'] == 'Test MR'
        assert call_args[1]['json']['description'] == 'Test description'
        assert call_args[1]['json']['remove_source_branch'] is True

    @patch('requests.Session.get')
    def test_get_merge_request_status_success(self, mock_get, gitlab_provider):
        """Test successful merge request status retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {"state": "opened"}
        mock_get.return_value = mock_response

        result = gitlab_provider.get_merge_request_status("group/project", "1")

        assert result == "opened"

    @patch('requests.Session.get')
    def test_discover_repositories_success(self, mock_get, gitlab_provider):
        """Test successful repository discovery."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"id": 1, "name": "project1", "path_with_namespace": "group/project1"},
            {"id": 2, "name": "project2", "path_with_namespace": "group/project2"}
        ]
        mock_get.return_value = mock_response

        result = gitlab_provider.discover_repositories()

        assert len(result) == 2
        assert result[0]["name"] == "project1"
        assert result[1]["name"] == "project2"

    @patch('requests.Session.get')
    def test_discover_repositories_with_group(self, mock_get, gitlab_provider):
        """Test repository discovery for specific group."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1, "name": "project1"}]
        mock_get.return_value = mock_response

        result = gitlab_provider.discover_repositories(group_id="mygroup")

        # Verify it uses the groups API endpoint
        expected_url = "https://gitlab.example.com/api/v4/groups/mygroup/projects"
        mock_get.assert_called()
        assert expected_url in mock_get.call_args[0][0]

    @patch('requests.Session.get')
    def test_discover_repositories_with_filters(self, mock_get, gitlab_provider):
        """Test repository discovery with ownership and membership filters."""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        gitlab_provider.discover_repositories(owned=True, membership=False, archived=True)

        # Verify parameters are passed correctly
        call_args = mock_get.call_args
        params = call_args[1]['params']
        assert params['owned'] is True
        assert params['membership'] is False
        assert params['archived'] is True

    @patch('requests.Session.get')
    def test_check_existing_merge_request_found(self, mock_get, gitlab_provider):
        """Test checking for existing merge request when one exists."""
        # Mock the get_merge_requests call
        with patch.object(gitlab_provider, 'get_merge_requests') as mock_get_mrs:
            mock_get_mrs.return_value = [
                {"title": "Update package", "web_url": "https://example.com/mr/1"},
                {"title": "Fix bug", "web_url": "https://example.com/mr/2"}
            ]

            result = gitlab_provider.check_existing_merge_request(
                "group/project", "Update package"
            )

            assert result is not None
            assert result["title"] == "Update package"

    @patch('requests.Session.get')
    def test_check_existing_merge_request_not_found(self, mock_get, gitlab_provider):
        """Test checking for existing merge request when none exists."""
        with patch.object(gitlab_provider, 'get_merge_requests') as mock_get_mrs:
            mock_get_mrs.return_value = [
                {"title": "Different title", "web_url": "https://example.com/mr/1"}
            ]

            result = gitlab_provider.check_existing_merge_request(
                "group/project", "Update package"
            )

            assert result is None

    def test_session_configuration(self, gitlab_provider):
        """Test that session is properly configured."""
        session = gitlab_provider.session

        assert 'Authorization' in session.headers
        assert session.headers['Authorization'] == 'Bearer test-token'
        assert session.headers['Content-Type'] == 'application/json'
        assert session.verify is True

    def test_rate_limiter_integration(self, gitlab_provider):
        """Test rate limiter is properly integrated."""
        assert isinstance(gitlab_provider.rate_limiter, RateLimiter)
        assert gitlab_provider.rate_limiter.requests_per_minute == 600
        assert gitlab_provider.rate_limiter.burst_limit == 10

    def test_retry_handler_integration(self, gitlab_provider):
        """Test retry handler is properly integrated."""
        assert isinstance(gitlab_provider.retry_handler, APIRetryHandler)
        assert gitlab_provider.retry_handler.max_retries == 3
        assert gitlab_provider.retry_handler.max_delay == 300.0

    @patch('requests.Session.get')
    def test_error_logging_on_api_failure(self, mock_get, gitlab_provider):
        """Test that errors are properly logged when API calls fail."""
        mock_get.side_effect = requests.RequestException("Network error")

        with patch('src.providers.gitlab_provider.logging') as mock_logging:
            result = gitlab_provider.get_project("group/project")

            assert result is None
            mock_logging.error.assert_called()

    def test_file_path_encoding(self, gitlab_provider):
        """Test that file paths are properly URL encoded."""
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"content": ""}
            mock_get.return_value = mock_response

            gitlab_provider.get_file_content("group/project", "path/with spaces/file.txt")

            # Verify the file path is URL encoded in the API call
            call_args = mock_get.call_args[0][0]
            assert "path%2Fwith%20spaces%2Ffile.txt" in call_args

    @patch('requests.Session.get')
    def test_list_branches_success(self, mock_get, gitlab_provider):
        """Test successful branch listing."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "name": "main",
                "commit": {
                    "id": "abc123",
                    "committed_date": "2024-03-15T10:30:00.000Z"
                }
            },
            {
                "name": "develop",
                "commit": {
                    "id": "def456",
                    "committed_date": "2024-03-14T09:15:00.000Z"
                }
            }
        ]
        mock_get.return_value = mock_response

        result = gitlab_provider.list_branches("group/project")

        assert len(result) == 2
        assert result[0]["name"] == "main"
        assert result[1]["name"] == "develop"
        mock_get.assert_called_once()

    @patch('requests.Session.get')
    def test_list_branches_pagination(self, mock_get, gitlab_provider):
        """Test branch listing with pagination."""
        # First page - full 100 items
        page1_response = Mock()
        page1_response.json.return_value = [{"name": f"branch{i}"} for i in range(100)]

        # Second page - partial items (indicates last page)
        page2_response = Mock()
        page2_response.json.return_value = [{"name": f"branch{i}"} for i in range(100, 120)]

        mock_get.side_effect = [page1_response, page2_response]

        result = gitlab_provider.list_branches("group/project")

        assert len(result) == 120
        assert mock_get.call_count == 2

    @patch('requests.Session.get')
    def test_list_branches_error_handling(self, mock_get, gitlab_provider):
        """Test branch listing error handling."""
        mock_get.side_effect = requests.RequestException("Network error")

        result = gitlab_provider.list_branches("group/project")

        assert result == []

    @patch('requests.Session.get')
    def test_get_most_recent_branch_success(self, mock_get, gitlab_provider):
        """Test getting most recent branch successfully."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "name": "main",
                "commit": {
                    "committed_date": "2024-03-15T10:30:00.000Z"
                }
            },
            {
                "name": "develop",
                "commit": {
                    "committed_date": "2024-03-16T11:45:00.000Z"  # More recent
                }
            },
            {
                "name": "feature-branch",
                "commit": {
                    "committed_date": "2024-03-14T09:15:00.000Z"
                }
            }
        ]
        mock_get.return_value = mock_response

        result = gitlab_provider.get_most_recent_branch("group/project")

        assert result == "develop"

    @patch('requests.Session.get')
    def test_get_most_recent_branch_with_filter(self, mock_get, gitlab_provider):
        """Test getting most recent branch with filter."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "name": "main",
                "commit": {
                    "committed_date": "2024-03-15T10:30:00.000Z"
                }
            },
            {
                "name": "hotfix-main",
                "commit": {
                    "committed_date": "2024-03-16T11:45:00.000Z"  # More recent, matches filter
                }
            },
            {
                "name": "develop",
                "commit": {
                    "committed_date": "2024-03-17T12:00:00.000Z"  # Most recent, but doesn't match filter
                }
            }
        ]
        mock_get.return_value = mock_response

        result = gitlab_provider.get_most_recent_branch("group/project", "*main*")

        assert result == "hotfix-main"

    @patch('requests.Session.get')
    def test_get_most_recent_branch_no_matches(self, mock_get, gitlab_provider):
        """Test getting most recent branch when no branches match filter."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "name": "develop",
                "commit": {
                    "committed_date": "2024-03-15T10:30:00.000Z"
                }
            },
            {
                "name": "feature-branch",
                "commit": {
                    "committed_date": "2024-03-16T11:45:00.000Z"
                }
            }
        ]
        mock_get.return_value = mock_response

        result = gitlab_provider.get_most_recent_branch("group/project", "*main*")

        assert result is None

    @patch('requests.Session.get')
    def test_get_most_recent_branch_no_branches(self, mock_get, gitlab_provider):
        """Test getting most recent branch when no branches exist."""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = gitlab_provider.get_most_recent_branch("group/project")

        assert result is None

    @patch('requests.Session.get')
    def test_get_most_recent_branch_invalid_date(self, mock_get, gitlab_provider):
        """Test getting most recent branch with invalid commit dates."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "name": "main",
                "commit": {
                    "committed_date": "invalid-date"
                }
            },
            {
                "name": "develop",
                "commit": {
                    "committed_date": "2024-03-16T11:45:00.000Z"
                }
            }
        ]
        mock_get.return_value = mock_response

        result = gitlab_provider.get_most_recent_branch("group/project")

        assert result == "develop"  # Should skip the invalid date and return the valid one
