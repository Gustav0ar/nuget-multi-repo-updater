import os
from unittest.mock import Mock

from src.services.code_migration_service import MigrationResult
from src.strategies.api_strategy import ApiStrategy


class _FakeCodeMigrationService:
    def __init__(self, tool_path: str):
        self.tool_path = tool_path

    @staticmethod
    def extract_search_terms(_rules):
        return []

    def execute_migrations(self, target_files, migration_rules, working_directory=None):
        # Simulate the tool modifying the first downloaded file.
        assert target_files
        os.makedirs(os.path.dirname(target_files[0]), exist_ok=True)
        with open(target_files[0], "w", encoding="utf-8", newline="") as f:
            f.write("// migrated\n")

        return MigrationResult(
            success=True,
            modified_files=[target_files[0]],
            applied_rules=["R"],
            errors=[],
            summary="ok",
        )

    def validate_tool_availability(self):
        return True


def test_api_strategy_uploads_modified_temp_file(monkeypatch, tmp_path):
    # Provider: one C# file available via API
    provider = Mock()
    provider.get_file_content.return_value = "// original\n"
    provider.update_file.return_value = True

    strategy = ApiStrategy(provider)

    # Patch CodeMigrationService used inside execute_csharp_migration_tool
    monkeypatch.setattr(
        "src.services.code_migration_service.CodeMigrationService",
        _FakeCodeMigrationService,
        raising=True,
    )

    rules_path = tmp_path / "rules.json"
    rules_path.write_text('{"rules": []}', encoding="utf-8")

    result = strategy.execute_csharp_migration_tool(
        repo_id="proj",
        rules_file=str(rules_path),
        target_files=["src/A.cs"],
        branch_name="feature/test",
    )

    assert result.success is True
    assert result.modified_files == ["src/A.cs"]  # reported as repo paths in API mode
    provider.update_file.assert_called_once()
    args, _kwargs = provider.update_file.call_args
    assert args[0] == "proj"
    assert args[1] == "src/A.cs"
    assert "// migrated" in args[2]
    assert args[4] == "feature/test"
