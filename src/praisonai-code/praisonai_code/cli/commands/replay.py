"""
Replay command group for PraisonAI CLI.

Provides context replay functionality:
- replay list: List available traces
- replay context <session_id>: Interactive replay of a trace
"""

from typing import Optional

import typer

app = typer.Typer(help="Context replay for debugging agent execution")


@app.command("list")
def replay_list(
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Maximum number of traces to show",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
):
    """List available context traces."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.replay import list_traces
        traces = list_traces(limit=limit)
    except ImportError:
        output.print_error("Replay module not available")
        raise typer.Exit(1)
    
    if json_output or output.is_json_mode:
        output.print_json({
            "traces": [t.to_dict() for t in traces]
        })
        return
    
    if not traces:
        output.print_info("No traces found. Run agents with trace=True to create traces.")
        return
    
    # Format as table
    headers = ["Session ID", "Events", "Size", "Modified"]
    rows = []
    
    for trace in traces:
        modified = trace.modified_at.strftime("%Y-%m-%d %H:%M")
        size_kb = trace.size_bytes / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{trace.size_bytes} B"
        
        rows.append([
            trace.session_id[:40] + "..." if len(trace.session_id) > 40 else trace.session_id,
            str(trace.event_count),
            size_str,
            modified,
        ])
    
    output.print_table(headers, rows, title="Available Context Traces")
    output.print("\nUse 'praisonai replay context <session_id>' to replay a trace.")


@app.command("context")
def replay_context(
    session_id: str = typer.Argument(
        ...,
        help="Session ID or path to trace file",
    ),
    start: int = typer.Option(
        0,
        "--start",
        "-s",
        help="Start from event number (1-based)",
    ),
    no_rich: bool = typer.Option(
        False,
        "--no-rich",
        help="Disable Rich formatting",
    ),
    dump: bool = typer.Option(
        False,
        "--dump",
        "-d",
        help="Dump all events non-interactively (for scripting)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON (implies --dump)",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        "-f",
        help="Show full context content (messages, responses) without truncation",
    ),
    stats: bool = typer.Option(
        False,
        "--stats",
        help="Show session statistics (tokens, costs, duplicates)",
    ),
    cost: bool = typer.Option(
        False,
        "--cost",
        help="Show cost breakdown only",
    ),
):
    """Interactive replay of a context trace.
    
    Use --dump for non-interactive output (useful for scripting/verification).
    Use --json for machine-readable output.
    Use --full to show complete context content at each stage.
    Use --stats to show session statistics (tokens, costs, duplicates).
    Use --cost to show cost breakdown only.
    """
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.replay import ContextTraceReader, ReplayPlayer
        from praisonai.replay.analyzer import TraceAnalyzer, format_stats_output, format_cost_output
    except ImportError:
        output.print_error("Replay module not available")
        raise typer.Exit(1)
    
    # Load trace
    reader = ContextTraceReader(session_id)
    
    if not reader.exists:
        output.print_error(f"Trace not found: {session_id}")
        output.print_info("Use 'praisonai replay list' to see available traces.")
        raise typer.Exit(1)
    
    events = reader.get_all()
    if not events:
        output.print_error(f"No events in trace: {session_id}")
        raise typer.Exit(1)
    
    # Stats mode - show statistics only
    if stats:
        analyzer = TraceAnalyzer(events)
        result = analyzer.analyze()
        if json_output:
            output.print_json(result.to_dict())
        else:
            output.print(format_stats_output(result))
        return
    
    # Cost mode - show cost breakdown only
    if cost:
        analyzer = TraceAnalyzer(events)
        result = analyzer.analyze()
        if json_output:
            output.print_json({"cost": result.to_dict()["cost_stats"]})
        else:
            output.print(format_cost_output(result))
        return
    
    # JSON output implies dump mode
    if json_output:
        dump = True
    
    # Non-interactive dump mode
    if dump:
        _dump_events(output, events, session_id, json_output, full)
        return
    
    output.print_success(f"Loaded {len(events)} events from: {session_id}")
    
    # Create and run player with full mode support
    player = ReplayPlayer(reader, use_rich=not no_rich, full_mode=full)
    
    # Set start position if specified
    if start > 0:
        if player.goto(start - 1):  # Convert to 0-based
            output.print(f"Starting from event {start}")
        else:
            output.print_warning(f"Invalid start position. Valid range: 1-{len(events)}")
    
    player.run()


def _dump_events(output, events, session_id: str, json_output: bool, full: bool = False):
    """Dump all events non-interactively.
    
    Args:
        output: Output controller
        events: List of trace events
        session_id: Session identifier
        json_output: Whether to output as JSON
        full: Whether to show full content without truncation
    """
    # Import analyzer for stats
    from praisonai.replay.analyzer import TraceAnalyzer
    
    if json_output or output.is_json_mode:
        # Include analysis in JSON output
        analyzer = TraceAnalyzer(events)
        result = analyzer.analyze()
        output.print_json({
            "session_id": session_id,
            "total_events": len(events),
            "analysis": result.to_dict(),
            "events": [e.to_dict() if hasattr(e, 'to_dict') else e for e in events],
        })
        return
    
    # Text output - formatted for readability
    output.print(f"\n{'='*60}")
    output.print(f"  CONTEXT REPLAY: {session_id}")
    output.print(f"  Total Events: {len(events)}")
    output.print(f"{'='*60}\n")
    
    # Track running totals
    running_prompt_tokens = 0
    running_completion_tokens = 0
    running_cost = 0.0
    
    for i, event in enumerate(events):
        # Get event details
        if hasattr(event, 'event_type'):
            et = event.event_type
            if hasattr(et, 'value'):
                et = et.value
        else:
            et = event.get('event_type', 'unknown')
        
        agent_name = getattr(event, 'agent_name', None) or (event.get('agent_name') if isinstance(event, dict) else None)
        seq = getattr(event, 'sequence_num', i) or (event.get('sequence_num', i) if isinstance(event, dict) else i)
        branch_id = getattr(event, 'branch_id', None) or (event.get('branch_id') if isinstance(event, dict) else None)
        
        # Get token/cost info
        prompt_tokens = getattr(event, 'prompt_tokens', 0) or (event.get('prompt_tokens', 0) if isinstance(event, dict) else 0)
        completion_tokens = getattr(event, 'completion_tokens', 0) or (event.get('completion_tokens', 0) if isinstance(event, dict) else 0)
        cost_usd = getattr(event, 'cost_usd', 0) or (event.get('cost_usd', 0) if isinstance(event, dict) else 0)
        
        # Update running totals
        running_prompt_tokens += prompt_tokens
        running_completion_tokens += completion_tokens
        running_cost += cost_usd
        
        # Format event header
        header = f"[{seq + 1:3d}] {et.upper()}"
        if agent_name:
            header += f" ({agent_name})"
        if branch_id:
            header += f" [branch: {branch_id}]"
        
        output.print(f"\n{'-'*50}")
        output.print(header)
        
        # Show token/cost info for LLM events
        if prompt_tokens or completion_tokens:
            output.print(f"  prompt_tokens: {prompt_tokens:,}")
            output.print(f"  completion_tokens: {completion_tokens:,}")
        if cost_usd:
            output.print(f"  cost: ${cost_usd:.6f}")
        
        # Show event-specific data
        data = getattr(event, 'data', None) or (event.get('data') if isinstance(event, dict) else None)
        if data:
            for key, value in data.items():
                if value is not None:
                    value_str = str(value)
                    # Full mode: show complete content; otherwise truncate
                    if not full and len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    
                    # For messages array in full mode, format nicely
                    if full and key == "messages" and isinstance(value, list):
                        output.print(f"  {key}:")
                        for msg_idx, msg in enumerate(value):
                            role = msg.get("role", "unknown") if isinstance(msg, dict) else "unknown"
                            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                            output.print(f"    [{msg_idx + 1}] {role}:")
                            # Indent content lines
                            for line in str(content).split('\n')[:20]:  # Limit lines in full mode
                                output.print(f"        {line}")
                            if len(str(content).split('\n')) > 20:
                                output.print(f"        ... ({len(str(content).split(chr(10)))} lines total)")
                    else:
                        output.print(f"  {key}: {value_str}")
        
        # Show token info if available (legacy field)
        tokens_used = getattr(event, 'tokens_used', 0) or (event.get('tokens_used', 0) if isinstance(event, dict) else 0)
        if tokens_used and not prompt_tokens and not completion_tokens:
            output.print(f"  tokens_used: {tokens_used}")
    
    # Show summary with running totals
    output.print(f"\n{'='*60}")
    output.print(f"  SESSION SUMMARY")
    output.print(f"{'='*60}")
    output.print(f"  Total Events:       {len(events)}")
    output.print(f"  Prompt Tokens:      {running_prompt_tokens:,}")
    output.print(f"  Completion Tokens:  {running_completion_tokens:,}")
    output.print(f"  Total Tokens:       {running_prompt_tokens + running_completion_tokens:,}")
    output.print(f"  Total Cost:         ${running_cost:.6f}")
    
    # Show duplicate analysis if in full mode
    if full:
        analyzer = TraceAnalyzer(events)
        result = analyzer.analyze()
        if result.duplicates:
            output.print(f"\n  DUPLICATE CONTENT DETECTED:")
            output.print(f"    Duplicates Found: {result.duplicate_count}")
            output.print(f"    Wasted Tokens:    {result.total_wasted_tokens:,}")
            for dup in result.duplicates[:3]:
                output.print(f"    - Hash {dup.content_hash[:12]}... ({dup.duplicate_count}x, ~{dup.wasted_tokens:,} wasted)")
        else:
            output.print(f"\n  CONTEXT EFFICIENCY: No duplicates detected ✓")
    
    output.print(f"{'='*60}\n")


@app.command("show")
def replay_show(
    session_id: str = typer.Argument(
        ...,
        help="Session ID or path to trace file",
    ),
    event_num: int = typer.Option(
        None,
        "--event",
        "-e",
        help="Show specific event number (1-based)",
    ),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        "-a",
        help="Filter by agent name",
    ),
    event_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by event type",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
):
    """Show trace events without interactive mode."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.replay import ContextTraceReader
    except ImportError:
        output.print_error("Replay module not available")
        raise typer.Exit(1)
    
    reader = ContextTraceReader(session_id)
    
    if not reader.exists:
        output.print_error(f"Trace not found: {session_id}")
        raise typer.Exit(1)
    
    # Get events with filters
    if event_num is not None:
        events = [reader[event_num - 1]] if 0 < event_num <= len(reader) else []
    elif agent:
        events = reader.get_by_agent(agent)
    elif event_type:
        events = reader.get_by_type(event_type)
    else:
        events = reader.get_all()
    
    if json_output or output.is_json_mode:
        output.print_json({
            "session_id": session_id,
            "total_events": len(reader),
            "filtered_events": len(events),
            "events": [e.to_dict() if hasattr(e, 'to_dict') else e for e in events],
        })
        return
    
    if not events:
        output.print_info("No events match the filter criteria.")
        return
    
    output.print(f"Session: {session_id}")
    output.print(f"Showing {len(events)} of {len(reader)} events\n")
    
    for i, event in enumerate(events):
        # Get event details
        if hasattr(event, 'event_type'):
            et = event.event_type
            if hasattr(et, 'value'):
                et = et.value
        else:
            et = event.get('event_type', 'unknown')
        
        agent_name = getattr(event, 'agent_name', None) or (event.get('agent_name') if isinstance(event, dict) else None)
        seq = getattr(event, 'sequence_num', i) or (event.get('sequence_num', i) if isinstance(event, dict) else i)
        
        line = f"[{seq + 1}] {et.upper()}"
        if agent_name:
            line += f" ({agent_name})"
        
        output.print(line)


@app.command("delete")
def replay_delete(
    session_id: str = typer.Argument(
        ...,
        help="Session ID to delete",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
):
    """Delete a context trace."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.replay import ContextTraceReader
    except ImportError:
        output.print_error("Replay module not available")
        raise typer.Exit(1)
    
    reader = ContextTraceReader(session_id)
    
    if not reader.exists:
        output.print_error(f"Trace not found: {session_id}")
        raise typer.Exit(1)
    
    if not force:
        confirm = typer.confirm(f"Delete trace '{session_id}' ({len(reader)} events)?")
        if not confirm:
            output.print("Cancelled.")
            raise typer.Exit(0)
    
    try:
        reader.path.unlink()
        output.print_success(f"Deleted trace: {session_id}")
    except Exception as e:
        output.print_error(f"Failed to delete: {e}")
        raise typer.Exit(1)


@app.command("flow")
def replay_flow(
    session_id: str = typer.Argument(
        ...,
        help="Session ID or path to trace file",
    ),
    format: str = typer.Option(
        "ascii",
        "--format",
        "-f",
        help="Output format: ascii, json",
    ),
):
    """Visualize agent flow from a context trace."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.replay import ContextTraceReader
    except ImportError:
        output.print_error("Replay module not available")
        raise typer.Exit(1)
    
    reader = ContextTraceReader(session_id)
    
    if not reader.exists:
        output.print_error(f"Trace not found: {session_id}")
        raise typer.Exit(1)
    
    events = reader.get_all()
    if not events:
        output.print_error(f"No events in trace: {session_id}")
        raise typer.Exit(1)
    
    # Build flow structure from events
    flow_data = _build_flow_from_events(events)
    
    if format == "json":
        output.print_json(flow_data)
        return
    
    # ASCII visualization
    _print_ascii_flow(output, flow_data, session_id)


def _build_flow_from_events(events) -> dict:
    """Build flow structure from context events."""
    agents = {}
    handoffs = []
    
    for event in events:
        event_type = event.event_type
        if hasattr(event_type, 'value'):
            event_type = event_type.value
        
        agent_name = event.agent_name
        
        if event_type == "agent_start" and agent_name:
            if agent_name not in agents:
                agents[agent_name] = {
                    "name": agent_name,
                    "start_time": event.timestamp,
                    "end_time": None,
                    "messages": 0,
                    "tool_calls": [],
                    "llm_calls": 0,
                }
        
        elif event_type == "agent_end" and agent_name:
            if agent_name in agents:
                agents[agent_name]["end_time"] = event.timestamp
        
        elif event_type == "agent_handoff":
            handoffs.append({
                "from": event.data.get("from_agent"),
                "to": event.data.get("to_agent"),
                "reason": event.data.get("reason"),
                "timestamp": event.timestamp,
            })
        
        elif event_type == "message_added" and agent_name:
            if agent_name in agents:
                agents[agent_name]["messages"] += 1
        
        elif event_type == "tool_call_start" and agent_name:
            tool_name = event.data.get("tool_name", "unknown")
            if agent_name in agents:
                agents[agent_name]["tool_calls"].append(tool_name)
        
        elif event_type == "llm_request" and agent_name:
            if agent_name in agents:
                agents[agent_name]["llm_calls"] += 1
    
    # Determine agent order based on start times
    agent_order = sorted(
        agents.keys(),
        key=lambda a: agents[a].get("start_time", 0) or 0
    )
    
    return {
        "session_id": events[0].session_id if events else "",
        "agents": agents,
        "agent_order": agent_order,
        "handoffs": handoffs,
        "total_events": len(events),
    }


def _print_ascii_flow(output, flow_data: dict, session_id: str):
    """Print ASCII flow visualization."""
    agents = flow_data["agents"]
    agent_order = flow_data["agent_order"]
    handoffs = flow_data["handoffs"]
    
    output.print(f"\n{'='*60}")
    output.print(f"  AGENT FLOW: {session_id}")
    output.print(f"{'='*60}\n")
    
    if not agent_order:
        output.print("  No agents found in trace.")
        return
    
    # Print agent boxes with connections
    for i, agent_name in enumerate(agent_order):
        agent = agents[agent_name]
        
        # Agent box
        box_width = 40
        output.print(f"  ┌{'─' * box_width}┐")
        output.print(f"  │ {'Agent: ' + agent_name:<{box_width-2}} │")
        output.print(f"  │{' ' * box_width}│")
        output.print(f"  │   Messages: {agent['messages']:<{box_width-15}} │")
        output.print(f"  │   LLM Calls: {agent['llm_calls']:<{box_width-16}} │")
        
        if agent['tool_calls']:
            tools_str = ", ".join(agent['tool_calls'][:3])
            if len(agent['tool_calls']) > 3:
                tools_str += f" (+{len(agent['tool_calls'])-3} more)"
            output.print(f"  │   Tools: {tools_str:<{box_width-13}} │")
        
        output.print(f"  └{'─' * box_width}┘")
        
        # Connection to next agent
        if i < len(agent_order) - 1:
            next_agent = agent_order[i + 1]
            
            # Find handoff reason
            handoff_reason = None
            for h in handoffs:
                if h["from"] == agent_name and h["to"] == next_agent:
                    handoff_reason = h.get("reason")
                    break
            
            output.print("          │")
            output.print("          ▼")
            if handoff_reason:
                reason_short = handoff_reason[:35] + "..." if len(handoff_reason) > 35 else handoff_reason
                output.print(f"    [{reason_short}]")
            output.print("")
    
    # Summary
    output.print("\n" + "─"*60)
    output.print("  Summary:")
    output.print(f"    Agents: {len(agent_order)}")
    output.print(f"    Handoffs: {len(handoffs)}")
    output.print(f"    Total Events: {flow_data['total_events']}")
    output.print("─"*60 + "\n")


@app.command("dashboard")
def replay_dashboard(
    session_id: Optional[str] = typer.Argument(
        None,
        help="Session ID (optional, shows all recent if not specified)",
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        "-n",
        help="Number of recent sessions to analyze",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
):
    """Show context analytics dashboard with usage patterns.
    
    Displays:
    - Token usage by agent (bar chart)
    - Cost breakdown by tool
    - Duplicate content patterns
    - Optimization recommendations
    """
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.replay import list_traces, ContextTraceReader
        from praisonai.replay.analyzer import TraceAnalyzer
    except ImportError:
        output.print_error("Replay module not available")
        raise typer.Exit(1)
    
    # Get traces to analyze
    if session_id:
        traces_to_analyze = [session_id]
    else:
        traces = list_traces(limit=limit)
        if not traces:
            output.print_info("No traces found. Run agents with trace=True to create traces.")
            return
        traces_to_analyze = [t.session_id for t in traces]
    
    # Aggregate stats across sessions
    all_stats = []
    total_tokens = 0
    total_cost = 0.0
    total_duplicates = 0
    total_wasted = 0
    agent_tokens = {}
    tool_costs = {}
    
    for sid in traces_to_analyze:
        reader = ContextTraceReader(sid)
        if not reader.exists:
            continue
        
        events = reader.get_all()
        if not events:
            continue
        
        analyzer = TraceAnalyzer(events)
        result = analyzer.analyze()
        all_stats.append(result)
        
        # Aggregate using correct attribute paths
        total_tokens += result.token_stats.total_tokens
        total_cost += result.cost_stats.total_cost
        total_duplicates += result.duplicate_count
        total_wasted += result.total_wasted_tokens
        
        # By agent - tokens is a dict with {prompt, completion, total}
        for agent, tokens in result.token_stats.by_agent.items():
            agent_total = tokens.get("total", 0) if isinstance(tokens, dict) else tokens
            agent_tokens[agent] = agent_tokens.get(agent, 0) + agent_total
        
        # By tool - cost is a dict with {count, cost}
        for tool, cost_info in result.cost_stats.by_tool.items():
            tool_cost = cost_info.get("cost", 0.0) if isinstance(cost_info, dict) else cost_info
            tool_costs[tool] = tool_costs.get(tool, 0.0) + tool_cost
    
    if json_output:
        output.print_json({
            "sessions_analyzed": len(all_stats),
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "total_duplicates": total_duplicates,
            "total_wasted_tokens": total_wasted,
            "tokens_by_agent": agent_tokens,
            "cost_by_tool": tool_costs,
        })
        return
    
    # Display dashboard
    output.print("\n" + "="*70)
    output.print("  CONTEXT ANALYTICS DASHBOARD")
    output.print("="*70)
    output.print(f"\n  Sessions Analyzed: {len(all_stats)}")
    output.print(f"  Total Tokens:      {total_tokens:,}")
    output.print(f"  Total Cost:        ${total_cost:.4f}")
    
    # Token usage by agent (bar chart)
    if agent_tokens:
        output.print("\n  TOKEN USAGE BY AGENT:")
        output.print("  " + "-"*50)
        max_tokens = max(agent_tokens.values()) if agent_tokens else 1
        for agent, tokens in sorted(agent_tokens.items(), key=lambda x: -x[1]):
            bar_len = int((tokens / max_tokens) * 30)
            bar = "█" * bar_len
            pct = (tokens / total_tokens * 100) if total_tokens > 0 else 0
            output.print(f"    {agent[:20]:<20} {bar:<30} {tokens:>10,} ({pct:.1f}%)")
    
    # Cost by tool
    if tool_costs:
        output.print("\n  COST BY TOOL:")
        output.print("  " + "-"*50)
        for tool, cost in sorted(tool_costs.items(), key=lambda x: -x[1]):
            output.print(f"    {tool:<25} ${cost:.4f}")
    
    # Context efficiency
    output.print("\n  CONTEXT EFFICIENCY:")
    output.print("  " + "-"*50)
    if total_duplicates > 0:
        waste_pct = (total_wasted / total_tokens * 100) if total_tokens > 0 else 0
        output.print(f"    ⚠️  Duplicates Found:  {total_duplicates}")
        output.print(f"    ⚠️  Wasted Tokens:     {total_wasted:,} ({waste_pct:.1f}%)")
        output.print("\n  RECOMMENDATIONS:")
        output.print("    • Enable session-level deduplication in workflow")
        output.print("    • Consider using context: {strategy: smart} in YAML")
        output.print("    • Review tool outputs for redundant content")
    else:
        output.print("    ✅ Context is optimized! No duplicates detected.")
    
    output.print("\n" + "="*70 + "\n")


@app.command("cleanup")
def replay_cleanup(
    max_age_days: int = typer.Option(
        7,
        "--max-age",
        help="Delete traces older than N days",
    ),
    max_size_mb: int = typer.Option(
        100,
        "--max-size",
        help="Delete oldest traces if total size exceeds N MB",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be deleted without deleting",
    ),
):
    """Clean up old context traces."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.replay.storage import cleanup_old_traces, list_traces
    except ImportError:
        output.print_error("Replay module not available")
        raise typer.Exit(1)
    
    if dry_run:
        from datetime import datetime
        traces = list_traces(limit=10000)
        now = datetime.now()
        
        to_delete = []
        for trace in traces:
            age_days = (now - trace.modified_at).days
            if age_days > max_age_days:
                to_delete.append(trace)
        
        if to_delete:
            output.print(f"Would delete {len(to_delete)} traces older than {max_age_days} days:")
            for t in to_delete[:10]:
                output.print(f"  - {t.session_id}")
            if len(to_delete) > 10:
                output.print(f"  ... and {len(to_delete) - 10} more")
        else:
            output.print("No traces would be deleted.")
        return
    
    deleted = cleanup_old_traces(max_age_days=max_age_days, max_size_mb=max_size_mb)
    
    if deleted > 0:
        output.print_success(f"Deleted {deleted} old traces.")
    else:
        output.print_info("No traces needed cleanup.")
