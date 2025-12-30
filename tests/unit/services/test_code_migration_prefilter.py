import shutil
from pathlib import Path

import pytest

from src.services.code_migration_service import CodeMigrationService


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


class TestCodeMigrationPrefilter:
    def test_extract_search_terms_only_known_keys(self):
        rules = [
            {
                "name": "Remove obsolete AddAnalyzerDelegatingHandler",
                "target_nodes": [
                    {
                        "type": "InvocationExpression",
                        "method_name": "AddAnalyzerDelegatingHandler",
                        "containing_namespace": "Microsoft.Extensions.Http",
                    }
                ],
                "action": {"type": "remove_invocation", "strategy": "smart_chain_aware"},
            }
        ]

        terms = CodeMigrationService.extract_search_terms(rules)

        assert "AddAnalyzerDelegatingHandler" in terms
        assert "Microsoft.Extensions.Http" in terms
        # We should not include action/type strings as search terms.
        assert "remove_invocation" not in terms
        assert "smart_chain_aware" not in terms

    def test_prefilter_uses_grep_when_rg_unavailable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo_root = tmp_path / "repo"
        a = repo_root / "A.cs"
        b = repo_root / "B.cs"

        _write(a, "class A { void M() { AddAnalyzerDelegatingHandler(); } }")
        _write(b, "class B { void M() { Console.WriteLine(\"hi\"); } }")

        grep_path = shutil.which("grep")
        assert grep_path, "grep must be available for this test"

        def fake_which(name: str):
            if name == "rg":
                return None
            if name == "grep":
                return grep_path
            return shutil.which(name)

        monkeypatch.setattr(shutil, "which", fake_which)

        svc = CodeMigrationService("./CSharpMigrationTool")
        rules = [{"target_nodes": [{"method_name": "AddAnalyzerDelegatingHandler"}]}]

        result = svc.prefilter_target_files_local(
            target_files=[str(a), str(b)],
            migration_rules=rules,
            repo_root=str(repo_root),
            prefer_ripgrep=True,
        )

        assert [str(a.resolve())] == result

    def test_prefilter_falls_back_to_python_scan_when_no_tools(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        repo_root = tmp_path / "repo"
        a = repo_root / "A.cs"
        b = repo_root / "B.cs"

        _write(a, "class A { void M() { AddAnalyzerDelegatingHandler(); } }")
        _write(b, "class B { void M() { Console.WriteLine(\"hi\"); } }")

        monkeypatch.setattr(shutil, "which", lambda _name: None)

        svc = CodeMigrationService("./CSharpMigrationTool")
        rules = [{"target_nodes": [{"method_name": "AddAnalyzerDelegatingHandler"}]}]

        result = svc.prefilter_target_files_local(
            target_files=[str(a), str(b)],
            migration_rules=rules,
            repo_root=str(repo_root),
            prefer_ripgrep=True,
        )

        assert [str(a.resolve())] == result
