"""
Migration configuration service for loading and validating package migration rules.
"""
import logging
import yaml
import json
from typing import Dict, List, Optional, Any
from packaging.version import parse as parse_version, Version
import os


class MigrationRule:
    """Represents a single migration rule."""
    
    def __init__(self, rule_data: Dict[str, Any]):
        self.name = rule_data.get('name', '')
        self.target_nodes = rule_data.get('target_nodes', [])
        self.action = rule_data.get('action', {})
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary for serialization."""
        return {
            'name': self.name,
            'target_nodes': self.target_nodes,
            'action': self.action
        }


class MigrationConfiguration:
    """Represents a complete migration configuration for a package."""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.id = config_data.get('id', '')
        self.package_name = config_data.get('package_name', '')
        self.description = config_data.get('description', '')
        self.version_conditions = config_data.get('version_conditions', [])
        self.rules = [MigrationRule(rule) for rule in config_data.get('rules', [])]
        
    def is_applicable(self, old_version: str, new_version: str) -> bool:
        """Check if this migration applies for the given version change."""
        try:
            old_ver = parse_version(old_version)
            new_ver = parse_version(new_version)
            
            for condition in self.version_conditions:
                condition_type = condition.get('type', '')
                condition_version = parse_version(condition.get('version', '0.0.0'))
                
                if condition_type == 'greater_than':
                    if new_ver > condition_version and old_ver <= condition_version:
                        return True
                elif condition_type == 'greater_than_or_equal':
                    if new_ver >= condition_version and old_ver < condition_version:
                        return True
                elif condition_type == 'exact':
                    if new_ver == condition_version:
                        return True
                elif condition_type == 'range':
                    max_version = parse_version(condition.get('max_version', '999.999.999'))
                    if condition_version <= new_ver <= max_version:
                        return True
                        
        except Exception as e:
            logging.warning(f"Failed to parse versions for migration check: {e}")
            return False
            
        return False
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization."""
        return {
            'id': self.id,
            'package_name': self.package_name,
            'description': self.description,
            'version_conditions': self.version_conditions,
            'rules': [rule.to_dict() for rule in self.rules]
        }


class MigrationConfigurationService:
    """Service for loading and managing migration configurations."""
    
    def __init__(self, config_file_path: str):
        self.config_file_path = config_file_path
        self.migrations: Dict[str, MigrationConfiguration] = {}
        self._load_migrations()
        
    def _load_migrations(self) -> None:
        """Load migration configurations from file."""
        if not os.path.exists(self.config_file_path):
            logging.warning(f"Migration config file not found: {self.config_file_path}")
            return
            
        try:
            with open(self.config_file_path, 'r') as f:
                if self.config_file_path.endswith('.json'):
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)
                    
            migrations_data = data.get('migrations', [])
            
            for migration_data in migrations_data:
                migration = MigrationConfiguration(migration_data)
                self.migrations[migration.id] = migration
                
            logging.info(f"Loaded {len(self.migrations)} migration configurations")
            
        except Exception as e:
            logging.error(f"Failed to load migration configuration: {e}")
            raise
            
    def get_migration_by_id(self, migration_id: str) -> Optional[MigrationConfiguration]:
        """Get a specific migration configuration by ID."""
        return self.migrations.get(migration_id)
        
    def get_applicable_migrations(self, package_name: str, old_version: str, new_version: str) -> List[MigrationConfiguration]:
        """Get all applicable migrations for a package version change."""
        applicable = []
        
        for migration in self.migrations.values():
            if (migration.package_name.lower() == package_name.lower() and
                migration.is_applicable(old_version, new_version)):
                applicable.append(migration)
                
        return applicable
        
    def get_migrations_by_package_and_rule_id(self, package_name: str, migration_rule_id: str) -> List[MigrationConfiguration]:
        """Get migrations for a package that match a specific rule ID from config."""
        matching = []
        
        for migration in self.migrations.values():
            if (migration.package_name.lower() == package_name.lower() and
                migration.id == migration_rule_id):
                matching.append(migration)
                
        return matching
        
    def validate_migration_rules(self) -> bool:
        """Validate all loaded migration rules."""
        valid = True
        
        for migration_id, migration in self.migrations.items():
            # Validate required fields
            if not migration.package_name:
                logging.error(f"Migration {migration_id}: package_name is required")
                valid = False
                
            if not migration.version_conditions:
                logging.error(f"Migration {migration_id}: version_conditions is required")
                valid = False
                
            if not migration.rules:
                logging.error(f"Migration {migration_id}: rules is required")
                valid = False
                
            # Validate version conditions
            for condition in migration.version_conditions:
                if 'type' not in condition or 'version' not in condition:
                    logging.error(f"Migration {migration_id}: version condition missing type or version")
                    valid = False
                    
                try:
                    parse_version(condition['version'])
                except Exception:
                    logging.error(f"Migration {migration_id}: invalid version format: {condition['version']}")
                    valid = False
                    
            # Validate rules
            for i, rule in enumerate(migration.rules):
                if not rule.name:
                    logging.error(f"Migration {migration_id}, rule {i}: name is required")
                    valid = False
                    
                if not rule.target_nodes:
                    logging.error(f"Migration {migration_id}, rule {i}: target_nodes is required")
                    valid = False
                    
                if not rule.action or 'type' not in rule.action:
                    logging.error(f"Migration {migration_id}, rule {i}: action.type is required")
                    valid = False
                    
        return valid
