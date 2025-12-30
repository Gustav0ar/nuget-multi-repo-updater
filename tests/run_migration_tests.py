"""
Test runner for the migration and rollback testing suite.
"""
import pytest
import sys
import os
from pathlib import Path

# Add the workspace root to Python path for imports
workspace_root = Path(__file__).parent.parent
sys.path.insert(0, str(workspace_root))

# Add the src directory to Python path for imports
src_path = workspace_root / 'src'
sys.path.insert(0, str(src_path))

# Set PYTHONPATH environment variable for subprocess calls
os.environ['PYTHONPATH'] = str(workspace_root)


def run_unit_tests():
    """Run all unit tests."""
    print("Running unit tests for migration services...")
    
    test_files = [
        'tests/unit/services/test_migration_configuration_service.py',
        'tests/unit/services/test_code_migration_service.py',
        'tests/unit/services/test_rollback_service.py'
    ]
    
    # Run each test file
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"\n--- Running {test_file} ---")
            result = pytest.main(['-v', test_file])
            if result != 0:
                print(f"Tests failed in {test_file}")
                return False
        else:
            print(f"Warning: Test file {test_file} not found")
    
    return True


def run_integration_tests():
    """Run integration tests."""
    print("\nRunning integration tests...")
    
    test_files = [
        'tests/integration/test_migration_workflow.py',
        'tests/integration/test_csharp_tool_integration.py'
    ]
    
    # Run each integration test file
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"\n--- Running {test_file} ---")
            result = pytest.main(['-v', test_file])
            if result != 0:
                print(f"Integration tests failed in {test_file}")
                return False
        else:
            print(f"Warning: Test file {test_file} not found")
    
    return True


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("MIGRATION FEATURE TEST SUITE")
    print("=" * 60)
    
    # Run unit tests first
    unit_success = run_unit_tests()
    
    if unit_success:
        print("\nUnit tests passed!")
        
        # Run integration tests
        integration_success = run_integration_tests()
        
        if integration_success:
            print("\nAll tests passed!")
            print("\nMigration feature implementation is ready for deployment!")
            return True
        else:
            print("\nIntegration tests failed!")
            return False
    else:
        print("\nUnit tests failed!")
        return False


def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run migration feature tests')
    parser.add_argument('--unit', action='store_true', help='Run only unit tests')
    parser.add_argument('--integration', action='store_true', help='Run only integration tests')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.unit:
        success = run_unit_tests()
    elif args.integration:
        success = run_integration_tests()
    else:
        success = run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
