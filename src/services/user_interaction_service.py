"""
User interaction service for repository discovery and confirmation dialogs.
"""
import sys
from typing import List, Dict
import logging


class UserInteractionService:
    """Handles user interactions for repository discovery and confirmation."""

    @staticmethod
    def display_discovered_repositories(discovered_projects: List[Dict]) -> None:
        """Display the list of discovered repositories in a formatted way."""
        print(f"\n{'='*80}")
        print(f"DISCOVERED REPOSITORIES ({len(discovered_projects)} total)")
        print(f"{'='*80}")

        for i, project in enumerate(discovered_projects, 1):
            print(f"{i:3d}. {project['name']}")
            print(f"     Path: {project['path_with_namespace']}")
            print(f"     ID: {project['id']}")
            print(f"     URL: {project['web_url']}")
            if project.get('description'):
                desc = project['description'][:100] + "..." if len(project['description']) > 100 else project['description']
                print(f"     Description: {desc}")
            print()

    @staticmethod
    def get_user_confirmation(projects: List[Dict]) -> List[Dict]:
        """Ask user for confirmation to update repositories."""
        if not projects:
            return projects

        UserInteractionService.display_discovered_repositories(projects)
        confirmation_mode = UserInteractionService._get_user_confirmation_mode()

        if confirmation_mode == 'cancel':
            print("Operation cancelled by user.")
            sys.exit(0)
        elif confirmation_mode == 'individual':
            confirmed_repos = []
            for repo in projects:
                if UserInteractionService._ask_repository_confirmation(repo):
                    confirmed_repos.append(repo)
                else:
                    logging.info(f"Skipping repository '{repo['name']}' per user request")
            return confirmed_repos
        else:  # confirmation_mode == 'all'
            print(f"\nProceeding with all {len(projects)} repositories...")
            return projects

    @staticmethod
    def _get_user_confirmation_mode() -> str:
        """Get user confirmation mode for repository updates."""
        print(f"{'='*80}")
        print("CONFIRMATION MODE")
        print(f"{'='*80}")
        print("Choose how you want to proceed with the repository updates:")
        print()
        print("1. Update ALL repositories without further confirmation")
        print("2. Ask for confirmation BEFORE updating each repository")
        print("3. Cancel operation")
        print()

        while True:
            try:
                choice = input("Enter your choice (1-3): ").strip()
                if choice == '1':
                    return 'all'
                elif choice == '2':
                    return 'individual'
                elif choice == '3':
                    return 'cancel'
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
            except (EOFError, KeyboardInterrupt):
                print("\nOperation cancelled by user.")
                return 'cancel'

    @staticmethod
    def _ask_repository_confirmation(project_info: Dict) -> bool:
        """Ask user for confirmation to update a specific repository."""
        print(f"\n{'-'*60}")
        print(f"REPOSITORY: {project_info['name']}")
        print(f"Path: {project_info['path_with_namespace']}")
        print(f"{'-'*60}")

        while True:
            try:
                choice = input("Update this repository? (y/n/q): ").strip().lower()
                if choice in ['y', 'yes']:
                    return True
                elif choice in ['n', 'no']:
                    return False
                elif choice in ['q', 'quit']:
                    print("Operation cancelled by user.")
                    sys.exit(0)
                else:
                    print("Please enter 'y' for yes, 'n' for no, or 'q' to quit.")
            except (EOFError, KeyboardInterrupt):
                print("\nOperation cancelled by user.")
                sys.exit(0)
