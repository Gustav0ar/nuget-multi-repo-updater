
import os
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.services.command_handlers import UpdateNugetCommandHandler
from src.strategies.local_clone_strategy import LocalCloneStrategy
from src.services.config_service import ConfigurationService
from src.providers.gitlab_provider import GitLabProvider

class TestExtensionMethodMigration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.csharp_project_dir = Path(self.temp_dir) / "csharp_project"
        os.makedirs(self.csharp_project_dir)

        self.csharp_project_file_content = """
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net9.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Sdk" Version="1.0.0" />
  </ItemGroup>
</Project>
"""

        self.program_cs_content = """
using Shared.Analyzer.Extensions.AnalyzerExtensions;

namespace SomeApp;

public static class HttpClientExtensions
{
    public static void UseHttpClient(this IServiceCollection services, IConfiguration configuration)
    {
        var httpClientBuilder = services.AddHttpClient()
                  .AddResilienceHandler()
                  .CustomDelegatingHandler()
                  .AddHttpMessageHander<TokenHandler>();
    }
}
"""

        self.extensions_cs_content = """
namespace Shared.Analyzer.Extensions.AnalyzerExtensions;

public static class AnalyzerExtensions
{
    public static IHttpClientBuilder CustomDelegatingHandler(this IHttpClientBuilder builder)
    {
        return builder;
    }
}
"""

        with open(self.csharp_project_dir / "csharp_project.csproj", "w") as f:
            f.write(self.csharp_project_file_content)

        with open(self.csharp_project_dir / "Program.cs", "w") as f:
            f.write(self.program_cs_content)

        os.makedirs(self.csharp_project_dir / "Shared/Analyzer/Extensions/AnalyzerExtensions", exist_ok=True)
        with open(self.csharp_project_dir / "Shared/Analyzer/Extensions/AnalyzerExtensions/AnalyzerExtensions.cs", "w") as f:
            f.write(self.extensions_cs_content)

        self.migration_config_content = """
migrations:
  - id: 'remove-custom-delegating-handler'
    package_name: 'Microsoft.NET.Sdk'
    description: 'Remove CustomDelegatingHandler() calls'
    version_conditions:
      - type: 'greater_than'
        version: '1.0.0'
    rules:
      - name: 'Remove CustomDelegatingHandler() calls'
        target_nodes:
          - type: 'InvocationExpression'
            method_name: 'CustomDelegatingHandler'
            containing_namespace: 'Shared.Analyzer.Extensions.AnalyzerExtensions'
        action:
          type: 'remove_invocation'
          strategy: 'smart_chain_aware'
"""

        with open(Path(self.temp_dir) / "migration-config.yml", "w") as f:
            f.write(self.migration_config_content)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_extension_method_migration(self):
        # Arrange
        class MockScmProvider(GitLabProvider):
            def get_project(self, repo_id):
                return {"id": repo_id, "default_branch": "main", "ssh_url_to_repo": ""}

            def check_existing_merge_request(self, repo_id, title, target_branch):
                return None

            def create_merge_request(self, repo_id, source_branch, target_branch, title, description):
                return {"web_url": "https://fake.com/mr/1"}

        class MockGitService:
            def __init__(self):
                self.local_path = None

            def clone_repository(self, repo_url):
                return self.local_path

            def create_branch(self, branch_name):
                pass

            def checkout_branch(self, branch_name):
                pass

            def add(self, files):
                pass

            def commit(self, message):
                pass

            def push(self, remote, branch):
                pass

            def get_current_branch(self):
                return "main"

            def branch_exists(self, branch_name):
                return False

            def delete_branch(self, branch_name):
                pass

            def cleanup_repository(self):
                pass

        class MockLocalCloneStrategy(LocalCloneStrategy):
            def __init__(self, git_service, scm_provider, csharp_project_dir):
                super().__init__(git_service, scm_provider)
                self.csharp_project_dir = csharp_project_dir

            def prepare_repository(self, repo_url, repo_id):
                self.git_service.local_path = str(self.csharp_project_dir)
                return True

        config_service = ConfigurationService(str(Path(self.temp_dir) / "migration-config.yml"))
        gitlab_provider = MockScmProvider("https://gitlab.com", "fake_token", False)
        git_service = MockGitService()
        strategy = MockLocalCloneStrategy(git_service, gitlab_provider, self.csharp_project_dir)
        handler = UpdateNugetCommandHandler(gitlab_provider, config_service, strategy=strategy)

        def mock_get_repositories(args, repository_manager, user_interaction):
            return [
                {
                    "id": "123",
                    "name": "csharp_project",
                    "ssh_url_to_repo": "",
                    "default_branch": "main"
                }
            ]

        handler._get_repositories = mock_get_repositories

        class Args:
            config_file = str(Path(self.temp_dir) / "migration-config.yml")
            gitlab_url = None
            gitlab_token = None
            discover_group = None
            repositories = None
            repo_file = None
            ignore_patterns = None
            owned_only = None
            member_only = None
            include_archived = None
            exclude_forks = None
            max_repositories = None
            dry_run = False
            allow_downgrade = False
            report_file = None
            packages = ["Microsoft.NET.Sdk@2.0.0"]
            use_local_clone = True
            no_verify_ssl = True
            log_level = "DEBUG"
            enable_migrations = True
            migration_config = str(Path(self.temp_dir) / "migration-config.yml")
            strict_migration_mode = True
            use_most_recent_branch = False
            branch_filter = None

        # Act
        handler.execute(Args())

        # Assert
        with open(self.csharp_project_dir / "Program.cs", "r") as f:
            content = f.read()
            self.assertNotIn(".CustomDelegatingHandler()", content)

if __name__ == '__main__':
    unittest.main()
