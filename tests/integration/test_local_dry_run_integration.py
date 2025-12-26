import os
import shutil
import pytest
from unittest.mock import MagicMock, patch
from src.services.dry_run_service import DryRunService
from src.services.git_service import GitService
from src.providers.scm_provider import ScmProvider
from src.services.migration_configuration_service import MigrationConfigurationService
from src.services.code_migration_service import MigrationResult

@pytest.mark.integration
class TestLocalDryRunIntegration:
    def setup_method(self):
        self.test_dir = os.path.abspath("test_local_dry_run_repo")
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
        # Create a dummy .csproj
        with open(os.path.join(self.test_dir, "Test.csproj"), "w") as f:
            f.write('''<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="12.0.1" />
  </ItemGroup>
</Project>''')

        # Initialize git
        os.system(f"cd {self.test_dir} && git init && git config user.email 'test@example.com' && git config user.name 'Test' && git add . && git commit -m 'Init'")

    def teardown_method(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_local_dry_run_execution(self, capsys):
        """Test basic local dry run with package updates."""
        # Mock ScmProvider
        scm_provider = MagicMock(spec=ScmProvider)
        repo_info = {
            'id': 'test-repo-id',
            'name': 'test_local_dry_run_repo',
            'path_with_namespace': 'group/test_local_dry_run_repo',
            'ssh_url_to_repo': self.test_dir, # Use local path as URL for cloning
            'http_url_to_repo': self.test_dir,
            'default_branch': 'master'
        }
        scm_provider.get_project.return_value = repo_info
        scm_provider.check_existing_merge_request.return_value = None
        
        # Mock args
        args = MagicMock()
        args.allow_downgrade = False
        args.strict_migration_mode = False
        
        service = DryRunService(scm_provider)
        service._disable_exit = True  # Prevent sys.exit
        
        repositories = [repo_info]
        packages = [{'name': 'Newtonsoft.Json', 'version': '13.0.1'}]
        
        # Run the dry run
        service.perform_local_dry_run(repositories, packages, args, None, False)
        
        # Capture output
        captured = capsys.readouterr()
        output = captured.out
        
        # Assertions
        assert "LOCAL DRY RUN MODE - CLONE & APPLY" in output
        assert "Code migration: Disabled" in output
        assert "Changes applied successfully (Dry Run)" in output
        assert "Newtonsoft.Json to 13.0.1" in output
        
        # Verify that the original repo was NOT modified (since it clones to a temp dir)
        with open(os.path.join(self.test_dir, "Test.csproj"), "r") as f:
            content = f.read()
            assert 'Version="12.0.1"' in content
            assert 'Version="13.0.1"' not in content

    def test_local_dry_run_with_migration(self, capsys):
        """Test local dry run with mocked migration execution."""
        # Setup C# file for migration
        with open(os.path.join(self.test_dir, "Program.cs"), "w") as f:
            f.write('''using Newtonsoft.Json;
public class Program {
    public void Main() {
        var x = JsonConvert.SerializeObjectAsync(new object());
    }
}''')
        os.system(f"cd {self.test_dir} && git add Program.cs && git commit -m 'Add Program.cs'")

        # Mock ScmProvider
        scm_provider = MagicMock(spec=ScmProvider)
        scm_provider.check_existing_merge_request.return_value = None
        repo_info = {
            'id': 'test-repo-id',
            'name': 'test_local_dry_run_repo',
            'path_with_namespace': 'group/test_local_dry_run_repo',
            'ssh_url_to_repo': self.test_dir,
            'http_url_to_repo': self.test_dir,
            'default_branch': 'master'
        }
        
        # Mock Migration Config
        migration_config_service = MagicMock(spec=MigrationConfigurationService)
        mock_migration = MagicMock()
        mock_rule = MagicMock()
        mock_rule.to_dict.return_value = {
            'name': 'Rename SerializeObjectAsync',
            'target_nodes': [{'type': 'InvocationExpression', 'method_name': 'SerializeObjectAsync'}],
            'action': {'type': 'replace_invocation', 'replacement_method': 'SerializeAsync'}
        }
        mock_migration.rules = [mock_rule]
        migration_config_service.get_migrations_for_package.return_value = [mock_migration]
        
        # Mock the C# tool execution to avoid needing the built binary
        with patch('src.strategies.local_clone_strategy.LocalCloneStrategy.execute_csharp_migration_tool') as mock_tool:
            # Setup mock return
            mock_result = MigrationResult(
                success=True,
                modified_files=['Program.cs'],
                applied_rules=['Rename SerializeObjectAsync'],
                errors=[],
                summary="Mocked success"
            )
            mock_tool.return_value = mock_result
            
            # Mock args
            args = MagicMock()
            args.allow_downgrade = False
            args.strict_migration_mode = False
            
            service = DryRunService(scm_provider)
            service._disable_exit = True
            
            repositories = [repo_info]
            packages = [{'name': 'Newtonsoft.Json', 'version': '13.0.1'}]
            
            service.perform_local_dry_run(repositories, packages, args, migration_config_service, True)
            
            captured = capsys.readouterr()
            output = captured.out
            
            assert "Code migration: Enabled" in output
            assert "Applied Migration Rules (1)" in output
            assert "Rename SerializeObjectAsync" in output
            assert "Modified Files" in output
            assert "Program.cs" in output
