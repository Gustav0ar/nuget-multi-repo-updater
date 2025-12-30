import json
import logging
from typing import List, Dict, Optional
from datetime import datetime

from src.core.action import Action
from src.providers.scm_provider import ScmProvider


class StatusCheckAction(Action):
    """Action to check and update the status of merge requests."""

    def __init__(self, scm_provider: ScmProvider, tracking_file: str, report_only: bool = False):
        self.scm_provider = scm_provider
        self.tracking_file = tracking_file
        self.report_only = report_only
        self.tracking_data = None
        self.stats = {
            'total_mrs': 0,
            'opened': 0,
            'merged': 0,
            'closed': 0,
            'errors': 0,
            'updated': 0
        }

    def execute(self):
        """Execute the status check action."""
        # Load tracking data
        if not self.load_tracking_data(self.tracking_file):
            return False

        if not self.report_only:
            # Update all MR statuses
            self.update_all_statuses()

            # Save updated tracking data
            self.save_tracking_data(self.tracking_file)

        return True

    def load_tracking_data(self, file_path: str) -> bool:
        """Load merge request tracking data from JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.tracking_data = json.load(f)

            self.stats['total_mrs'] = len(self.tracking_data.get('merge_requests', []))
            logging.info(f"Loaded tracking data for {self.stats['total_mrs']} merge requests")
            return True

        except FileNotFoundError:
            logging.error(f"Tracking file not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in tracking file {file_path}: {e}")
            return False
        except Exception as e:
            logging.error(f"Error loading tracking file {file_path}: {e}")
            return False

    def update_mr_status(self, mr_entry: Dict) -> bool:
        """Update the status of a single merge request."""
        try:
            # Get current MR status from GitLab
            if mr_entry.get('merge_request_iid') and mr_entry.get('repository_id'):
                # Use project ID and MR IID if available
                status = self.scm_provider.get_merge_request_status(
                    str(mr_entry['repository_id']),
                    str(mr_entry['merge_request_iid'])
                )
            else:
                logging.error(f"Insufficient data to fetch MR for {mr_entry.get('repository_name', 'unknown')}")
                return False

            if not status:
                self.stats['errors'] += 1
                return False

            # Update tracking data with current information
            old_status = mr_entry.get('status', 'unknown')
            new_status = status

            mr_entry['status'] = new_status
            mr_entry['last_checked'] = datetime.now().isoformat()

            # Track statistics
            if old_status != new_status:
                self.stats['updated'] += 1
                logging.info(f"Status updated for {mr_entry['repository_name']}: {old_status} → {new_status}")

            return True

        except Exception as e:
            logging.error(f"Error updating MR status for {mr_entry.get('repository_name', 'unknown')}: {e}")
            self.stats['errors'] += 1
            return False

    def update_all_statuses(self) -> bool:
        """Update status for all merge requests in tracking data."""
        if not self.tracking_data or 'merge_requests' not in self.tracking_data:
            logging.error("No tracking data loaded")
            return False

        logging.info(f"Updating status for {len(self.tracking_data['merge_requests'])} merge requests...")

        for mr_entry in self.tracking_data['merge_requests']:
            self.update_mr_status(mr_entry)

        # Update statistics
        for mr_entry in self.tracking_data['merge_requests']:
            status = mr_entry.get('status', 'unknown')
            if status == 'opened':
                self.stats['opened'] += 1
            elif status == 'merged':
                self.stats['merged'] += 1
            elif status == 'closed':
                self.stats['closed'] += 1

        # Update metadata
        if 'metadata' not in self.tracking_data:
            self.tracking_data['metadata'] = {}
        self.tracking_data['metadata']['last_updated'] = datetime.now().isoformat()

        return True

    def save_tracking_data(self, file_path: str) -> bool:
        """Save updated tracking data back to JSON file."""
        try:
            # Sort merge requests by URL then by status before saving
            if self.tracking_data and 'merge_requests' in self.tracking_data:
                self.tracking_data['merge_requests'].sort(
                    key=lambda mr: (mr.get('merge_request_url', ''), mr.get('status', ''))
                )

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.tracking_data, f, indent=2, ensure_ascii=False)
            logging.info(f"Updated tracking data saved to: {file_path}")
            return True
        except Exception as e:
            logging.error(f"Error saving tracking data to {file_path}: {e}")
            return False

    def generate_status_report(self, output_file: Optional[str] = None) -> str:
        """Generate a status report of all merge requests."""
        if not self.tracking_data:
            return "No tracking data available"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata = self.tracking_data.get('metadata', {})

        report_content = f"""
# Merge Request Status Report
Generated: {timestamp}

## Summary
- **Package**: {metadata.get('package_name', 'Multiple packages')}
- **Version**: {metadata.get('new_version', 'Various versions')}
- **Total Merge Requests**: {self.stats['total_mrs']}
- **Opened**: {self.stats['opened']}
- **Merged**: {self.stats['merged']}
- **Closed**: {self.stats['closed']}
- **Errors**: {self.stats['errors']}
- **Updated This Run**: {self.stats['updated']}

## Merge Request Details

"""

        # Group MRs by status and sort within each group
        mrs_by_status = {
            'merged': [],
            'opened': [],
            'closed': [],
            'unknown': []
        }

        for mr_entry in self.tracking_data.get('merge_requests', []):
            status = mr_entry.get('status', 'unknown')
            if status not in mrs_by_status:
                mrs_by_status['unknown'].append(mr_entry)
            else:
                mrs_by_status[status].append(mr_entry)

        # Sort each status group by URL then status
        for status_list in mrs_by_status.values():
            status_list.sort(key=lambda mr: (mr.get('merge_request_url', ''), mr.get('status', '')))

        # Report merged MRs
        if mrs_by_status['merged']:
            report_content += f"### Merged ({len(mrs_by_status['merged'])})\n\n"
            for mr in mrs_by_status['merged']:
                package_name = mr.get('package_name', 'Unknown')
                new_version = mr.get('new_version', 'Unknown')
                report_content += f"- **{mr['repository_name']}** ({package_name} → {new_version}): [{mr['merge_request_url']}]({mr['merge_request_url']})\n"
                if mr.get('existed'):
                    report_content += f"  - *(Pre-existing MR)*\n"
                report_content += "\n"

        # Report open MRs
        if mrs_by_status['opened']:
            report_content += f"### Open ({len(mrs_by_status['opened'])})\n\n"
            for mr in mrs_by_status['opened']:
                package_name = mr.get('package_name', 'Unknown')
                new_version = mr.get('new_version', 'Unknown')
                report_content += f"- **{mr['repository_name']}** ({package_name} → {new_version}): [{mr['merge_request_url']}]({mr['merge_request_url']})\n"
                if mr.get('existed'):
                    report_content += f"  - *(Pre-existing MR)*\n"
                report_content += "\n"

        # Report closed MRs
        if mrs_by_status['closed']:
            report_content += f"### Closed ({len(mrs_by_status['closed'])})\n\n"
            for mr in mrs_by_status['closed']:
                package_name = mr.get('package_name', 'Unknown')
                new_version = mr.get('new_version', 'Unknown')
                report_content += f"- **{mr['repository_name']}** ({package_name} → {new_version}): [{mr['merge_request_url']}]({mr['merge_request_url']})\n"
                if mr.get('existed'):
                    report_content += f"  - *(Pre-existing MR)*\n"
                report_content += "\n"

        # Report unknown/error status
        if mrs_by_status['unknown']:
            report_content += f"### Unknown Status ({len(mrs_by_status['unknown'])})\n\n"
            for mr in mrs_by_status['unknown']:
                package_name = mr.get('package_name', 'Unknown')
                new_version = mr.get('new_version', 'Unknown')
                report_content += f"- **{mr['repository_name']}** ({package_name} → {new_version}): [{mr['merge_request_url']}]({mr['merge_request_url']})\n"
                report_content += f"  - Status: {mr.get('status', 'Unknown')}\n"
                report_content += "\n"

        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                logging.info(f"Status report saved to: {output_file}")
            except Exception as e:
                logging.error(f"Error saving report to {output_file}: {e}")

        return report_content

    def filter_by_status(self, status: str) -> List[Dict]:
        """Filter merge requests by status."""
        if not self.tracking_data or 'merge_requests' not in self.tracking_data:
            return []

        filtered_mrs = [mr for mr in self.tracking_data['merge_requests']
                       if mr.get('status', '').lower() == status.lower()]

        # Sort filtered results by URL then status
        filtered_mrs.sort(key=lambda mr: (mr.get('merge_request_url', ''), mr.get('status', '')))

        return filtered_mrs

    def generate_html_visualization(self, output_file: str = "mr_status_dashboard.html") -> str:
        """Generate an interactive HTML visualization of merge request status."""
        if not self.tracking_data:
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata = self.tracking_data.get('metadata', {})

        # Prepare data for visualization
        mrs_by_status = {'opened': [], 'merged': [], 'closed': [], 'unknown': []}
        for mr_entry in self.tracking_data.get('merge_requests', []):
            status = mr_entry.get('status', 'unknown')
            if status not in mrs_by_status:
                mrs_by_status['unknown'].append(mr_entry)
            else:
                mrs_by_status[status].append(mr_entry)

        # Sort each status group
        for status_list in mrs_by_status.values():
            status_list.sort(key=lambda mr: (mr.get('merge_request_url', ''), mr.get('status', '')))

        # Generate MR sections HTML
        mr_sections_html = ""

        # Merged section
        if mrs_by_status['merged']:
            mr_items = ""
            for mr in mrs_by_status['merged']:
                package_info = f"{mr.get('package_name', 'Unknown')} → {mr.get('new_version', 'Unknown')}"
                mr_items += f"""
                <div class="mr-item merged">
                    <div class="mr-title">{mr['repository_name']}</div>
                    <div class="mr-url"><a href="{mr['merge_request_url']}" target="_blank">{mr['merge_request_url']}</a></div>
                    <div class="mr-meta">Package: {package_info}</div>
                    {"<div class='mr-meta'><em>Pre-existing MR</em></div>" if mr.get('existed') else ""}
                </div>
                """

            mr_sections_html += f"""
            <div class="mr-section" data-status="merged">
                <div class="section-header" onclick="toggleSection(this)">
                    <span class="section-icon"></span>
                    <span class="section-title">Merged</span>
                    <span class="section-count">{len(mrs_by_status['merged'])}</span>
                    <button class="toggle-btn">▼</button>
                target_branch = mr.get('target_branch', 'Unknown')
                source_branch = mr.get('source_branch', 'Unknown')
                </div>
                <div class="mr-list">
                    {mr_items}
                </div>
            </div>
                    <div class="mr-meta">Target Branch: <strong>{target_branch}</strong> ← Source Branch: <strong>{source_branch}</strong></div>
            """

        # Open section
        if mrs_by_status['opened']:
            mr_items = ""
            for mr in mrs_by_status['opened']:
                package_info = f"{mr.get('package_name', 'Unknown')} → {mr.get('new_version', 'Unknown')}"
                mr_items += f"""
                <div class="mr-item opened">
                    <div class="mr-title">{mr['repository_name']}</div>
                    <div class="mr-url"><a href="{mr['merge_request_url']}" target="_blank">{mr['merge_request_url']}</a></div>
                    <div class="mr-meta">Package: {package_info}</div>
                    {"<div class='mr-meta'><em>Pre-existing MR</em></div>" if mr.get('existed') else ""}
                </div>
                """

            mr_sections_html += f"""
            <div class="mr-section" data-status="opened">
                <div class="section-header" onclick="toggleSection(this)">
                    <span class="section-icon"></span>
                    <span class="section-title">Open</span>
                    <span class="section-count">{len(mrs_by_status['opened'])}</span>
                    <button class="toggle-btn">▼</button>
                target_branch = mr.get('target_branch', 'Unknown')
                source_branch = mr.get('source_branch', 'Unknown')
                </div>
                <div class="mr-list">
                    {mr_items}
                </div>
            </div>
                    <div class="mr-meta">Target Branch: <strong>{target_branch}</strong> ← Source Branch: <strong>{source_branch}</strong></div>
            """

        # Closed section
        if mrs_by_status['closed']:
            mr_items = ""
            for mr in mrs_by_status['closed']:
                package_info = f"{mr.get('package_name', 'Unknown')} → {mr.get('new_version', 'Unknown')}"
                mr_items += f"""
                <div class="mr-item closed">
                    <div class="mr-title">{mr['repository_name']}</div>
                    <div class="mr-url"><a href="{mr['merge_request_url']}" target="_blank">{mr['merge_request_url']}</a></div>
                    <div class="mr-meta">Package: {package_info}</div>
                    {"<div class='mr-meta'><em>Pre-existing MR</em></div>" if mr.get('existed') else ""}
                </div>
                """

            mr_sections_html += f"""
            <div class="mr-section" data-status="closed">
                <div class="section-header" onclick="toggleSection(this)">
                    <span class="section-icon"></span>
                    <span class="section-title">Closed</span>
                    <span class="section-count">{len(mrs_by_status['closed'])}</span>
                    <button class="toggle-btn">▼</button>
                target_branch = mr.get('target_branch', 'Unknown')
                source_branch = mr.get('source_branch', 'Unknown')
                </div>
                <div class="mr-list">
                    {mr_items}
                </div>
            </div>
                    <div class="mr-meta">Target Branch: <strong>{target_branch}</strong> ← Source Branch: <strong>{source_branch}</strong></div>
            """

        # Create HTML content
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Merge Request Status Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.2s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #666;
            font-size: 1.1em;
        }}
        .opened {{ color: #3498db; }}
        .merged {{ color: #27ae60; }}
        .closed {{ color: #e74c3c; }}
        .total {{ color: #9b59b6; }}
        .errors {{ color: #f39c12; }}
        .mr-details {{
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .mr-section {{
            padding: 25px;
            border-bottom: 1px solid #eee;
        }}
        .mr-section:last-child {{
            border-bottom: none;
        }}
        .section-header {{
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            cursor: pointer;
            user-select: none;
        }}
        .section-icon {{
            font-size: 1.5em;
            margin-right: 10px;
        }}
        .section-title {{
            font-size: 1.3em;
            font-weight: bold;
        }}
        .section-count {{
            margin-left: auto;
            background: #f8f9fa;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            color: #666;
        }}
        .mr-list {{
            display: none;
        }}
        .mr-list.active {{
            display: block;
        }}
        .mr-item {{
            background: #f8f9fa;
            margin: 10px 0;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #ddd;
        }}
        .mr-item.opened {{
            border-left-color: #3498db;
        }}
        .mr-item.merged {{
            border-left-color: #27ae60;
        }}
        .mr-item.closed {{
            border-left-color: #e74c3c;
        }}
        .mr-title {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .mr-url {{
            color: #666;
            font-size: 0.9em;
            word-break: break-all;
        }}
        .mr-meta {{
            font-size: 0.85em;
            color: #888;
            margin-top: 8px;
        }}
        .toggle-btn {{
            background: none;
            border: none;
            font-size: 1.2em;
            cursor: pointer;
            margin-left: 10px;
            transition: transform 0.2s;
        }}
        .toggle-btn.rotated {{
            transform: rotate(180deg);
        }}
        .filter-container {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        .filter-title {{
            font-size: 1.2em;
            margin-bottom: 15px;
            font-weight: bold;
        }}
        .filter-buttons {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            padding: 8px 16px;
            border: 2px solid #ddd;
            background: white;
            border-radius: 25px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .filter-btn:hover {{
            background: #f8f9fa;
        }}
        .filter-btn.active {{
            background: #667eea;
            color: white;
            border-color: #667eea;
        }}
        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Merge Request Status Dashboard</h1>
            <p>Multiple Packages Update Status</p>
            <p>Generated: {timestamp}</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number total">{self.stats['total_mrs']}</div>
                <div class="stat-label">Total MRs</div>
            </div>
            <div class="stat-card">
                <div class="stat-number opened">{self.stats['opened']}</div>
                <div class="stat-label">Open</div>
            </div>
            <div class="stat-card">
                <div class="stat-number merged">{self.stats['merged']}</div>
                <div class="stat-label">Merged</div>
            </div>
            <div class="stat-card">
                <div class="stat-number closed">{self.stats['closed']}</div>
                <div class="stat-label">Closed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number errors">{self.stats['errors']}</div>
                <div class="stat-label">Errors</div>
            </div>
        </div>

        <div class="filter-container">
            <div class="filter-title">Filter by Status:</div>
            <div class="filter-buttons">
                <button class="filter-btn active" onclick="filterMRs('all')">All</button>
                <button class="filter-btn" onclick="filterMRs('opened')">Open ({len(mrs_by_status['opened'])})</button>
                <button class="filter-btn" onclick="filterMRs('merged')">Merged ({len(mrs_by_status['merged'])})</button>
                <button class="filter-btn" onclick="filterMRs('closed')">Closed ({len(mrs_by_status['closed'])})</button>
                <button class="filter-btn" onclick="filterMRs('unknown')">Unknown ({len(mrs_by_status['unknown'])})</button>
            </div>
        </div>

        <div class="mr-details">
            {mr_sections_html}
        </div>
    </div>

    <script>
        function toggleSection(header) {{
            const mrList = header.nextElementSibling;
            const toggleBtn = header.querySelector('.toggle-btn');
            
            mrList.classList.toggle('active');
            toggleBtn.classList.toggle('rotated');
        }}

        function filterMRs(status) {{
            const buttons = document.querySelectorAll('.filter-btn');
            const sections = document.querySelectorAll('.mr-section');
            
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            sections.forEach(section => {{
                if (status === 'all' || section.dataset.status === status) {{
                    section.style.display = 'block';
                }} else {{
                    section.style.display = 'none';
                }}
            }});
        }}

        // Initialize - show all sections collapsed
        document.addEventListener('DOMContentLoaded', function() {{
            // Auto-expand merged section if it has items
            const mergedSection = document.querySelector('[data-status="merged"]');
            if (mergedSection) {{
                const header = mergedSection.querySelector('.section-header');
                toggleSection(header);
            }}
        }});
    </script>
</body>
</html>"""

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logging.info(f"HTML dashboard saved to: {output_file}")
            return output_file
        except Exception as e:
            logging.error(f"Error saving HTML dashboard to {output_file}: {e}")
            return None
