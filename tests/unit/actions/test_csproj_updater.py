"""
Unit tests for CSProjUpdater class.

Tests cover all business logic for:
- Finding .csproj files in repository trees
- Updating package versions in both single-line and multi-line formats
- Handling edge cases and special characters in package names
- Proper regex pattern matching and replacement
- Error handling scenarios
"""

import pytest
import re
from unittest.mock import Mock, patch
from typing import List, Dict

# Import the class under test
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from nuget_package_updater import CSProjUpdater


class TestCSProjUpdater:
    """Test cases for CSProjUpdater class."""

    @pytest.fixture
    def csproj_updater(self):
        """Create a CSProjUpdater instance for testing."""
        return CSProjUpdater("Microsoft.EntityFrameworkCore", "7.0.1")

    @pytest.fixture
    def special_chars_updater(self):
        """Create a CSProjUpdater instance with special characters in package name."""
        return CSProjUpdater("Microsoft.Extensions.DependencyInjection", "7.0.1")

    def test_init(self, csproj_updater):
        """Test CSProjUpdater initialization."""
        assert csproj_updater.package_name == "Microsoft.EntityFrameworkCore"
        assert csproj_updater.new_version == "7.0.1"

    def test_init_with_special_characters(self, special_chars_updater):
        """Test initialization with package names containing special characters."""
        assert special_chars_updater.package_name == "Microsoft.Extensions.DependencyInjection"
        assert special_chars_updater.new_version == "7.0.1"

    def test_find_csproj_files_empty_tree(self, csproj_updater):
        """Test finding .csproj files in an empty tree."""
        tree = []
        result = csproj_updater.find_csproj_files(tree)
        assert result == []

    def test_find_csproj_files_no_csproj_files(self, csproj_updater):
        """Test finding .csproj files when none exist."""
        tree = [
            {"name": "README.md", "type": "blob", "path": "README.md"},
            {"name": "src", "type": "tree", "path": "src"},
            {"name": "Program.cs", "type": "blob", "path": "src/Program.cs"},
            {"name": "appsettings.json", "type": "blob", "path": "src/appsettings.json"}
        ]
        result = csproj_updater.find_csproj_files(tree)
        assert result == []

    def test_find_csproj_files_single_file(self, csproj_updater):
        """Test finding a single .csproj file."""
        tree = [
            {"name": "README.md", "type": "blob", "path": "README.md"},
            {"name": "MyProject.csproj", "type": "blob", "path": "src/MyProject.csproj"},
            {"name": "Program.cs", "type": "blob", "path": "src/Program.cs"}
        ]
        result = csproj_updater.find_csproj_files(tree)
        assert result == ["src/MyProject.csproj"]

    def test_find_csproj_files_multiple_files(self, csproj_updater):
        """Test finding multiple .csproj files."""
        tree = [
            {"name": "WebAPI.csproj", "type": "blob", "path": "src/WebAPI/WebAPI.csproj"},
            {"name": "Tests.csproj", "type": "blob", "path": "tests/Tests.csproj"},
            {"name": "Common.csproj", "type": "blob", "path": "src/Common/Common.csproj"},
            {"name": "README.md", "type": "blob", "path": "README.md"}
        ]
        result = csproj_updater.find_csproj_files(tree)
        expected = ["src/WebAPI/WebAPI.csproj", "tests/Tests.csproj", "src/Common/Common.csproj"]
        assert sorted(result) == sorted(expected)

    def test_find_csproj_files_case_sensitivity(self, csproj_updater):
        """Test that .csproj file detection is case-sensitive."""
        tree = [
            {"name": "Project.csproj", "type": "blob", "path": "Project.csproj"},
            {"name": "Project.CSPROJ", "type": "blob", "path": "Project.CSPROJ"},
            {"name": "project.csproj", "type": "blob", "path": "project.csproj"}
        ]
        result = csproj_updater.find_csproj_files(tree)
        # Only files ending with lowercase .csproj should be found
        assert "Project.csproj" in result
        assert "project.csproj" in result
        assert "Project.CSPROJ" not in result

    def test_find_csproj_files_ignores_directories(self, csproj_updater):
        """Test that directory names ending with .csproj are ignored."""
        tree = [
            {"name": "Project.csproj", "type": "tree", "path": "Project.csproj"},  # Directory
            {"name": "Real.csproj", "type": "blob", "path": "src/Real.csproj"}    # File
        ]
        result = csproj_updater.find_csproj_files(tree)
        assert result == ["src/Real.csproj"]

    @patch('logging.info')
    def test_find_csproj_files_logging(self, mock_logging, csproj_updater):
        """Test that finding .csproj files logs the count."""
        tree = [
            {"name": "Project1.csproj", "type": "blob", "path": "Project1.csproj"},
            {"name": "Project2.csproj", "type": "blob", "path": "Project2.csproj"}
        ]
        csproj_updater.find_csproj_files(tree)
        mock_logging.assert_called_once_with("Found 2 .csproj files")

    def test_update_package_version_single_line_format(self, csproj_updater):
        """Test updating package version in single-line format."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        assert 'Version="7.0.1"' in updated_content
        assert 'Version="6.0.0"' not in updated_content
        # Ensure other packages are not affected
        assert 'Newtonsoft.Json" Version="13.0.1"' in updated_content

    def test_update_package_version_multi_line_format(self, csproj_updater):
        """Test updating package version in multi-line format."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>6.0.0</Version>
    </PackageReference>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        assert '<Version>7.0.1</Version>' in updated_content
        assert '<Version>6.0.0</Version>' not in updated_content
        # Ensure other packages are not affected
        assert 'Newtonsoft.Json" Version="13.0.1"' in updated_content

    def test_update_package_version_mixed_formats(self, csproj_updater):
        """Test updating package version when both formats are present."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>5.0.0</Version>
    </PackageReference>
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        assert 'Version="7.0.1"' in updated_content
        assert '<Version>7.0.1</Version>' in updated_content
        assert 'Version="6.0.0"' not in updated_content
        assert '<Version>5.0.0</Version>' not in updated_content

    def test_update_package_version_no_target_package(self, csproj_updater):
        """Test updating when target package is not present."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
    <PackageReference Include="AutoMapper" Version="11.0.1" />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is False
        assert updated_content == content

    def test_update_package_version_case_insensitive(self, csproj_updater):
        """Test that package name matching is case-insensitive."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="microsoft.entityframeworkcore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        assert 'Version="7.0.1"' in updated_content

    def test_update_package_version_with_extra_whitespace(self, csproj_updater):
        """Test updating with extra whitespace in XML."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference   Include="Microsoft.EntityFrameworkCore"   Version="6.0.0"   />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        assert 'Version="7.0.1"' in updated_content

    def test_update_package_version_special_characters_in_name(self, special_chars_updater):
        """Test updating package with special characters in name."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.Extensions.DependencyInjection" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = special_chars_updater.update_package_version(content)

        assert modified is True
        assert 'Microsoft.Extensions.DependencyInjection" Version="7.0.1"' in updated_content

    def test_update_package_version_multiple_occurrences(self, csproj_updater):
        """Test updating multiple occurrences of the same package."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
  <ItemGroup Condition="'$(Configuration)' == 'Debug'">
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        # Should update both occurrences
        assert updated_content.count('Version="7.0.1"') == 2
        assert 'Version="6.0.0"' not in updated_content

    def test_update_package_version_preserves_other_attributes_first_format(self, csproj_updater):
        """Test that the first format (Version at end) is handled correctly."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        assert 'Version="7.0.1"' in updated_content

    def test_update_package_version_simple_multiline_format(self, csproj_updater):
        """Test updating simple multi-line format."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>6.0.0</Version>
    </PackageReference>
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        assert '<Version>7.0.1</Version>' in updated_content
        assert '<Version>6.0.0</Version>' not in updated_content

    def test_update_package_version_attributes_after_version_not_supported(self, csproj_updater):
        """Test that current implementation doesn't support attributes after Version."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" PrivateAssets="all" />
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        # Current implementation cannot handle this format
        assert modified is False
        assert updated_content == content

    def test_update_package_version_multiline_with_other_elements_not_supported(self, csproj_updater):
        """Test that current implementation doesn't support multiline with other elements."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>6.0.0</Version>
      <PrivateAssets>all</PrivateAssets>
    </PackageReference>
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        # Current implementation cannot handle this format due to strict regex
        assert modified is False
        assert updated_content == content

    def test_update_package_version_similar_package_names(self):
        """Test that similar package names don't interfere with each other."""
        updater = CSProjUpdater("Microsoft.EntityFrameworkCore", "7.0.1")

        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.Tools" Version="6.0.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore.Design" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = updater.update_package_version(content)

        assert modified is True
        # Only the exact match should be updated
        lines = updated_content.split('\n')
        ef_core_line = next(line for line in lines if 'Microsoft.EntityFrameworkCore" Version=' in line)
        assert 'Version="7.0.1"' in ef_core_line

        # Other packages should remain unchanged
        assert 'Microsoft.EntityFrameworkCore.Tools" Version="6.0.0"' in updated_content
        assert 'Microsoft.EntityFrameworkCore.Design" Version="6.0.0"' in updated_content

    def test_update_package_version_empty_content(self, csproj_updater):
        """Test updating empty content."""
        content = ""
        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is False
        assert updated_content == ""

    def test_update_package_version_malformed_xml(self, csproj_updater):
        """Test updating malformed XML content."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0"
  </ItemGroup>
</Project>'''

        # Should not crash, but also should not modify
        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is False
        assert updated_content == content

    def test_update_package_version_version_with_special_chars(self):
        """Test updating to version with special characters."""
        updater = CSProjUpdater("Microsoft.EntityFrameworkCore", "7.0.1-preview.1")

        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = updater.update_package_version(content)

        assert modified is True
        assert 'Version="7.0.1-preview.1"' in updated_content

    def test_update_package_version_regex_escaping(self):
        """Test that special regex characters in package names are properly escaped."""
        # Package name with regex special characters
        updater = CSProjUpdater("Microsoft.AspNetCore.Mvc.Core", "7.0.1")

        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.Mvc.Core" Version="6.0.0" />
  </ItemGroup>
</Project>'''

        updated_content, modified = updater.update_package_version(content)

        assert modified is True
        assert 'Microsoft.AspNetCore.Mvc.Core" Version="7.0.1"' in updated_content

    def test_update_package_version_returns_tuple(self, csproj_updater):
        """Test that update_package_version returns proper tuple type."""
        content = '''<PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />'''

        result = csproj_updater.update_package_version(content)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)  # updated_content
        assert isinstance(result[1], bool)  # modified

    def test_update_package_version_multiline_indentation_preserved(self, csproj_updater):
        """Test that indentation is preserved in multiline format updates."""
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>6.0.0</Version>
    </PackageReference>
  </ItemGroup>
</Project>'''

        updated_content, modified = csproj_updater.update_package_version(content)

        assert modified is True
        # Check that the replacement maintains proper indentation
        assert '''<PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>7.0.1</Version>
    </PackageReference>''' in updated_content
