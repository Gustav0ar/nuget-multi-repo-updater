"""
Repository management utilities for handling different repository input methods.
"""
import logging
from typing import List, Dict, Optional

from src.providers.scm_provider import ScmProvider


class RepositoryManager:
    """Handles repository discovery, loading, and filtering operations."""
    
    def __init__(self, scm_provider: ScmProvider):
        self.scm_provider = scm_provider
    
    def load_repositories_from_file(self, file_path: str) -> List[str]:
        """Load repository IDs/paths from a file."""
        try:
            with open(file_path, 'r') as f:
                repositories = [line.strip() for line in f
                              if line.strip() and not line.strip().startswith('#')]
            logging.info(f"Loaded {len(repositories)} repositories from file: {file_path}")
            return repositories
        except Exception as e:
            logging.error(f"Error reading repository file {file_path}: {e}")
            return []
    
    def filter_repositories(self, projects: List[Dict], ignore_patterns: Optional[str] = None, 
                          exclude_forks: bool = False) -> List[Dict]:
        """Filter repositories based on ignore patterns and fork status."""
        if ignore_patterns:
            import fnmatch
            patterns = [p.strip() for p in ignore_patterns.split(',') if p.strip()]
            projects = [p for p in projects if not any(
                fnmatch.fnmatch(p['name'].lower(), pattern.lower()) or
                fnmatch.fnmatch(p['path_with_namespace'].lower(), pattern.lower())
                for pattern in patterns
            )]
            logging.info(f"Applied ignore patterns, {len(projects)} repositories remaining")

        if exclude_forks:
            projects = [p for p in projects if not p.get('forked_from_project')]
            logging.info(f"Excluded forks, {len(projects)} repositories remaining")

        return projects

    def filter_repositories_by_patterns(self, projects: List[Dict], ignore_patterns: List[str]) -> List[Dict]:
        """Filter repositories by ignore patterns (case-insensitive)."""
        if not ignore_patterns:
            return projects

        import fnmatch
        filtered_projects = []

        for project in projects:
            name = project['name'].lower()
            path = project.get('path_with_namespace', '').lower()
            
            matched = False
            for pattern in ignore_patterns:
                if fnmatch.fnmatch(name, pattern.lower()) or fnmatch.fnmatch(path, pattern.lower()):
                    matched = True
                    break
            
            if not matched:
                filtered_projects.append(project)

        ignored_count = len(projects) - len(filtered_projects)
        if ignored_count > 0:
            logging.info(f"Ignored {ignored_count} repositories based on patterns, {len(filtered_projects)} remaining")

        return filtered_projects

    def filter_out_forks(self, projects: List[Dict]) -> List[Dict]:
        """Filter out forked repositories."""
        filtered_projects = [p for p in projects if not p.get('forked_from_project')]
        if len(projects) > len(filtered_projects):
            logging.info(f"Excluded {len(projects) - len(filtered_projects)} forks, {len(filtered_projects)} repositories remaining")
        return filtered_projects

    def get_repositories_from_command_line(self, repo_list_str: str) -> List[Dict]:
        """Get repositories from command line comma-separated list."""
        repositories = []
        repo_list = [repo.strip() for repo in repo_list_str.split(',') if repo.strip()]
        
        for repo_id in repo_list:
            project = self.scm_provider.get_project(repo_id)
            if project:
                repositories.append(project)
            else:
                logging.warning(f"Could not find repository: {repo_id}")
        
        return repositories
    
    def get_repositories_from_file(self, file_path: str) -> List[Dict]:
        """Get repositories from file."""
        repositories = []
        repo_list = self.load_repositories_from_file(file_path)
        
        for repo_id in repo_list:
            project = self.scm_provider.get_project(repo_id)
            if project:
                repositories.append(project)
            else:
                logging.warning(f"Could not find repository: {repo_id}")
        
        return repositories
    
    def discover_repositories(self, group_id: str, owned_only: bool = False, 
                            member_only: bool = False, include_archived: bool = False) -> List[Dict]:
        """Discover repositories from a GitLab group."""
        return self.scm_provider.discover_repositories(
            group_id=group_id,
            owned=owned_only,
            membership=member_only,
            archived=include_archived
        )
    
    def get_repositories_from_config(self, repo_configs: List) -> List[Dict]:
        """Get repositories from configuration."""
        repositories = []
        
        for repo_config in repo_configs:
            if isinstance(repo_config, dict):
                repositories.append(repo_config)
            else:
                project = self.scm_provider.get_project(repo_config)
                if project:
                    repositories.append(project)
        
        return repositories
