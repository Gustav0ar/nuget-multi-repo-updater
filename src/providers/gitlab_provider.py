import base64
import logging
import time
from typing import List, Dict, Optional
from urllib.parse import quote

import requests

from src.providers.scm_provider import ScmProvider


class RateLimitExceeded(Exception):
    """Exception raised when API rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimiter:
    """Rate limiter to prevent API overload and handle 429 errors gracefully."""

    def __init__(self, requests_per_minute: int = 600, burst_limit: int = 10):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute (GitLab typically allows 2000/min)
            burst_limit: Maximum requests in a short burst before adding delays
        """
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.request_times = []
        self.burst_count = 0
        self.last_request_time = 0

        # Calculate minimum delay between requests
        self.min_delay = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.1

    def wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()

        # Clean old request times (older than 1 minute)
        minute_ago = current_time - 60
        self.request_times = [t for t in self.request_times if t > minute_ago]

        # Check if we're approaching the rate limit
        if len(self.request_times) >= self.requests_per_minute * 0.9:  # 90% of limit
            wait_time = 60 - (current_time - self.request_times[0])
            if wait_time > 0:
                logging.warning(f"Approaching rate limit. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                return

        # Handle burst limiting
        time_since_last = current_time - self.last_request_time
        if time_since_last < 1.0:  # Less than 1 second since last request
            self.burst_count += 1
            if self.burst_count >= self.burst_limit:
                burst_delay = max(1.0, self.min_delay * 2)
                logging.debug(f"Burst limit reached. Waiting {burst_delay:.1f} seconds...")
                time.sleep(burst_delay)
                self.burst_count = 0
        else:
            self.burst_count = 0

        # Ensure minimum delay between requests
        if time_since_last < self.min_delay:
            wait_time = self.min_delay - time_since_last
            time.sleep(wait_time)

        # Record this request
        self.request_times.append(time.time())
        self.last_request_time = time.time()


class APIRetryHandler:
    """Handle API retries with exponential backoff for 429 and other recoverable errors."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 300.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def execute_with_retry(self, func, *args, **kwargs):
        """
        Execute a function with retry logic for recoverable errors.

        Args:
            func: Function to execute
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Function result or raises exception after max retries
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)

            except requests.RequestException as e:
                last_exception = e

                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code

                    # Handle 429 (Rate Limited)
                    if status_code == 429:
                        retry_after = self._get_retry_after(e.response)
                        if attempt < self.max_retries:
                            wait_time = min(retry_after or (self.base_delay * (2 ** attempt)), self.max_delay)
                            logging.warning(
                                f"Rate limit exceeded (429). Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{self.max_retries}...")

                            # Ask user if they want to continue for long waits
                            if wait_time > 60:
                                if not self._ask_user_continue(wait_time):
                                    raise RateLimitExceeded(
                                        f"Rate limit exceeded. User chose to abort after {wait_time:.1f}s wait time.")

                            time.sleep(wait_time)
                            continue
                        else:
                            raise RateLimitExceeded(f"Rate limit exceeded after {self.max_retries} retries")

                    # Handle other server errors (5xx)
                    elif 500 <= status_code < 600:
                        if attempt < self.max_retries:
                            wait_time = min(self.base_delay * (2 ** attempt), self.max_delay)
                            logging.warning(
                                f"Server error ({status_code}). Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{self.max_retries}...")
                            time.sleep(wait_time)
                            continue

                    # Handle temporary network issues
                    elif status_code in [502, 503, 504]:
                        if attempt < self.max_retries:
                            wait_time = min(self.base_delay * (2 ** attempt), self.max_delay)
                            logging.warning(
                                f"Network error ({status_code}). Waiting {wait_time:.1f} seconds before retry {attempt + 1}/{self.max_retries}...")
                            time.sleep(wait_time)
                            continue

                # For non-recoverable errors or final attempt, re-raise
                if attempt == self.max_retries:
                    break

        # If we get here, all retries failed
        if last_exception:
            raise last_exception

    def _get_retry_after(self, response) -> Optional[int]:
        """Extract Retry-After header value."""
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                pass
        return None

    def _ask_user_continue(self, wait_time: float) -> bool:
        """Ask user if they want to continue with a long wait."""
        try:
            print(f"\n{'=' * 60}")
            print("RATE LIMIT EXCEEDED")
            print(f"{'=' * 60}")
            print(f"The GitLab API rate limit has been exceeded.")
            print(f"Recommended wait time: {wait_time:.1f} seconds ({wait_time / 60:.1f} minutes)")
            print()
            print("Options:")
            print("1. Wait and continue (recommended)")
            print("2. Cancel operation")
            print()

            while True:
                choice = input("Enter your choice (1-2): ").strip()
                if choice == '1':
                    return True
                elif choice == '2':
                    return False
                else:
                    print("Invalid choice. Please enter 1 or 2.")

        except (EOFError, KeyboardInterrupt):
            print("\nOperation cancelled by user.")
            return False


class GitLabProvider(ScmProvider):
    """GitLab API client for repository operations."""

    def __init__(self, gitlab_url: str, access_token: str, verify_ssl: bool = True):
        self.gitlab_url = gitlab_url.rstrip('/')
        self.access_token = access_token
        self.verify_ssl = verify_ssl
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.verify = verify_ssl

        # Initialize rate limiting and retry handling
        self.rate_limiter = RateLimiter(requests_per_minute=600, burst_limit=10)
        self.retry_handler = APIRetryHandler(max_retries=3, base_delay=1.0, max_delay=300.0)

        # Suppress SSL warnings if verification is disabled
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _make_request(self, method: str, url: str, **kwargs):
        """Make an API request with rate limiting and retry logic."""

        def _request():
            self.rate_limiter.wait_if_needed()
            response = getattr(self.session, method.lower())(url, **kwargs)
            response.raise_for_status()
            return response

        return self.retry_handler.execute_with_retry(_request)

    def get_project(self, project_id: str) -> Optional[Dict]:
        """Get project information by ID or path."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}"
        try:
            response = self._make_request('get', url)
            return response.json()
        except (requests.RequestException, RateLimitExceeded) as e:
            logging.error(f"Failed to get project {project_id}: {e}")
            return None

    def get_repository_tree(self, project_id: str, path: str = "", ref: str = "main") -> List[Dict]:
        """Get repository tree structure with pagination support."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/repository/tree"

        all_items = []
        page = 1
        per_page = 100  # GitLab's default and maximum

        while True:
            params = {
                'path': path,
                'ref': ref,
                'recursive': True,
                'per_page': per_page,
                'page': page
            }

            try:
                response = self._make_request('get', url, params=params)
                items = response.json()

                if not items:  # No more items, we've reached the end
                    break

                all_items.extend(items)

                # Check if we've gotten less than per_page items, indicating this is the last page
                if len(items) < per_page:
                    break

                page += 1

                # Log progress for large repositories
                if page % 10 == 0:  # Log every 10 pages
                    logging.info(f"Fetched {len(all_items)} files from repository tree (page {page})")

            except (requests.RequestException, RateLimitExceeded) as e:
                logging.error(f"Failed to get repository tree for {project_id} (page {page}): {e}")
                break

        logging.info(f"Total files fetched from repository tree: {len(all_items)}")
        return all_items

    def search_code_blobs(self, project_id: str, search: str, ref: Optional[str] = None) -> List[str]:
        """Search repository blobs for a plain-text term.

        Returns a list of file paths that contain the search term.

        Notes:
        - This uses GitLab's project search API (scope=blobs).
        - Some GitLab versions may not support 'ref' here; if it fails, we retry without it.
        """
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/search"

        def do_search(include_ref: bool) -> List[str]:
            all_paths: List[str] = []
            seen = set()
            page = 1
            per_page = 100
            while True:
                params = {
                    'scope': 'blobs',
                    'search': search,
                    'per_page': per_page,
                    'page': page,
                }
                if include_ref and ref:
                    params['ref'] = ref

                response = self._make_request('get', url, params=params)
                items = response.json()
                if not items:
                    break

                for item in items:
                    path = item.get('path') or item.get('filename')
                    if not path:
                        continue
                    if path in seen:
                        continue
                    seen.add(path)
                    all_paths.append(path)

                if len(items) < per_page:
                    break
                page += 1

            return all_paths

        try:
            # Prefer searching the requested branch/ref when supported.
            return do_search(include_ref=True)
        except (requests.RequestException, RateLimitExceeded) as e:
            # Retry without ref for GitLab instances that don't support it.
            logging.warning(f"Blob search with ref failed for {project_id} (retrying without ref): {e}")
            try:
                return do_search(include_ref=False)
            except Exception as e2:
                logging.error(f"Blob search failed for {project_id}: {e2}")
                return []

    def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> Optional[str]:
        """Get file content from repository."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        # URL encode the file path for the API
        encoded_file_path = quote(file_path, safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/repository/files/{encoded_file_path}"
        params = {'ref': ref}

        try:
            response = self._make_request('get', url, params=params)
            file_data = response.json()
            # Content is base64 encoded
            return base64.b64decode(file_data['content']).decode('utf-8')
        except (requests.RequestException, RateLimitExceeded) as e:
            logging.error(f"Failed to get file {file_path} from {project_id}: {e}")
            return None

    def create_merge_request(self, project_id: str, source_branch: str, target_branch: str,
                           title: str, description: str) -> Optional[Dict]:
        """Create a merge request."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/merge_requests"

        data = {
            'source_branch': source_branch,
            'target_branch': target_branch,
            'title': title,
            'description': description,
            'remove_source_branch': True
        }

        try:
            response = self._make_request('post', url, json=data)
            return response.json()
        except (requests.RequestException, RateLimitExceeded) as e:
            logging.error(f"Failed to create merge request in {project_id}: {e}")
            return None

    def get_merge_request_status(self, project_id: str, mr_iid: str) -> Optional[str]:
        """Get the status of a merge request."""
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_iid}"

        try:
            response = self._make_request('get', url)
            return response.json().get('state')
        except (requests.RequestException, RateLimitExceeded) as e:
            logging.error(f"Failed to get merge request {mr_iid} from project {project_id}: {e}")
            return None

    def discover_repositories(self, group_id: str = None, owned: bool = None,
                              membership: bool = None, archived: bool = False) -> List[Dict]:
        """Get all repositories the user has access to, with optional filtering."""
        url = f"{self.gitlab_url}/api/v4/projects"

        params = {
            'per_page': 100,
            'simple': True,
            'archived': archived
        }

        if group_id:
            # Get repositories from a specific group/namespace
            encoded_group_id = quote(group_id, safe='')
            url = f"{self.gitlab_url}/api/v4/groups/{encoded_group_id}/projects"
            params['include_subgroups'] = True
        else:
            # Get user's repositories with optional filters
            if owned is not None:
                params['owned'] = owned
            if membership is not None:
                params['membership'] = membership

        all_projects = []
        page = 1

        while True:
            params['page'] = page

            try:
                response = self._make_request('get', url, params=params)
                projects = response.json()

                if not projects:  # No more projects
                    break

                all_projects.extend(projects)

                # Check if we've gotten less than per_page items, indicating this is the last page
                if len(projects) < params['per_page']:
                    break

                page += 1

                # Log progress for large numbers of repositories
                if page % 10 == 0:
                    logging.info(f"Fetched {len(all_projects)} repositories (page {page})")

            except (requests.RequestException, RateLimitExceeded) as e:
                logging.error(f"Failed to get repositories (page {page}): {e}")
                break

        logging.info(f"Total repositories found: {len(all_projects)}")
        return all_projects

    def check_existing_merge_request(self, project_id: str, title: str,
                                   source_branch: str = None, target_branch: str = None) -> Optional[Dict]:
        """Check if a merge request with the same title already exists."""
        merge_requests = self.get_merge_requests(project_id, state="opened",
                                               source_branch=source_branch,
                                               target_branch=target_branch)

        # Check for exact title match
        for mr in merge_requests:
            if mr['title'] == title:
                logging.info(f"Found existing merge request with title '{title}': {mr['web_url']}")
                return mr

        return None

    def get_merge_requests(self, project_id: str, state: str = "opened",
                          source_branch: str = None, target_branch: str = None) -> List[Dict]:
        """Get merge requests for a project with optional filters."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/merge_requests"

        params = {'state': state}
        if source_branch:
            params['source_branch'] = source_branch
        if target_branch:
            params['target_branch'] = target_branch

        try:
            response = self._make_request('get', url, params=params)
            return response.json()
        except (requests.RequestException, RateLimitExceeded) as e:
            logging.error(f"Failed to get merge requests for {project_id}: {e}")
            return []

    def update_file(self, project_id: str, file_path: str, content: str, commit_message: str,
                   branch_name: str, ref: str = "main") -> bool:
        """Update file in repository."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        # URL encode the file path for the API
        encoded_file_path = quote(file_path, safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/repository/files/{encoded_file_path}"

        # Prepare data for the API call
        data = {
            'branch': branch_name,
            'content': content,
            'commit_message': commit_message
        }

        # Only add start_branch if the branch doesn't exist yet
        # If branch exists, we just commit to it directly
        if not self.branch_exists(project_id, branch_name):
            data['start_branch'] = ref

        try:
            response = self._make_request('put', url, json=data)
            return True
        except (requests.RequestException, RateLimitExceeded) as e:
            logging.error(f"Failed to update file {file_path} in {project_id}: {e}")
            return False

    def create_branch(self, project_id: str, branch_name: str, ref: str = "main") -> bool:
        """Create a new branch."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/repository/branches"

        data = {
            'branch': branch_name,
            'ref': ref
        }

        try:
            response = self._make_request('post', url, json=data)
            return True
        except (requests.RequestException, RateLimitExceeded) as e:
            logging.error(f"Failed to create branch {branch_name} in {project_id}: {e}")
            return False

    def delete_branch(self, project_id: str, branch_name: str) -> bool:
        """Delete a branch."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        # URL encode the branch name to handle special characters
        encoded_branch_name = quote(branch_name, safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/repository/branches/{encoded_branch_name}"

        try:
            response = self._make_request('delete', url)
            return True
        except (requests.RequestException, RateLimitExceeded) as e:
            # Don't log as error if branch doesn't exist (404)
            if hasattr(e, 'response') and e.response.status_code == 404:
                logging.debug(f"Branch {branch_name} doesn't exist in {project_id}, nothing to delete")
                return True
            logging.error(f"Failed to delete branch {branch_name} in {project_id}: {e}")
            return False

    def branch_exists(self, project_id: str, branch_name: str) -> bool:
        """Check if a branch exists."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        # URL encode the branch name to handle special characters
        encoded_branch_name = quote(branch_name, safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/repository/branches/{encoded_branch_name}"

        try:
            response = self._make_request('get', url)
            return response.status_code == 200
        except (requests.RequestException, RateLimitExceeded):
            return False

    def create_or_recreate_branch(self, project_id: str, branch_name: str, ref: str = "main") -> bool:
        """Create a branch, deleting it first if it already exists."""
        if self.branch_exists(project_id, branch_name):
            logging.info(f"Branch {branch_name} already exists, deleting it first")
            if not self.delete_branch(project_id, branch_name):
                logging.error(f"Failed to delete existing branch {branch_name}")
                return False
            logging.info(f"Successfully deleted existing branch {branch_name}")

        logging.info(f"Creating branch {branch_name}")
        return self.create_branch(project_id, branch_name, ref)

    def list_branches(self, project_id: str) -> List[Dict]:
        """List all branches in a repository."""
        # URL encode the project_id to handle paths like "group/project"
        encoded_project_id = quote(str(project_id), safe='')
        url = f"{self.gitlab_url}/api/v4/projects/{encoded_project_id}/repository/branches"
        
        all_branches = []
        page = 1
        per_page = 100  # GitLab's default and maximum

        while True:
            params = {
                'per_page': per_page,
                'page': page
            }

            try:
                response = self._make_request('get', url, params=params)
                branches = response.json()

                if not branches:  # No more branches
                    break

                all_branches.extend(branches)

                # Check if we've gotten less than per_page items, indicating this is the last page
                if len(branches) < per_page:
                    break

                page += 1

            except (requests.RequestException, RateLimitExceeded) as e:
                logging.error(f"Failed to list branches for {project_id} (page {page}): {e}")
                break

        logging.debug(f"Found {len(all_branches)} branches in repository {project_id}")
        return all_branches

    def get_most_recent_branch(self, project_id: str, branch_filter: str = None) -> Optional[str]:
        """Get the branch with the most recent commit, optionally filtered by pattern."""
        import fnmatch
        from datetime import datetime

        branches = self.list_branches(project_id)
        if not branches:
            logging.warning(f"No branches found in repository {project_id}")
            return None

        # Filter branches if pattern is provided
        filtered_branches = branches
        if branch_filter:
            filtered_branches = []
            for branch in branches:
                branch_name = branch['name']
                if fnmatch.fnmatch(branch_name, branch_filter):
                    filtered_branches.append(branch)
            
            if not filtered_branches:
                logging.warning(f"No branches match filter '{branch_filter}' in repository {project_id}")
                return None
            
            logging.info(f"Filtered to {len(filtered_branches)} branches matching pattern '{branch_filter}'")

        # Find the branch with the most recent commit
        most_recent_branch = None
        most_recent_date = None

        for branch in filtered_branches:
            try:
                # Get commit date from the branch info
                commit_date_str = branch['commit']['committed_date']
                # Parse ISO format date: 2024-03-15T10:30:00.000Z
                commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
                
                if most_recent_date is None or commit_date > most_recent_date:
                    most_recent_date = commit_date
                    most_recent_branch = branch['name']
            except (KeyError, ValueError) as e:
                logging.warning(f"Could not parse commit date for branch {branch.get('name', 'unknown')}: {e}")
                continue

        if most_recent_branch:
            logging.info(f"Found most recent branch: {most_recent_branch} (last commit: {most_recent_date})")
        else:
            logging.warning(f"Could not determine most recent branch in repository {project_id}")

        return most_recent_branch
