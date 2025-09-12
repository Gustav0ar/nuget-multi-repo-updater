from datetime import datetime

class ReportGenerator:
    """Service for generating reports."""

    def __init__(self):
        self.report_data = []

    def add_entry(self, repo_name: str, package_name: str, new_version: str, status: str, details: str):
        """Add an entry to the report."""
        self.report_data.append({
            'repo_name': repo_name,
            'package_name': package_name,
            'new_version': new_version,
            'status': status,
            'details': details
        })

    def generate(self, output_file: str):
        """Generate the report file."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{output_file}_{timestamp}.md"

        with open(filename, 'w') as f:
            f.write(f"# NuGet Package Update Report\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            for entry in self.report_data:
                f.write(f"## Repository: {entry['repo_name']}\n")
                f.write(f"- **Package**: {entry['package_name']}\n")
                f.write(f"  - **Version**: {entry['new_version']}\n")
                f.write(f"  - **Status**: {entry['status']}\n")
                f.write(f"  - **Details**: {entry['details']}\n\n")
        
        return filename
