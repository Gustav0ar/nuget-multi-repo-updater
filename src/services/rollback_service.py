"""
Rollback mechanisms for repository update transactions.
"""
import logging
from typing import List, Callable, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class RollbackResult:
    """Result of executing rollback operations."""
    success: bool = True
    completed_actions: List[str] = field(default_factory=list)
    failed_actions: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_completed_action(self, action_description: str):
        """Add a successfully completed rollback action."""
        self.completed_actions.append(action_description)
        logging.info(f"Rollback completed: {action_description}")
        
    def add_failed_action(self, action_description: str, error: str):
        """Add a failed rollback action."""
        self.failed_actions.append({"action": action_description, "error": error})
        self.success = False
        logging.error(f"Rollback failed: {action_description} - {error}")
        
    def add_warning(self, warning: str):
        """Add a rollback warning."""
        self.warnings.append(warning)
        logging.warning(f"Rollback warning: {warning}")
        
    def generate_report(self) -> str:
        """Generate human-readable rollback report."""
        report = ["=== ROLLBACK REPORT ==="]
        
        if self.success:
            report.append("Rollback completed successfully")
        else:
            report.append("Rollback completed with errors")
            
        if self.completed_actions:
            report.append("\nCompleted Actions:")
            for action in self.completed_actions:
                report.append(f"  • {action}")
                
        if self.failed_actions:
            report.append("\nFailed Actions:")
            for failed in self.failed_actions:
                report.append(f"  • {failed['action']}: {failed['error']}")
                
        if self.warnings:
            report.append("\nWarnings:")
            for warning in self.warnings:
                report.append(f"  • {warning}")
                
        return "\n".join(report)


class RepositoryUpdateTransaction:
    """Manages the entire repository update process with rollback capabilities."""
    
    def __init__(self, repo_id: str, strategy_instance):
        self.repo_id = repo_id
        self.strategy = strategy_instance
        self.rollback_actions: List[Callable[[], None]] = []
        self.created_branch = None
        self.temp_files = []
        self.rollback_result = RollbackResult()
        
    def add_rollback_action(self, action: Callable[[], None], description: str = ""):
        """Add a rollback action to be executed if transaction fails."""
        self.rollback_actions.append((action, description))
        
    def execute_rollback(self) -> RollbackResult:
        """Execute all rollback actions in reverse order."""
        logging.info(f"Starting rollback for repository {self.repo_id}")
        self.rollback_result = RollbackResult()
        
        # Execute rollback actions in reverse order (LIFO)
        while self.rollback_actions:
            action, description = self.rollback_actions.pop()
            try:
                action()
                self.rollback_result.add_completed_action(description or "Unnamed rollback action")
            except Exception as rollback_error:
                self.rollback_result.add_failed_action(
                    description or "Unnamed rollback action",
                    str(rollback_error)
                )
                
        logging.info(f"Rollback completed for repository {self.repo_id}")
        return self.rollback_result
        
    def clear_rollback_actions(self):
        """Clear all rollback actions (called on successful completion)."""
        self.rollback_actions.clear()
        logging.debug(f"Cleared rollback actions for repository {self.repo_id}")
        
    def set_created_branch(self, branch_name: str):
        """Set the name of the branch created for this transaction."""
        self.created_branch = branch_name
        
    def add_temp_file(self, file_path: str):
        """Add a temporary file to be cleaned up on rollback."""
        self.temp_files.append(file_path)


class RollbackCapableTransaction:
    """Base class for operations that support rollback."""
    
    def __init__(self, transaction: RepositoryUpdateTransaction):
        self.transaction = transaction
        
    def execute_with_rollback(self, operation_name: str, operation_func: Callable[[], Any]) -> Any:
        """Execute an operation and automatically rollback on failure."""
        try:
            result = operation_func()
            logging.debug(f"Successfully completed operation: {operation_name}")
            return result
        except Exception as e:
            logging.error(f"Operation failed: {operation_name} - {e}")
            self.transaction.execute_rollback()
            raise e


class TransactionException(Exception):
    """Exception that includes rollback result information."""
    
    def __init__(self, message: str, rollback_result: Optional[RollbackResult] = None):
        super().__init__(message)
        self.rollback_result = rollback_result


def with_rollback(transaction: RepositoryUpdateTransaction, description: str):
    """Decorator to automatically add rollback capability to methods."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                # If the function succeeds, we don't add a rollback action
                # Instead, the function itself should add appropriate rollback actions
                return result
            except Exception as e:
                logging.error(f"Operation failed: {description} - {e}")
                rollback_result = transaction.execute_rollback()
                raise TransactionException(f"{description} failed: {e}", rollback_result)
        return wrapper
    return decorator
