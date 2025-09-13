"""
Unit tests for rollback service.
"""
import pytest
import tempfile
import os
from dataclasses import dataclass
from unittest.mock import Mock, patch, MagicMock
from src.services.rollback_service import (
    RollbackResult,
    RepositoryUpdateTransaction,
    TransactionException
)


@dataclass
class RollbackAction:
    """Mock rollback action for testing."""
    action_type: str
    description: str
    rollback_data: dict


class TestRollbackAction:
    """Test cases for RollbackAction dataclass."""
    
    def test_rollback_action_creation(self):
        """Test creating a rollback action."""
        action = RollbackAction(
            action_type='git_commit',
            description='Test commit',
            rollback_data={'commit_sha': 'abc123'}
        )
        
        assert action.action_type == 'git_commit'
        assert action.description == 'Test commit'
        assert action.rollback_data['commit_sha'] == 'abc123'


class TestRollbackResult:
    """Test cases for RollbackResult dataclass."""
    
    def test_rollback_result_creation(self):
        """Test creating a rollback result."""
        result = RollbackResult(
            success=True,
            completed_actions=['action1', 'action2'],
            failed_actions=[],
            warnings=[]
        )
        
        assert result.success is True
        assert len(result.completed_actions) == 2
        assert len(result.failed_actions) == 0


class TestRepositoryUpdateTransaction:
    """Test cases for RepositoryUpdateTransaction class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_strategy = Mock()
        self.transaction = RepositoryUpdateTransaction('test-repo', self.mock_strategy)
        
    def test_execute_rollback_empty_transaction(self):
        """Test rollback with empty transaction."""
        result = self.transaction.execute_rollback()
        
        assert result.success is True
        assert len(result.completed_actions) == 0
        assert len(result.failed_actions) == 0
        
    def test_add_rollback_action(self):
        """Test adding rollback actions."""
        mock_action1 = Mock()
        mock_action2 = Mock()
        
        self.transaction.add_rollback_action(mock_action1, "Action 1")
        self.transaction.add_rollback_action(mock_action2, "Action 2")
        
        assert len(self.transaction.rollback_actions) == 2
        
    def test_execute_rollback_successful_actions(self):
        """Test successful execution of rollback actions."""
        mock_action1 = Mock()
        mock_action2 = Mock()
        
        self.transaction.add_rollback_action(mock_action1, "Action 1")
        self.transaction.add_rollback_action(mock_action2, "Action 2")
        
        result = self.transaction.execute_rollback()
        
        assert result.success is True
        assert len(result.completed_actions) == 2
        assert len(result.failed_actions) == 0
        # Actions should be executed in reverse order (LIFO)
        mock_action2.assert_called_once()
        mock_action1.assert_called_once()
        
    def test_execute_rollback_with_failures(self):
        """Test rollback with some failed actions."""
        mock_action1 = Mock()
        mock_action2 = Mock(side_effect=Exception("Test error"))
        
        self.transaction.add_rollback_action(mock_action1, "Action 1")
        self.transaction.add_rollback_action(mock_action2, "Action 2")
        
        result = self.transaction.execute_rollback()
        
        assert result.success is False
        assert len(result.completed_actions) == 1
        assert len(result.failed_actions) == 1
        assert result.failed_actions[0]["action"] == "Action 2"
        assert "Test error" in result.failed_actions[0]["error"]
        
    def test_clear_rollback_actions(self):
        """Test clearing rollback actions."""
        mock_action = Mock()
        self.transaction.add_rollback_action(mock_action, "Test action")
        
        assert len(self.transaction.rollback_actions) == 1
        
        self.transaction.clear_rollback_actions()
        
        assert len(self.transaction.rollback_actions) == 0
        
    def test_set_created_branch(self):
        """Test setting created branch for rollback."""
        branch_name = "feature/test-branch"
        self.transaction.set_created_branch(branch_name)
        
        assert self.transaction.created_branch == branch_name
        
    def test_add_temp_file(self):
        """Test adding temporary files for cleanup."""
        temp_file = "/tmp/test-file.txt"
        self.transaction.add_temp_file(temp_file)
        
        assert temp_file in self.transaction.temp_files


class TestTransactionException:
    """Test cases for TransactionException class."""
    
    def test_transaction_exception_creation(self):
        """Test creating a transaction exception."""
        mock_strategy = Mock()
        rollback_result = RollbackResult()
        exception = TransactionException('Test error', rollback_result)
        
        assert str(exception) == 'Test error'
        assert exception.rollback_result == rollback_result
