#!/usr/bin/env python
"""
Test the flow display with agents centered and tools on sides.
"""

from praisonaiagents.flow_display import track_workflow

# Create flow tracker
flow = track_workflow()
flow.tracking = True

# Simulate a workflow
# Agent 1 with multiple tools
flow._add_agent("Researcher")
flow._add_tool("Researcher", "web_search")
flow._add_tool("Researcher", "fetch_data")
flow._add_tool("Researcher", "parse_html")

# Agent 2 with one tool
flow._add_agent("Analyst")
flow._add_tool("Analyst", "analyze_data")

# Agent 3 with multiple tools
flow._add_agent("Reporter")
flow._add_tool("Reporter", "format_report")
flow._add_tool("Reporter", "send_email")
flow._add_tool("Reporter", "save_file")
flow._add_tool("Reporter", "upload_cloud")

# Agent 4 with no tools
flow._add_agent("Reviewer")

# Display the flow
flow.tracking = False
flow.display()