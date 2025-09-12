"""
Test runner for comprehensive integration tests.
Organizes and executes all NuGet update workflow tests.
"""

import pytest
import sys
import os
from pathlib import Path

# Add the src directory to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_all_integration_tests():
    """Run all integration tests with comprehensive reporting."""
    test_args = [
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "--strict-markers",  # Strict marker checking
        "--disable-warnings",  # Disable pytest warnings for cleaner output
        "-x",  # Stop on first failure for debugging
        "--durations=10",  # Show 10 slowest tests
        "tests/integration/",  # Run only integration tests
    ]

    return pytest.main(test_args)


def run_specific_test_module(module_name):
    """Run a specific test module."""
    test_args = [
        "-v",
        "--tb=short",
        f"tests/integration/{module_name}",
    ]

    return pytest.main(test_args)


def run_tests_with_coverage():
    """Run tests with coverage reporting."""
    try:
        import pytest_cov
        test_args = [
            "-v",
            "--cov=src",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--cov-branch",
            "tests/integration/",
        ]
        return pytest.main(test_args)
    except ImportError:
        print("pytest-cov not installed. Install with: pip install pytest-cov")
        return run_all_integration_tests()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run NuGet update integration tests")
    parser.add_argument(
        "--module",
        choices=[
            "test_nuget_update_flows.py",
            "test_error_handling.py",
            "test_status_and_repository_management.py",
            "test_configuration_and_real_world.py"
        ],
        help="Run specific test module"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run tests with coverage reporting"
    )

    args = parser.parse_args()

    if args.coverage:
        exit_code = run_tests_with_coverage()
    elif args.module:
        exit_code = run_specific_test_module(args.module)
    else:
        exit_code = run_all_integration_tests()

    sys.exit(exit_code)
