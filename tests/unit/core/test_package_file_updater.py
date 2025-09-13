"""
Unit tests for core package file updater functionality.
"""
import pytest
from src.core.package_file_updater import PackageFileUpdater


class TestPackageFileUpdater:
    """Unit tests for PackageFileUpdater."""
    
    def test_update_package_version_basic(self):
        """Test basic package version update."""
        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
  </ItemGroup>
</Project>'''
        
        updater = PackageFileUpdater('Microsoft.EntityFrameworkCore', '7.0.0')
        updated_content, was_modified = updater.update_csproj_package_version(content, False)
        
        assert was_modified
        assert '7.0.0' in updated_content
        assert '6.0.0' not in updated_content
    
    def test_update_package_version_not_found(self):
        """Test package update when package is not found."""
        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="SomeOtherPackage" Version="1.0.0" />
  </ItemGroup>
</Project>'''
        
        updater = PackageFileUpdater('Microsoft.EntityFrameworkCore', '7.0.0')
        updated_content, was_modified = updater.update_csproj_package_version(content, False)
        
        # Should return original content unchanged
        assert not was_modified
        assert updated_content == content
    
    def test_update_package_version_case_insensitive(self):
        """Test package update is case insensitive."""
        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="microsoft.entityframeworkcore" Version="6.0.0" />
  </ItemGroup>
</Project>'''
        
        updater = PackageFileUpdater('Microsoft.EntityFrameworkCore', '7.0.0')
        updated_content, was_modified = updater.update_csproj_package_version(content, False)
        
        # Should modify because package names are matched case insensitively
        assert was_modified
        assert '7.0.0' in updated_content
        assert '6.0.0' not in updated_content
    
    def test_update_package_version_multiline_format(self):
        """Test package update with multiline format."""
        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore">
      <Version>6.0.0</Version>
    </PackageReference>
  </ItemGroup>
</Project>'''
        
        updater = PackageFileUpdater('Microsoft.EntityFrameworkCore', '7.0.0')
        updated_content, was_modified = updater.update_csproj_package_version(content, False)
        
        assert was_modified
        assert '7.0.0' in updated_content
        assert '6.0.0' not in updated_content
    
    def test_downgrade_prevention(self):
        """Test that downgrades are prevented when not allowed."""
        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="7.0.0" />
  </ItemGroup>
</Project>'''
        
        updater = PackageFileUpdater('Microsoft.EntityFrameworkCore', '6.0.0')
        updated_content, was_modified = updater.update_csproj_package_version(content, False)
        
        # Should not downgrade when allow_downgrade is False
        assert not was_modified
        assert updated_content == content
    
    def test_downgrade_allowed(self):
        """Test that downgrades are allowed when explicitly enabled."""
        content = '''<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="7.0.0" />
  </ItemGroup>
</Project>'''
        
        updater = PackageFileUpdater('Microsoft.EntityFrameworkCore', '6.0.0')
        updated_content, was_modified = updater.update_csproj_package_version(content, True)
        
        # Should downgrade when allow_downgrade is True
        assert was_modified
        assert '6.0.0' in updated_content
        assert '7.0.0' not in updated_content
