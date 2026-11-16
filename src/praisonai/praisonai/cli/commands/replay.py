"""
Replay command group for PraisonAI CLI.

Provides context replay functionality:
- replay list: List available traces
- replay context <session_id>: Interactive replay of a trace
- replay flow <run|yaml> --format ascii|json|mermaid: Agent flow / static graph
- replay view [run|yaml] [--live]: Open PraisonAI Replay (aiui) on a run
- replay watch [yaml]: A page with a Run button that draws each run live
- replay export <run> --format html|json|mermaid|otel: Export a run
- replay rerun <run> --from NODE: Re-run from a node, reusing earlier outputs
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
        help="Session ID, path to trace file, or a YAML definition (static graph)",
    ),
    format: str = typer.Option(
        "ascii",
        "--format",
        "-f",
        help="Output format: ascii, json, mermaid",
    ),
):
    """Visualize agent flow from a context trace, or a YAML definition before it runs."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()

    if format not in ("ascii", "json", "mermaid"):
        output.print_error(f"Unknown format: {format} (use ascii, json or mermaid)")
        raise typer.Exit(2)

    from praisonai.replay.yaml_run import is_yaml_path

    if is_yaml_path(session_id):
        _print_static_flow(output, session_id, format)
        return

    if format == "mermaid":
        from praisonai.replay.events import load_events
        from praisonai.replay.export import to_mermaid

        try:
            raw_events = load_events(session_id)
        except FileNotFoundError:
            output.print_error(f"Trace not found: {session_id}")
            raise typer.Exit(1)
        # Plain echo: Rich would treat mermaid's [brackets] as markup.
        typer.echo(to_mermaid(raw_events), nl=False)
        return
    
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


def _print_static_flow(output, yaml_file: str, format: str) -> None:
    """Static graph of a YAML definition (nothing is executed)."""
    from praisonai.replay.yaml_run import static_graph, static_mermaid

    try:
        if format == "mermaid":
            typer.echo(static_mermaid(yaml_file), nl=False)
            return
        graph, _flow = static_graph(yaml_file)
    except Exception as e:
        output.print_error(f"Could not read {yaml_file}: {e}")
        raise typer.Exit(1)

    if format == "json":
        output.print_json(graph)
        return

    typer.echo(f"\n  STATIC GRAPH: {yaml_file}  ({graph.get('kind')}, {graph.get('process')})\n")
    for node in graph.get("nodes", []):
        typer.echo(f"  [{node.get('kind')}] {node.get('label')}  ({node.get('id')})")
    typer.echo("")
    for edge in graph.get("edges", []):
        label = f" [{edge['label']}]" if edge.get("label") else ""
        typer.echo(f"  {edge.get('source')} --{edge.get('kind')}--> {edge.get('target')}{label}")
    typer.echo("")


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


# ---------------------------------------------------------------------------
# PraisonAI Replay: view / export / rerun
# ---------------------------------------------------------------------------

_AIUI_INSTALL_HINT = 'pip install "praisonai[ui]"'
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_EXPORT_FORMATS = ("html", "json", "mermaid", "otel")


def _aiui_installed() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("praisonaiui") is not None
    except (ImportError, ValueError):
        return False


def _replay_app_path():
    """The bundled ``praisonai/ui_replay/default_app.py`` preset."""
    from pathlib import Path

    import praisonai

    return Path(praisonai.__file__).resolve().parent / "ui_replay" / "default_app.py"


def _spawn_aiui(app_path, host: str, port: int, env: dict):
    """Start ``aiui run`` for the replay app (falls back to ``python -m praisonaiui.cli``)."""
    import shutil
    import subprocess
    import sys

    args = ["run", str(app_path), "--port", str(port), "--host", host]
    exe = shutil.which("aiui")
    cmd = [exe, *args] if exe else [sys.executable, "-m", "praisonaiui.cli", *args]
    return subprocess.Popen(cmd, env=env)


def _open_browser(url: str, host: str, port: int, timeout: float = 20.0) -> None:
    """Open ``url`` once the server accepts connections (in a daemon thread)."""
    import socket
    import threading
    import time
    import webbrowser

    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host

    def _wait_then_open():
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((probe_host, port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        webbrowser.open(url)

    threading.Thread(target=_wait_then_open, name="replay-open-browser", daemon=True).start()


def _replay_url(host: str, port: int, run_id: Optional[str], live: bool) -> str:
    url_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    if ":" in url_host and not url_host.startswith("["):
        url_host = f"[{url_host}]"
    url = f"http://{url_host}:{port}/#/replay"
    params = []
    if run_id:
        params.append(f"run={run_id}")
    if live:
        params.append("live=1")
    return url + ("?" + "&".join(params) if params else "")


def _start_yaml_run(yaml_file: str, run_id: str):
    """Run a YAML definition recorded live in a background thread."""
    import threading

    from praisonai.replay.yaml_run import run_yaml_recorded

    def _target():
        try:
            run_yaml_recorded(yaml_file, run_id=run_id, live=True)
            typer.echo(f"Run finished: {run_id}")
        except Exception as e:  # the viewer keeps serving the partial trace
            typer.echo(f"Run failed: {e}", err=True)

    thread = threading.Thread(target=_target, name="replay-yaml-run", daemon=True)
    thread.start()
    return thread


@app.command("view")
def replay_view(
    target: Optional[str] = typer.Argument(
        None,
        help="Run id, trace .jsonl path, or a YAML file to run and watch (default: recent runs)",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="Follow the run as it is written (implied for a YAML file)",
    ),
    port: int = typer.Option(8090, "--port", "-p", help="Port for the replay UI"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
):
    """Open PraisonAI Replay (timeline + map) for a run in the browser.

    Examples:
        praisonai replay view
        praisonai replay view run-1a2b3c4d5e6f
        praisonai replay view agents.yaml        # runs it, recorded, and follows it live
    """
    import os
    from pathlib import Path

    from praisonai.replay.events import SAFE_RUN_ID, resolve_trace_path
    from praisonai.replay.recorder import new_run_id
    from praisonai.replay.storage import resolve_traces_dir
    from praisonai.replay.yaml_run import is_yaml_path

    if not _aiui_installed():
        typer.echo("ERROR: PraisonAI Replay needs PraisonAI UI (aiui), which is not installed.", err=True)
        typer.echo(f"Install with:\n  {_AIUI_INSTALL_HINT}", err=True)
        raise typer.Exit(1)

    if host not in _LOOPBACK_HOSTS:
        typer.echo(
            f"WARNING: serving replay on {host} makes your traces (prompts, outputs, tool "
            "arguments) reachable from the network. Use --host 127.0.0.1 to keep them local.",
            err=True,
        )

    traces_dir = resolve_traces_dir()
    run_id: Optional[str] = None
    yaml_file: Optional[str] = None

    if target and is_yaml_path(target):
        yaml_file = target
        run_id = new_run_id()
        live = True
    elif target:
        path = resolve_trace_path(target)
        if str(target).endswith(".jsonl") or "/" in str(target):
            traces_dir = path.parent
        run_id = path.stem
        if not SAFE_RUN_ID.match(run_id):
            typer.echo(f"ERROR: not a valid run id: {run_id}", err=True)
            raise typer.Exit(2)
        if not path.exists() and not live:
            typer.echo(f"ERROR: Trace not found: {target}", err=True)
            typer.echo("Use 'praisonai replay list' to see available traces (or --live to wait for it).", err=True)
            raise typer.Exit(1)

    app_path = _replay_app_path()
    if not app_path.exists():
        typer.echo(f"ERROR: bundled replay app missing: {app_path}", err=True)
        raise typer.Exit(1)

    env = os.environ.copy()
    env["PRAISONAI_TRACES_DIR"] = str(Path(traces_dir))
    url = _replay_url(host, port, run_id, live)

    if yaml_file:
        typer.echo(f"Running {yaml_file} as {run_id} (recording live to {Path(traces_dir) / (run_id + '.jsonl')})")
        _start_yaml_run(yaml_file, run_id)

    typer.echo(f"PraisonAI Replay: {url}")
    proc = _spawn_aiui(app_path, host, port, env)
    _open_browser(url, host, port)
    code = _wait_for_server(proc)
    if code:
        raise typer.Exit(code)


def _wait_for_server(proc) -> int:
    """Wait for the aiui server; never leave it running after this CLI exits."""
    import signal
    import threading

    previous = None
    if threading.current_thread() is threading.main_thread():
        def _on_term(signum, _frame):
            raise SystemExit(128 + signum)

        previous = signal.signal(signal.SIGTERM, _on_term)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def _load_raw_events(output, run: str):
    from praisonai.replay.events import load_events

    try:
        events = load_events(run)
    except FileNotFoundError:
        output.print_error(f"Trace not found: {run}")
        output.print_info("Use 'praisonai replay list' to see available traces.")
        raise typer.Exit(1)
    if not events:
        output.print_error(f"No events in trace: {run}")
        raise typer.Exit(1)
    return events


@app.command("watch")
def replay_watch(
    yaml_file: Optional[str] = typer.Argument(None, help="agents.yaml to run from the page (default: just view recorded runs)"),
    port: int = typer.Option(8090, "--port", "-p", help="Port for the page"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open the browser"),
):
    """Open a page with a Run button: each run is recorded and drawn live, step by step.

    Examples:
        praisonai replay watch agents.yaml
        praisonai replay watch               # recorded runs only
    """
    from praisonai.replay.live import watch
    from praisonai.replay.yaml_run import is_yaml_path

    if not _aiui_installed():
        typer.echo(f"ERROR: PraisonAI Replay needs PraisonAI UI (aiui). Install with:\n  {_AIUI_INSTALL_HINT}", err=True)
        raise typer.Exit(1)
    if yaml_file and not is_yaml_path(yaml_file):
        typer.echo(f"ERROR: not a YAML file: {yaml_file}", err=True)
        raise typer.Exit(2)
    try:
        watch(yaml_file, host=host, port=port, open_browser=not no_browser)
    except ImportError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(1)


@app.command("export")
def replay_export(
    run: str = typer.Argument(..., help="Run id or path to trace file"),
    format: str = typer.Option("html", "--format", "-f", help="html, json, mermaid or otel (OTLP-JSON)"),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Write to FILE (default: stdout; html: ./<run>.html)"
    ),
    no_redact: bool = typer.Option(
        False, "--no-redact", help="Export as recorded, without removing secrets/PII"
    ),
):
    """Export a run: a self-contained HTML replay, JSON, Mermaid or OTLP-JSON.

    Everything is redacted by default; --no-redact exports the trace as recorded.
    """
    import json
    from pathlib import Path

    from ..output.console import get_output_controller
    from praisonai.replay import export as exporter
    from praisonai.replay.events import SAFE_RUN_ID, run_id_of

    output = get_output_controller()
    if format not in _EXPORT_FORMATS:
        output.print_error(f"Unknown format: {format} (use {', '.join(_EXPORT_FORMATS)})")
        raise typer.Exit(2)

    events = _load_raw_events(output, run)
    redact = not no_redact
    if format == "html":
        text = exporter.to_html(events, redact=redact)
        if not output_file:
            # The run id comes from the trace: never let it pick a path outside ./
            name = run_id_of(events, Path(run).stem)
            if not SAFE_RUN_ID.match(name):
                name = Path(run).stem if SAFE_RUN_ID.match(Path(run).stem) else "replay"
            output_file = f"{name}.html"
    elif format == "json":
        text = exporter.to_json(events, redact=redact)
    elif format == "mermaid":
        text = exporter.to_mermaid(events, redact=redact)
    else:
        text = json.dumps(exporter.to_otlp_json(events, redact=redact), indent=2)

    if output_file:
        Path(output_file).write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {format} export to {output_file}")
    else:
        typer.echo(text, nl=not text.endswith("\n"))


@app.command("rerun")
def replay_rerun(
    run: str = typer.Argument(..., help="Run id or path to the recorded trace"),
    from_node: str = typer.Option(..., "--from", help="Node id to re-run from (e.g. task:write, step:draft)"),
    file: Optional[str] = typer.Option(
        None, "--file", help="YAML definition (default: the one recorded with the run)"
    ),
):
    """Re-run a recorded run from NODE: earlier nodes reuse their recorded output.

    The new run is recorded with workflow_start.data.forked_from = {run_id, node_id}.
    """
    from pathlib import Path

    from ..output.console import get_output_controller
    from praisonai.replay.events import session_meta
    from praisonai.replay.recorder import new_run_id
    from praisonai.replay.rerun import RerunError, plan_rerun
    from praisonai.replay.yaml_run import run_yaml_recorded, yaml_kind

    output = get_output_controller()
    events = _load_raw_events(output, run)
    try:
        plan = plan_rerun(events, from_node)
    except RerunError as e:
        output.print_error(str(e))
        raise typer.Exit(1)

    meta = session_meta(events)
    definition = file or meta.get("yaml_path") or meta.get("agents_file") or meta.get("workflow")
    if not definition:
        output.print_error("This run did not record its definition; pass it with --file agents.yaml")
        raise typer.Exit(1)
    if not Path(definition).expanduser().is_file():
        output.print_error(f"Definition not found: {definition} (pass --file)")
        raise typer.Exit(1)
    if yaml_kind(definition) != plan.kind:
        output.print_error(
            f"{definition} defines a {yaml_kind(definition)} but {from_node} is a {plan.kind} node; "
            "pass the definition that recorded this run with --file."
        )
        raise typer.Exit(1)

    seeded = []
    new_id = new_run_id()
    reused = ", ".join(plan.outputs) or "nothing"
    typer.echo(f"Re-running {plan.source_run_id} from {from_node} as {new_id} (reusing: {reused})")
    try:
        rec, result = run_yaml_recorded(definition, run_id=new_id, plan=plan, on_seeded=seeded.append)
    except Exception as e:
        output.print_error(f"Re-run failed: {e}")
        raise typer.Exit(1)
    if not seeded:
        output.print_warning("The definition was run, but the recorded outputs could not be applied to it.")
    typer.echo(str(result) if result is not None else "")
    typer.echo(f"Recorded: {rec.run_id} ({rec.path})")
