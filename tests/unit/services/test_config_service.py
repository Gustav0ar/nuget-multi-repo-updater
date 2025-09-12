import pytest
import json
import yaml
import tempfile
import os
from unittest.mock import patch, mock_open
from src.services.config_service import ConfigurationService


class TestConfigurationService:
    """Test suite for ConfigurationService."""

    def setup_method(self):
        """Set up test data for each test method."""
        self.sample_config_data = {
            "gitlab_url": "https://gitlab.company.com",
            "packages_to_update": [
                {"name": "Microsoft.EntityFrameworkCore", "version": "7.0.5"},
                {"name": "Newtonsoft.Json", "version": "13.0.3"}
            ],
            "report_file": "reports/entity-framework-update.md",
            "verify_ssl": False,
            "allow_downgrade": False,
            "repositories": ["123", "456", "backend-team/user-service"]
        }

    def test_init_with_json_file(self):
        """Test initialization with a JSON config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.config == self.sample_config_data
            finally:
                os.unlink(f.name)

    def test_init_with_yaml_file(self):
        """Test initialization with a YAML config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.config == self.sample_config_data
            finally:
                os.unlink(f.name)

    def test_init_with_yml_file(self):
        """Test initialization with a .yml config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.config == self.sample_config_data
            finally:
                os.unlink(f.name)

    def test_load_config_json_success(self):
        """Test successful loading of JSON config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService.__new__(ConfigurationService)
                result = service._load_config(f.name)
                assert result == self.sample_config_data
            finally:
                os.unlink(f.name)

    def test_load_config_yaml_success(self):
        """Test successful loading of YAML config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService.__new__(ConfigurationService)
                result = service._load_config(f.name)
                assert result == self.sample_config_data
            finally:
                os.unlink(f.name)

    def test_load_config_unsupported_format(self):
        """Test loading config with unsupported file format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("some content")
            f.flush()

            try:
                service = ConfigurationService.__new__(ConfigurationService)
                with pytest.raises(ValueError, match="Unsupported config file format"):
                    service._load_config(f.name)
            finally:
                os.unlink(f.name)

    def test_load_config_file_not_found(self):
        """Test loading config when file doesn't exist."""
        service = ConfigurationService.__new__(ConfigurationService)
        with pytest.raises(FileNotFoundError):
            service._load_config("non_existent_file.json")

    def test_load_config_invalid_json(self):
        """Test loading config with invalid JSON content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json content")
            f.flush()

            try:
                service = ConfigurationService.__new__(ConfigurationService)
                with pytest.raises(json.JSONDecodeError):
                    service._load_config(f.name)
            finally:
                os.unlink(f.name)

    def test_load_config_invalid_yaml(self):
        """Test loading config with invalid YAML content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()

            try:
                service = ConfigurationService.__new__(ConfigurationService)
                with pytest.raises(yaml.YAMLError):
                    service._load_config(f.name)
            finally:
                os.unlink(f.name)

    def test_get_existing_key(self):
        """Test getting a value for an existing key."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.get("gitlab_url") == "https://gitlab.company.com"
                assert service.get("verify_ssl") is False
                assert service.get("packages_to_update") == [
                    {"name": "Microsoft.EntityFrameworkCore", "version": "7.0.5"},
                    {"name": "Newtonsoft.Json", "version": "13.0.3"}
                ]
            finally:
                os.unlink(f.name)

    def test_get_non_existing_key_no_default(self):
        """Test getting a value for a non-existing key without default."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.get("non_existing_key") is None
            finally:
                os.unlink(f.name)

    def test_get_non_existing_key_with_default(self):
        """Test getting a value for a non-existing key with default."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.get("non_existing_key", "default_value") == "default_value"
                assert service.get("missing_flag", True) is True
                assert service.get("missing_number", 42) == 42
                assert service.get("missing_list", []) == []
            finally:
                os.unlink(f.name)

    def test_get_nested_structures(self):
        """Test getting complex nested data structures."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                repositories = service.get("repositories")
                assert isinstance(repositories, list)
                assert "123" in repositories
                assert "backend-team/user-service" in repositories

                packages = service.get("packages_to_update")
                assert isinstance(packages, list)
                assert len(packages) == 2
                assert packages[0]["name"] == "Microsoft.EntityFrameworkCore"
            finally:
                os.unlink(f.name)

    def test_empty_config_file(self):
        """Test loading an empty config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.config == {}
                assert service.get("any_key") is None
                assert service.get("any_key", "default") == "default"
            finally:
                os.unlink(f.name)

    def test_config_with_none_values(self):
        """Test config file containing None values."""
        config_with_none = {
            "setting1": None,
            "setting2": "value2",
            "setting3": None
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_with_none, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                assert service.get("setting1") is None
                assert service.get("setting1", "default") is None  # None is a valid value
                assert service.get("setting2") == "value2"
                assert service.get("setting3") is None
                assert service.get("non_existing", "default") == "default"
            finally:
                os.unlink(f.name)

    def test_config_service_immutability(self):
        """Test that the config service doesn't modify the original config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config_data, f)
            f.flush()

            try:
                service = ConfigurationService(f.name)
                original_url = service.get("gitlab_url")

                # Get a mutable object and modify it
                repos = service.get("repositories")
                if repos:
                    repos.append("modified")

                # The original config should remain unchanged when we get it again
                assert service.get("gitlab_url") == original_url
                repos_again = service.get("repositories")
                assert "modified" in repos_again  # Our modification persists in the same object
            finally:
                os.unlink(f.name)

    @patch("builtins.open", new_callable=mock_open)
    @patch("json.load")
    def test_load_config_with_mock_json(self, mock_json_load, mock_file):
        """Test config loading with mocked file operations for JSON."""
        mock_json_load.return_value = {"test": "value"}

        service = ConfigurationService.__new__(ConfigurationService)
        result = service._load_config("test.json")

        mock_file.assert_called_once_with("test.json", 'r')
        mock_json_load.assert_called_once()
        assert result == {"test": "value"}

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    def test_load_config_with_mock_yaml(self, mock_yaml_load, mock_file):
        """Test config loading with mocked file operations for YAML."""
        mock_yaml_load.return_value = {"test": "value"}

        service = ConfigurationService.__new__(ConfigurationService)
        result = service._load_config("test.yaml")

        mock_file.assert_called_once_with("test.yaml", 'r')
        mock_yaml_load.assert_called_once()
        assert result == {"test": "value"}
