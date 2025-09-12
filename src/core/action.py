from abc import ABC, abstractmethod
from typing import Optional, Dict

class Action(ABC):
    """Base class for all actions."""

    @abstractmethod
    def execute(self, repo_url: str, repo_id: str, default_branch: str) -> Optional[Dict]:
        """Execute the action."""
        pass
