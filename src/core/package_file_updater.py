"""
Generic file updater for package version updates.
"""
import logging
import re
from typing import Tuple
from packaging.version import parse as parse_version


class PackageFileUpdater:
    """Generic handler for updating package versions in project files."""

    def __init__(self, package_name: str, new_version: str):
        self.package_name = package_name
        self.new_version = new_version

    def update_csproj_package_version(self, file_content: str, allow_downgrade: bool) -> Tuple[str, bool]:
        """
        Update package version in .csproj file content.
        Returns: (updated_content, was_modified)
        """
        # Pattern to match single-line PackageReference with the target package
        pattern = rf'<PackageReference\s+Include="{re.escape(self.package_name)}"\s+Version="([^"]*)"[^>]*/?>'

        # Also handle multi-line format
        multiline_pattern = rf'<PackageReference\s+Include="{re.escape(self.package_name)}"\s*>\s*<Version>([^<]*)</Version>\s*</PackageReference>'

        updated_content = file_content
        modified = False
        old_version_str = None

        newline = "\r\n" if "\r\n" in file_content else "\n"

        # Check for single-line format first
        match = re.search(pattern, updated_content, re.IGNORECASE)
        if match:
            old_version_str = match.group(1)

            if not self._should_update_version(old_version_str, allow_downgrade):
                return file_content, False

            replacement = f'<PackageReference Include="{self.package_name}" Version="{self.new_version}" />'
            updated_content = re.sub(pattern, replacement, updated_content, flags=re.IGNORECASE)
            modified = True
        else:
            # Check for multi-line format
            match = re.search(multiline_pattern, updated_content, re.IGNORECASE | re.DOTALL)
            if match:
                old_version_str = match.group(1)

                if not self._should_update_version(old_version_str, allow_downgrade):
                    return file_content, False

                multiline_replacement = (
                    f'<PackageReference Include="{self.package_name}">{newline}'
                    f'      <Version>{self.new_version}</Version>{newline}'
                    f'    </PackageReference>'
                )
                updated_content = re.sub(multiline_pattern, multiline_replacement, updated_content, flags=re.IGNORECASE | re.DOTALL)
                modified = True

        return updated_content, modified

    def update_package_json_version(self, file_content: str, allow_downgrade: bool) -> Tuple[str, bool]:
        """
        Update package version in package.json file content.
        Returns: (updated_content, was_modified)
        """
        # This could be extended for Node.js package.json files
        # Implementation would parse JSON and update dependencies
        raise NotImplementedError("package.json updates not yet implemented")

    def _should_update_version(self, old_version_str: str, allow_downgrade: bool) -> bool:
        """Check if the version should be updated based on downgrade policy."""
        if old_version_str == self.new_version:
            logging.info(f"Package {self.package_name} is already at version {self.new_version}")
            return False

        if not allow_downgrade:
            try:
                old_version = parse_version(old_version_str)
                new_version = parse_version(self.new_version)
                if new_version < old_version:
                    logging.warning(f"Skipping downgrade for package {self.package_name} from {old_version_str} to {self.new_version}")
                    return False
            except Exception as e:
                logging.warning(f"Could not parse version for comparison: {e}")

        return True
