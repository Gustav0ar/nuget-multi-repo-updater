import git

class GitService:
    """Service for handling local Git operations."""

    def __init__(self, local_path: str):
        self.local_path = local_path
        self.repo = None

    def clone(self, repo_url: str):
        """Clone a repository."""
        self.repo = git.Repo.clone_from(repo_url, self.local_path)

    def create_branch(self, branch_name: str):
        """Create a new branch."""
        if self.repo:
            self.repo.git.checkout('-b', branch_name)

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
