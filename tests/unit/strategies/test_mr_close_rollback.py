from unittest.mock import Mock

from src.services.rollback_service import RepositoryUpdateTransaction
from src.strategies.api_strategy import ApiStrategy
from src.strategies.local_clone_strategy import LocalCloneStrategy


def test_api_strategy_registers_close_mr_on_rollback():
    provider = Mock()
    provider.create_merge_request.return_value = {"iid": 7, "web_url": "u"}
    provider.close_merge_request.return_value = True

    strategy = ApiStrategy(provider)
    tx = RepositoryUpdateTransaction("proj", strategy)
    strategy.set_transaction(tx)

    mr = strategy.create_merge_request("proj", "b", "main", "t", "d")
    assert mr["iid"] == 7

    tx.execute_rollback()
    provider.close_merge_request.assert_called_once_with("proj", "7")


def test_local_strategy_registers_close_mr_on_rollback():
    git_service = Mock()
    provider = Mock()
    provider.create_merge_request.return_value = {"iid": 9, "web_url": "u"}
    provider.close_merge_request.return_value = True

    strategy = LocalCloneStrategy(git_service, provider)
    tx = RepositoryUpdateTransaction("proj", strategy)
    strategy.set_transaction(tx)

    mr = strategy.create_merge_request("proj", "b", "main", "t", "d")
    assert mr["iid"] == 9

    tx.execute_rollback()
    provider.close_merge_request.assert_called_once_with("proj", "9")
