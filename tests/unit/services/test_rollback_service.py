"""
Unit tests for rollback service.
"""
import pytest
import tempfile
import os
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
            actions_rolled_back=['action1', 'action2'],
            message='Rollback completed successfully'
        )
        
        assert result.success is True
        assert len(result.actions_rolled_back) == 2
        assert result.message == 'Rollback completed successfully'


class TestRepositoryUpdateTransaction:
    """Test cases for RepositoryUpdateTransaction class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.transaction = RepositoryUpdateTransaction('test-repo')
        
    def test_transaction_creation(self):
        """Test creating a transaction."""
        assert self.transaction.repository_path == 'test-repo'
        assert len(self.transaction.actions) == 0
        assert self.transaction.start_time is not None
        
    def test_add_action(self):
        """Test adding an action to the transaction."""
        action = RollbackAction(
            action_type='git_commit',
            description='Test commit',
            rollback_data={'commit_sha': 'abc123'}
        )
        
        self.transaction.add_action(action)
        
        assert len(self.transaction.actions) == 1
        assert self.transaction.actions[0] == action
        
    def test_get_rollback_actions_fifo(self):
        """Test getting rollback actions in LIFO order."""
        action1 = RollbackAction('type1', 'desc1', {})
        action2 = RollbackAction('type2', 'desc2', {})
        action3 = RollbackAction('type3', 'desc3', {})
        
        self.transaction.add_action(action1)
        self.transaction.add_action(action2)
        self.transaction.add_action(action3)
        
        rollback_actions = self.transaction.get_rollback_actions()
        
        # Should be in reverse order (LIFO)
        assert len(rollback_actions) == 3
        assert rollback_actions[0] == action3
        assert rollback_actions[1] == action2
        assert rollback_actions[2] == action1
        
    def test_clear_actions(self):
        """Test clearing all actions from transaction."""
        self.transaction.add_action(RollbackAction('type1', 'desc1', {}))
        self.transaction.add_action(RollbackAction('type2', 'desc2', {}))
        
        assert len(self.transaction.actions) == 2
        
        self.transaction.clear_actions()
        
        assert len(self.transaction.actions) == 0


class TestTransactionException:
    """Test cases for TransactionException class."""
    
    def test_transaction_exception_creation(self):
        """Test creating a transaction exception."""
        transaction = RepositoryUpdateTransaction('test-repo')
        exception = TransactionException('Test error', transaction)
        
        assert str(exception) == 'Test error'
        assert exception.transaction == transaction


class TestRollbackService:
    """Test cases for RollbackService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = RollbackService()
        
    def test_execute_rollback_empty_transaction(self):
        """Test rollback with empty transaction."""
        transaction = RepositoryUpdateTransaction('test-repo')
        
        result = self.service.execute_rollback(transaction)
        
        assert result.success is True
        assert len(result.actions_rolled_back) == 0
        assert 'No actions to rollback' in result.message
        
    def test_execute_rollback_git_reset_success(self):
        """Test successful git reset rollback."""
        transaction = RepositoryUpdateTransaction('test-repo')
        action = RollbackAction(
            action_type='git_reset',
            description='Reset to previous commit',
            rollback_data={'commit_sha': 'abc123'}
        )
        transaction.add_action(action)
        
        # Mock successful git reset
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'HEAD is now at abc123'
        
        with patch('subprocess.run', return_value=mock_result):
            result = self.service.execute_rollback(transaction)
            
        assert result.success is True
        assert len(result.actions_rolled_back) == 1
        assert 'git_reset' in result.actions_rolled_back
        
    def test_execute_rollback_git_reset_failure(self):
        """Test failed git reset rollback."""
        transaction = RepositoryUpdateTransaction('test-repo')
        action = RollbackAction(
            action_type='git_reset',
            description='Reset to previous commit',
            rollback_data={'commit_sha': 'abc123'}
        )
        transaction.add_action(action)
        
        # Mock failed git reset
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = 'fatal: bad revision'
        
        with patch('subprocess.run', return_value=mock_result):
            result = self.service.execute_rollback(transaction)
            
        assert result.success is False
        assert 'Failed to rollback git_reset' in result.message
        
    def test_execute_rollback_delete_branch_success(self):
        """Test successful branch deletion rollback."""
        transaction = RepositoryUpdateTransaction('test-repo')
        action = RollbackAction(
            action_type='delete_branch',
            description='Delete feature branch',
            rollback_data={'branch_name': 'feature/test'}
        )
        transaction.add_action(action)
        
        # Mock successful branch deletion
        mock_result = Mock()
        mock_result.returncode = 0
        
        with patch('subprocess.run', return_value=mock_result):
            result = self.service.execute_rollback(transaction)
            
        assert result.success is True
        assert len(result.actions_rolled_back) == 1
        
    def test_execute_rollback_delete_files_success(self):
        """Test successful file deletion rollback."""
        # Create temporary test files
        temp_dir = tempfile.mkdtemp()
        test_file1 = os.path.join(temp_dir, 'test1.txt')
        test_file2 = os.path.join(temp_dir, 'test2.txt')
        
        with open(test_file1, 'w') as f:
            f.write('test content 1')
        with open(test_file2, 'w') as f:
            f.write('test content 2')
            
        transaction = RepositoryUpdateTransaction('test-repo')
        action = RollbackAction(
            action_type='delete_files',
            description='Delete temporary files',
            rollback_data={'file_paths': [test_file1, test_file2]}
        )
        transaction.add_action(action)
        
        try:
            result = self.service.execute_rollback(transaction)
            
            assert result.success is True
            assert len(result.actions_rolled_back) == 1
            assert not os.path.exists(test_file1)
            assert not os.path.exists(test_file2)
            
        finally:
            # Clean up
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
                
    def test_execute_rollback_delete_files_partial_failure(self):
        """Test file deletion rollback with some files missing."""
        # Create one real file and reference one non-existent file
        temp_dir = tempfile.mkdtemp()
        test_file1 = os.path.join(temp_dir, 'test1.txt')
        test_file2 = os.path.join(temp_dir, 'nonexistent.txt')
        
        with open(test_file1, 'w') as f:
            f.write('test content')
            
        transaction = RepositoryUpdateTransaction('test-repo')
        action = RollbackAction(
            action_type='delete_files',
            description='Delete files',
            rollback_data={'file_paths': [test_file1, test_file2]}
        )
        transaction.add_action(action)
        
        try:
            result = self.service.execute_rollback(transaction)
            
            # Should still succeed even if some files don't exist
            assert result.success is True
            assert not os.path.exists(test_file1)
            
        finally:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
                
    def test_execute_rollback_multiple_actions(self):
        """Test rollback with multiple actions in correct order."""
        transaction = RepositoryUpdateTransaction('test-repo')
        
        # Add actions in order
        action1 = RollbackAction('action1', 'First action', {})
        action2 = RollbackAction('action2', 'Second action', {})
        action3 = RollbackAction('git_reset', 'Reset commit', {'commit_sha': 'abc123'})
        
        transaction.add_action(action1)
        transaction.add_action(action2)
        transaction.add_action(action3)
        
        # Mock git reset success
        mock_result = Mock()
        mock_result.returncode = 0
        
        with patch('subprocess.run', return_value=mock_result):
            result = self.service.execute_rollback(transaction)
            
        # Should rollback in reverse order: action3, action2, action1
        assert result.success is True
        assert len(result.actions_rolled_back) == 3
        
    def test_execute_rollback_unknown_action_type(self):
        """Test rollback with unknown action type."""
        transaction = RepositoryUpdateTransaction('test-repo')
        action = RollbackAction(
            action_type='unknown_action',
            description='Unknown action',
            rollback_data={}
        )
        transaction.add_action(action)
        
        result = self.service.execute_rollback(transaction)
        
        # Should skip unknown actions but continue
        assert result.success is True
        assert len(result.actions_rolled_back) == 0
        
    def test_execute_rollback_git_command_exception(self):
        """Test rollback when git command raises exception."""
        transaction = RepositoryUpdateTransaction('test-repo')
        action = RollbackAction(
            action_type='git_reset',
            description='Reset commit',
            rollback_data={'commit_sha': 'abc123'}
        )
        transaction.add_action(action)
        
        # Mock subprocess exception
        with patch('subprocess.run', side_effect=Exception('Command failed')):
            result = self.service.execute_rollback(transaction)
            
        assert result.success is False
        assert 'Exception during rollback' in result.message
