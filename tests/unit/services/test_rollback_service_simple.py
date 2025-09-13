"""
Unit tests for rollback service components.
"""
import pytest
from unittest.mock import Mock
from src.services.rollback_service import (
    RollbackResult,
    RepositoryUpdateTransaction,
    TransactionException
)


class TestRollbackResult:
    """Test cases for RollbackResult dataclass."""
    
    def test_rollback_result_creation(self):
        """Test creating a rollback result."""
        result = RollbackResult()
        
        assert result.success is True
        assert len(result.completed_actions) == 0
        assert len(result.failed_actions) == 0
        assert len(result.warnings) == 0
        
    def test_add_completed_action(self):
        """Test adding completed action."""
        result = RollbackResult()
        result.add_completed_action('Test action completed')
        
        assert len(result.completed_actions) == 1
        assert result.completed_actions[0] == 'Test action completed'
        assert result.success is True
        
    def test_add_failed_action(self):
        """Test adding failed action."""
        result = RollbackResult()
        result.add_failed_action('Test action', 'Error message')
        
        assert len(result.failed_actions) == 1
        assert result.failed_actions[0]['action'] == 'Test action'
        assert result.failed_actions[0]['error'] == 'Error message'
        assert result.success is False
        
    def test_add_warning(self):
        """Test adding warning."""
        result = RollbackResult()
        result.add_warning('Warning message')
        
        assert len(result.warnings) == 1
        assert result.warnings[0] == 'Warning message'


class TestRepositoryUpdateTransaction:
    """Test cases for RepositoryUpdateTransaction class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        from unittest.mock import Mock
        self.mock_strategy = Mock()
        self.transaction = RepositoryUpdateTransaction('test-repo', self.mock_strategy)
        
    def test_transaction_creation(self):
        """Test creating a transaction."""
        assert self.transaction.repo_id == 'test-repo'
        assert len(self.transaction.rollback_actions) == 0
        
    def test_add_rollback_action(self):
        """Test adding rollback action."""
        action = lambda: print("rollback")
        self.transaction.add_rollback_action(action, "Test action")
        
        assert len(self.transaction.rollback_actions) == 1
        
    def test_execute_rollback(self):
        """Test executing rollback actions."""
        executed_actions = []
        
        def action1():
            executed_actions.append("action1")
            
        def action2():
            executed_actions.append("action2")
        
        self.transaction.add_rollback_action(action1, "Action 1")
        self.transaction.add_rollback_action(action2, "Action 2")
        
        result = self.transaction.execute_rollback()
        
        assert result.success is True
        assert len(executed_actions) == 2
        # Actions should be executed in reverse order (LIFO)
        assert executed_actions == ["action2", "action1"]


class TestTransactionException:
    """Test cases for TransactionException class."""
    
    def test_transaction_exception_creation(self):
        """Test creating a transaction exception."""
        from src.services.rollback_service import RollbackResult
        rollback_result = RollbackResult()
        exception = TransactionException('Test error', rollback_result)
        
        assert str(exception) == 'Test error'
        assert exception.rollback_result == rollback_result
