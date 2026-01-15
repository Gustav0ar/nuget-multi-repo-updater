import os
import pytest
import time
from testcontainers.compose import DockerCompose

@pytest.mark.integration
class TestContainerizedMigration:
    @pytest.fixture(scope="class")
    def compose(self):
        # Path to the directory containing compose.yaml
        compose_path = os.path.join(os.path.dirname(__file__), "container_specs")
        
        # Ensure we use the correct compose file
        # Use podman as the executable since docker is not available
        compose = DockerCompose(compose_path, compose_file_name="compose.yaml", pull=True, docker_command_path="podman", wait=False)
        
        # Start the container
        compose.start()
        
        # Wait for container to be ready (tail -f /dev/null starts immediately, but let's give it a sec)
        time.sleep(2)
        
        yield compose
        
        # Stop the container
        compose.stop()

    def test_environment_setup(self, compose):
        """Verify the container environment has necessary tools."""
        # Check dotnet version
        output, stderr, exit_code = compose.exec_in_container(["dotnet", "--version"], service_name="migration-runner")
        assert exit_code == 0
        assert output.strip().startswith("10.")
        
        # Check python version
        output, stderr, exit_code = compose.exec_in_container(["python3", "--version"], service_name="migration-runner")
        assert exit_code == 0
        assert "Python 3" in output

    def test_full_migration_flow(self, compose):
        """
        Test the full migration flow inside the container:
        1. Create a test project structure.
        2. Run the migration tool.
        3. Verify file changes.
        """
        # 1. Setup test project inside the container
        setup_script = """
import os
import shutil

if os.path.exists("test_project"):
    shutil.rmtree("test_project")

os.makedirs("test_project", exist_ok=True)
with open("test_project/TestProject.csproj", "w") as f:
    f.write('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="12.0.1" />
  </ItemGroup>
</Project>''')

with open("test_project/Program.cs", "w") as f:
    f.write('''using System;
using Newtonsoft.Json;

namespace TestProject
{
    class Program
    {
        static void Main(string[] args)
        {
            var obj = new { Name = "Test" };
            // This method should be renamed if we apply the rule
            var json = JsonConvert.SerializeObjectAsync(obj).Result;
            Console.WriteLine(json);
        }
    }
}''')

# Create a migration config
with open("test_project/migration.yml", "w") as f:
    f.write('''migrations:
  - id: "newtonsoft-test"
    package_name: "Newtonsoft.Json"
    version_conditions:
      - type: "greater_than"
        version: "13.0.0"
    rules:
      - name: "Rename SerializeObjectAsync"
        target_nodes:
          - type: "InvocationExpression"
            method_name: "SerializeObjectAsync"
        action:
          type: "replace_invocation"
          replacement_method: "SerializeAsync"
''')

# Create a tool config
import json
config = {
    "gitlab_url": "https://gitlab.example.com",
    "token": "dummy",
    "use_local_clone": True,
    "enable_code_migrations": True,
    "migration_config_file": "test_project/migration.yml",
    "packages_to_update": [
        {"name": "Newtonsoft.Json", "version": "13.0.3"}
    ],
    "repositories": ["test_project"]
}
with open("test_project/config.json", "w") as f:
    json.dump(config, f)
"""
        # Write setup script to a file in the container
        compose.exec_in_container(["python3", "-c", setup_script], service_name="migration-runner")

        # 2. Run the migration
        # We need to point to the CSharpMigrationTool. 
        # Assuming the workspace is mounted at /app, the tool is at /app/CSharpMigrationTool
        # We need to build it inside the container to be sure, or use the host built one.
        # Let's build it inside to be safe and robust.
        
        build_cmd = ["dotnet", "build", "/app/CSharpMigrationTool/CSharpMigrationTool.csproj", "-c", "Debug"]
        output, stderr, exit_code = compose.exec_in_container(build_cmd, service_name="migration-runner")
        assert exit_code == 0, f"Build failed: {output} {stderr}"

        # Now run the update-nuget command
        # We need to mock the GitLab part or use local clone strategy.
        # The config uses "use_local_clone": True.
        # But "repositories": ["test_project"] implies a local path?
        # The tool expects repository IDs or paths. If local clone is used, it might expect a git repo.
        # Let's initialize git in the test project.
        
        git_init_script = """
import os
import subprocess

os.chdir("test_project")
subprocess.run(["git", "init"], check=True)
subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
subprocess.run(["git", "config", "user.name", "Test User"], check=True)
subprocess.run(["git", "add", "."], check=True)
subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)
"""
        compose.exec_in_container(["python3", "-c", git_init_script], service_name="migration-runner")

        # Run the tool
        # We need to make sure the CSharpMigrationTool path is correctly found.
        # The CodeMigrationService looks for it. We might need to set an env var or ensure it's in a standard place.
        # Or we can pass the path if the tool supports it? No, it's hardcoded or config based?
        # Let's check CodeMigrationService.
        
        # For now, let's try running it.
        # We use --repo-file or --repositories.
        # Since we are in /app, and test_project is in /app/test_project (or relative to where we run).
        # We run from /app.
        
        run_cmd = [
            "python3", "run.py", "update-nuget",
            "--config-file", "test_project/config.json",
            "--repositories", "test_project",
            "--use-local-clone",
            "--log-level", "DEBUG"
        ]
        
        output, stderr, exit_code = compose.exec_in_container(run_cmd, service_name="migration-runner")

        # Assert success
        assert exit_code == 0, f"Migration failed: {output} {stderr}"

        # 3. Verify changes
        # The changes are pushed to a new branch in the origin repo (test_project)
        # We need to find that branch and checkout it
        
        checkout_script = """
import subprocess
import os

os.chdir("test_project")
branches = subprocess.check_output(["git", "branch"]).decode("utf-8").splitlines()
for branch in branches:
    branch = branch.strip().replace("* ", "")
    if branch != "master":
        print(f"Checking out {branch}")
        subprocess.run(["git", "checkout", branch], check=True)
        break
"""
        output, stderr, exit_code = compose.exec_in_container(["python3", "-c", checkout_script], service_name="migration-runner")
        assert exit_code == 0, f"Failed to checkout branch: {output} {stderr}"

        # Check .csproj
        cat_csproj = ["cat", "test_project/TestProject.csproj"]
        output, stderr, exit_code = compose.exec_in_container(cat_csproj, service_name="migration-runner")
        csproj_content = output
        assert 'Include="Newtonsoft.Json" Version="13.0.3"' in csproj_content
        
        # Check .cs file for migration
        cat_cs = ["cat", "test_project/Program.cs"]
        output, stderr, exit_code = compose.exec_in_container(cat_cs, service_name="migration-runner")
        cs_content = output
        assert "JsonConvert.SerializeAsync(obj)" in cs_content
        assert "SerializeObjectAsync" not in cs_content

    def test_complex_multi_package_migration(self, compose):
        """
        Test a complex scenario with multiple package updates and code migrations.
        """
        # 1. Setup complex test project
        setup_script = """
import os
import shutil

if os.path.exists("complex_project"):
    shutil.rmtree("complex_project")+

os.makedirs("complex_project", exist_ok=True)
with open("complex_project/ComplexProject.csproj", "w") as f:
    f.write('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="12.0.1" />
    <PackageReference Include="Serilog" Version="2.10.0" />
  </ItemGroup>
</Project>''')

with open("complex_project/Program.cs", "w") as f:
            f.write('''using System;
    using Newtonsoft.Json;
    using Serilog;
    
    namespace ComplexProject
    {
        class Program
        {
            static void Main(string[] args)
            {
                var obj = new { Name = "Test" };
                // Rule 1: Rename method
                var json = JsonConvert.SerializeObjectAsync(obj).Result;
    
                // Rule 2: Rename method
                var logger = new LoggerConfiguration().CreateLogger();
    
                Console.WriteLine(json);
        }
    }
}''')

# Create migration config with multiple rules
with open("complex_project/migration.yml", "w") as f:
    f.write('''migrations:
  - id: "newtonsoft-update"
    package_name: "Newtonsoft.Json"
    version_conditions:
      - type: "greater_than"
        version: "13.0.0"
    rules:
      - name: "Rename SerializeObjectAsync"
        target_nodes:
          - type: "InvocationExpression"
            method_name: "SerializeObjectAsync"
        action:
          type: "replace_invocation"
          replacement_method: "SerializeAsync"

  - id: "serilog-update"
    package_name: "Serilog"
    version_conditions:
      - type: "greater_than"
        version: "3.0.0"
    rules:
      - name: "Rename CreateLogger to Build"
        target_nodes:
          - type: "InvocationExpression"
            method_name: "CreateLogger"
        action:
          type: "replace_invocation"
          replacement_method: "Build"
''')

# Create tool config
import json
config = {
    "gitlab_url": "https://gitlab.example.com",
    "token": "dummy",
    "use_local_clone": True,
    "enable_code_migrations": True,
    "migration_config_file": "complex_project/migration.yml",
    "packages_to_update": [
        {"name": "Newtonsoft.Json", "version": "13.0.3"},
        {"name": "Serilog", "version": "3.1.1"}
    ],
    "repositories": ["complex_project"]
}
with open("complex_project/config.json", "w") as f:
    json.dump(config, f)
"""
        compose.exec_in_container(["python3", "-c", setup_script], service_name="migration-runner")

        # 2. Initialize git
        git_init_script = """
import os
import subprocess

os.chdir("complex_project")
subprocess.run(["git", "init"], check=True)
subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
subprocess.run(["git", "config", "user.name", "Test User"], check=True)
subprocess.run(["git", "add", "."], check=True)
subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)
"""
        compose.exec_in_container(["python3", "-c", git_init_script], service_name="migration-runner")

        # 3. Run the tool
        run_cmd = [
            "python3", "run.py", "update-nuget",
            "--config-file", "complex_project/config.json",
            "--repositories", "complex_project",
            "--use-local-clone",
            "--log-level", "DEBUG"
        ]
        
        output, stderr, exit_code = compose.exec_in_container(run_cmd, service_name="migration-runner")
        assert exit_code == 0, f"Migration failed: {output} {stderr}"

        # 4. Verify changes
        
        # Checkout the new branch
        checkout_script = """
import subprocess
import os

os.chdir("complex_project")
branches = subprocess.check_output(["git", "branch"]).decode("utf-8").splitlines()
for branch in branches:
    branch = branch.strip().replace("* ", "")
    if branch != "master":
        print(f"Checking out {branch}")
        subprocess.run(["git", "checkout", branch], check=True)
        break
"""
        output, stderr, exit_code = compose.exec_in_container(["python3", "-c", checkout_script], service_name="migration-runner")
        assert exit_code == 0, f"Failed to checkout branch: {output} {stderr}"

        # Check .csproj for both updates
        cat_csproj = ["cat", "complex_project/ComplexProject.csproj"]
        output, stderr, exit_code = compose.exec_in_container(cat_csproj, service_name="migration-runner")
        csproj_content = output
        
        assert 'Include="Newtonsoft.Json" Version="13.0.3"' in csproj_content
        assert 'Include="Serilog" Version="3.1.1"' in csproj_content
        
        # Check .cs file for both migrations
        cat_cs = ["cat", "complex_project/Program.cs"]
        output, stderr, exit_code = compose.exec_in_container(cat_cs, service_name="migration-runner")
        cs_content = output
        
        # Verify Newtonsoft migration
        assert "JsonConvert.SerializeAsync(obj)" in cs_content
        assert "SerializeObjectAsync" not in cs_content
        
        # Verify Serilog migration
        assert "new LoggerConfiguration().Build()" in cs_content
        assert "CreateLogger" not in cs_content

    def test_method_removal_scenarios(self, compose):
        """
        Test removing specific method calls from fluent API chains.
        Scenarios:
        1. Remove full line
        2. Remove full line (split)
        3. Remove from chain (middle)
        4. Remove from chain (start)
        """
        # 1. Setup test project inside the container
        setup_script = """
import os
import json
import yaml
import shutil

if os.path.exists("removal_project"):
    shutil.rmtree("removal_project")

os.makedirs("removal_project", exist_ok=True)

# Create .csproj
csproj_content = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.Extensions.Http" Version="8.0.0" />
  </ItemGroup>
</Project>'''

with open("removal_project/RemovalProject.csproj", "w") as f:
    f.write(csproj_content)

# Create Program.cs with scenarios
program_cs = '''using System;
using Microsoft.Extensions.DependencyInjection;

namespace RemovalProject
{
    public class Program
    {
        public static void Main(string[] args)
        {
            var services = new ServiceCollection();
            var httpClientBuilder = services.AddHttpClient("test");

            // Scenario 1: Remove full line
            httpClientBuilder.AddAnalyzerDelegatingHandler();

            // Scenario 2: Remove full line (split)
            httpClientBuilder
                .AddAnalyzerDelegatingHandler();

            // Scenario 3: Remove from chain (middle)
            httpClientBuilder.AnotherExtension().AddAnalyzerDelegatingHandler().AnotherExtension2();

            // Scenario 4: Remove from chain (start)
            httpClientBuilder.AddAnalyzerDelegatingHandler().OtherExtension();
        }
    }

    public static class Extensions
    {
        public static IHttpClientBuilder AddAnalyzerDelegatingHandler(this IHttpClientBuilder builder) => builder;
        public static IHttpClientBuilder AnotherExtension(this IHttpClientBuilder builder) => builder;
        public static IHttpClientBuilder AnotherExtension2(this IHttpClientBuilder builder) => builder;
        public static IHttpClientBuilder OtherExtension(this IHttpClientBuilder builder) => builder;
    }
}'''

with open("removal_project/Program.cs", "w") as f:
    f.write(program_cs)

# Create migration config (migration.yml)
migration_config = {
    "migrations": [
        {
            "id": "http-client-update",
            "package_name": "Microsoft.Extensions.Http",
            "version_conditions": [
                {
                    "type": "greater_than",
                    "version": "8.0.0"
                }
            ],
            "rules": [
                {
                    "name": "Remove AddAnalyzerDelegatingHandler",
                    "target_nodes": [
                        {
                            "type": "InvocationExpression",
                            "method_name": "AddAnalyzerDelegatingHandler"
                        }
                    ],
                    "action": {
                        "type": "remove_invocation"
                    }
                }
            ]
        }
    ]
}

with open("removal_project/migration.yml", "w") as f:
    yaml.dump(migration_config, f)

# Create tool config (config.json)
config = {
    "gitlab_url": "https://gitlab.example.com",
    "token": "dummy",
    "use_local_clone": True,
    "enable_code_migrations": True,
    "migration_config_file": "removal_project/migration.yml",
    "packages_to_update": [
        {"name": "Microsoft.Extensions.Http", "version": "8.0.1"}
    ],
    "repositories": ["removal_project"]
}

with open("removal_project/config.json", "w") as f:
    json.dump(config, f)
"""
        compose.exec_in_container(["python3", "-c", setup_script], service_name="migration-runner")

        # 2. Initialize git
        git_init_script = """
import os
import subprocess

os.chdir("removal_project")
subprocess.run(["git", "init"], check=True)
subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
subprocess.run(["git", "config", "user.name", "Test User"], check=True)
subprocess.run(["git", "add", "."], check=True)
subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)
"""
        compose.exec_in_container(["python3", "-c", git_init_script], service_name="migration-runner")

        # 3. Run the tool
        run_cmd = [
            "python3", "run.py", "update-nuget",
            "--config-file", "removal_project/config.json",
            "--repositories", "removal_project",
            "--use-local-clone",
            "--log-level", "DEBUG"
        ]
        
        output, stderr, exit_code = compose.exec_in_container(run_cmd, service_name="migration-runner")
        print(f"Migration Output: {output}")
        print(f"Migration Stderr: {stderr}")
        assert exit_code == 0, f"Migration failed: {output} {stderr}"

        # 4. Verify changes
        
        # Checkout the new branch
        checkout_script = """
import subprocess
import os

os.chdir("removal_project")
branches = subprocess.check_output(["git", "branch"]).decode("utf-8").splitlines()
for branch in branches:
    branch = branch.strip().replace("* ", "")
    if branch != "master":
        print(f"Checking out {branch}")
        subprocess.run(["git", "checkout", branch], check=True)
        break
"""
        output, stderr, exit_code = compose.exec_in_container(["python3", "-c", checkout_script], service_name="migration-runner")
        assert exit_code == 0, f"Failed to checkout branch: {output} {stderr}"

        cat_cs = ["cat", "removal_project/Program.cs"]
        output, stderr, exit_code = compose.exec_in_container(cat_cs, service_name="migration-runner")
        cs_content = output
        
        # Verify Scenario 1: Line removed
        assert "httpClientBuilder.AddAnalyzerDelegatingHandler();" not in cs_content
        
        # Verify Scenario 2: Split line removed
        assert ".AddAnalyzerDelegatingHandler();" not in cs_content
        
        # Verify Scenario 3: Middle of chain removed
        # Should become: httpClientBuilder.AnotherExtension().AnotherExtension2();
        assert "httpClientBuilder.AnotherExtension().AnotherExtension2();" in cs_content
        
        # Verify Scenario 4: Start of chain removed
        # Should become: httpClientBuilder.OtherExtension();
        assert "httpClientBuilder.OtherExtension();" in cs_content


