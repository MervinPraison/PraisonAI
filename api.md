# PraisonAI API Reference

This file is auto-generated. Do not edit manually.
Regenerate with: `praisonai docs api-md --write`

# Agents

Types:
```python
from praisonaiagents import Agent, Agents
```

Methods:

* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">achat</a>(prompt: str, temperature = 1.0, tools = None, output_json = None, output_pydantic = None, reasoning_steps = False, task_name = None, task_description = None, task_id = None, attachments = None)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">aexecute</a>(task, context = None)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">agent_id</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">analyze_prompt</a>(prompt: str) -> set</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">arun</a>(prompt: str, **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">astart</a>(prompt: str, **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">auto_memory</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">auto_memory</a>(value)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">background</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">background</a>(value)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">chat</a>(prompt, temperature = 1.0, tools = None, output_json = None, output_pydantic = None, reasoning_steps = False, stream = None, task_name = None, task_description = None, task_id = None, config = None, force_retrieval = False, skip_retrieval = False, attachments = None)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">chat_with_context</a>(message: str, context: 'ContextPack', **kwargs) -> str</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">checkpoints</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">checkpoints</a>(value)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">clean_json_output</a>(output: str) -> str</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">clear_history</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">console</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">context_manager</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">context_manager</a>(value)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">delete_history</a>(index: int) -> bool</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">delete_history_matching</a>(pattern: str) -> int</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">display_name</a>() -> str</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">ephemeral</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">execute</a>(task, context = None)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">execute_tool</a>(function_name, arguments)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">execute_tool_async</a>(function_name: str, arguments: Dict[str, Any]) -> Any</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">from_template</a>(uri: str, config: Optional[Dict[str, Any]] = None, offline: bool = False, **kwargs) -> 'Agent'</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">generate_task</a>() -> 'Task'</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">get_available_tools</a>() -> List[Any]</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">get_history_size</a>() -> int</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">get_memory_context</a>(query: Optional[str] = None) -> str</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">get_recommended_stage</a>(prompt: str) -> str</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">get_rules_context</a>(file_path: Optional[str] = None, include_manual: Optional[List[str]] = None) -> str</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">get_skills_prompt</a>() -> str</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">handoff_to</a>(target_agent: 'Agent', prompt: str, context: Optional[Dict[str, Any]] = None, config: Optional['HandoffConfig'] = None) -> 'HandoffResult'</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">handoff_to_async</a>(target_agent: 'Agent', prompt: str, context: Optional[Dict[str, Any]] = None, config: Optional['HandoffConfig'] = None) -> 'HandoffResult'</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">iter_stream</a>(prompt: str, **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">launch</a>(path: str = '/', port: int = 8000, host: str = '0.0.0.0', debug: bool = False, protocol: str = 'http')</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">llm_model</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">output_style</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">output_style</a>(value)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">policy</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">policy</a>(value)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">prune_history</a>(keep_last: int = 5) -> int</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">query</a>(question: str, **kwargs) -> 'RAGResult'</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">rag</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">rag_query</a>(question: str, **kwargs) -> 'RAGResult'</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">retrieval_config</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">retrieve</a>(query: str, **kwargs) -> 'ContextPack'</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">rules_manager</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">run</a>(prompt: str, **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">run_autonomous</a>(prompt: str, max_iterations: Optional[int] = None, timeout_seconds: Optional[float] = None)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">session_id</a>() -> Optional[str]</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">skill_manager</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">start</a>(prompt: str = None, **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">store_memory</a>(content: str, memory_type: str = 'short_term', **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">switch_model</a>(new_model: str) -> None</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">thinking_budget</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">thinking_budget</a>(value)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">add_task</a>(task)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">aexecute_task</a>(task_id)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">append_to_state</a>(key: str, value: Any, max_length: Optional[int] = None) -> List[Any]</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">arun_all_tasks</a>()</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">arun_task</a>(task_id)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">astart</a>(content = None, return_dict = False, **kwargs)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">clean_json_output</a>(output: str) -> str</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">clear_state</a>() -> None</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">context_manager</a>()</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">current_plan</a>()</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">default_completion_checker</a>(task, agent_output)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">delete_state</a>(key: str) -> bool</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">display_token_usage</a>()</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">execute_task</a>(task_id)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_agent_details</a>(agent_name)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_all_state</a>() -> Dict[str, Any]</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_all_tasks_status</a>()</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_detailed_token_report</a>() -> Dict[str, Any]</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_plan_markdown</a>() -> str</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_state</a>(key: str, default: Any = None) -> Any</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_task_details</a>(task_id)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_task_result</a>(task_id)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_task_status</a>(task_id)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_todo_markdown</a>() -> str</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_token_usage_summary</a>() -> Dict[str, Any]</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">has_state</a>(key: str) -> bool</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">increment_state</a>(key: str, amount: float = 1, default: float = 0) -> float</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">launch</a>(path: str = '/agents', port: int = 8000, host: str = '0.0.0.0', debug: bool = False, protocol: str = 'http')</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">restore_session_state</a>(session_id: str) -> bool</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">run</a>(content = None, return_dict = False, **kwargs)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">run_all_tasks</a>()</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">run_task</a>(task_id)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">save_output_to_file</a>(task, task_output)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">save_session_state</a>(session_id: str, include_memory: bool = True) -> None</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">set_state</a>(key: str, value: Any) -> None</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">start</a>(content = None, return_dict = False, output = None, **kwargs)</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">todo_list</a>()</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">update_plan_step_status</a>(step_id: str, status: str) -> bool</code>
* <code title="class Agents">Agents.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">update_state</a>(updates: Dict) -> None</code>

# Tools

Types:
```python
from praisonaiagents import Tools, tool
```

Methods:

* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/tools/decorator.py">tool</a>(func: Optional[Callable] = None) -> Union[FunctionTool, Callable[[Callable], FunctionTool]]</code>

# Other

Types:
```python
from praisonaiagents import EmbeddingResult, Task, aembedding, aembeddings, embedding, embeddings, get_dimensions
```

Methods:

* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">execute_callback</a>(task_output: TaskOutput) -> None</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">execute_callback_sync</a>(task_output: TaskOutput) -> None</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">initialize_memory</a>()</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">store_in_memory</a>(content: str, agent_name: str = None, task_id: str = None)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/embed.py">aembedding</a>(input: Union[str, List[str]], model: str = 'text-embedding-3-small', dimensions: Optional[int] = None, encoding_format: str = 'float', timeout: float = 600.0, api_key: Optional[str] = None, api_base: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> EmbeddingResult</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/embed.py">embedding</a>(input: Union[str, List[str]], model: str = 'text-embedding-3-small', dimensions: Optional[int] = None, encoding_format: str = 'float', timeout: float = 600.0, api_key: Optional[str] = None, api_base: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> EmbeddingResult</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/dimensions.py">get_dimensions</a>(model_name: str) -> int</code>

# Wrapper (praisonai)

Types:
```python
from praisonai import CloudProvider, Deploy, DeployConfig, DeployType, PraisonAI, __version__
```

# CLI

Methods:

* <code title="cli">praisonai <a href="./src/praisonai/praisonai/cli/main.py">--help</a></code>
* <code title="cli">praisonai acp acp-main <a href="./src/praisonai/praisonai/cli/commands/acp.py">--help</a></code>
* <code title="cli">praisonai agents create <a href="./src/praisonai/praisonai/cli/commands/agents.py">--help</a></code>
* <code title="cli">praisonai agents info <a href="./src/praisonai/praisonai/cli/commands/agents.py">--help</a></code>
* <code title="cli">praisonai agents list <a href="./src/praisonai/praisonai/cli/commands/agents.py">--help</a></code>
* <code title="cli">praisonai audit agent-centric <a href="./src/praisonai/praisonai/cli/commands/audit.py">--help</a></code>
* <code title="cli">praisonai batch batch-run <a href="./src/praisonai/praisonai/cli/commands/batch.py">--help</a></code>
* <code title="cli">praisonai batch list <a href="./src/praisonai/praisonai/cli/commands/batch.py">--help</a></code>
* <code title="cli">praisonai batch report <a href="./src/praisonai/praisonai/cli/commands/batch.py">--help</a></code>
* <code title="cli">praisonai batch stats <a href="./src/praisonai/praisonai/cli/commands/batch.py">--help</a></code>
* <code title="cli">praisonai benchmark agent <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai benchmark benchmark-callback <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai benchmark cli <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai benchmark compare <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai benchmark litellm <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai benchmark profile <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai benchmark sdk <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai benchmark workflow <a href="./src/praisonai/praisonai/cli/commands/benchmark.py">--help</a></code>
* <code title="cli">praisonai call call-main <a href="./src/praisonai/praisonai/cli/commands/call.py">--help</a></code>
* <code title="cli">praisonai chat <a href="./src/praisonai/praisonai/cli/main.py">--help</a></code>
* <code title="cli">praisonai chat chat-main <a href="./src/praisonai/praisonai/cli/commands/chat.py">--help</a></code>
* <code title="cli">praisonai code <a href="./src/praisonai/praisonai/cli/main.py">--help</a></code>
* <code title="cli">praisonai code code-main <a href="./src/praisonai/praisonai/cli/commands/code.py">--help</a></code>
* <code title="cli">praisonai commit commit-main <a href="./src/praisonai/praisonai/cli/commands/commit.py">--help</a></code>
* <code title="cli">praisonai completion bash <a href="./src/praisonai/praisonai/cli/commands/completion.py">--help</a></code>
* <code title="cli">praisonai completion completion-callback <a href="./src/praisonai/praisonai/cli/commands/completion.py">--help</a></code>
* <code title="cli">praisonai completion fish <a href="./src/praisonai/praisonai/cli/commands/completion.py">--help</a></code>
* <code title="cli">praisonai completion zsh <a href="./src/praisonai/praisonai/cli/commands/completion.py">--help</a></code>
* <code title="cli">praisonai config get <a href="./src/praisonai/praisonai/cli/commands/config.py">--help</a></code>
* <code title="cli">praisonai config list <a href="./src/praisonai/praisonai/cli/commands/config.py">--help</a></code>
* <code title="cli">praisonai config path <a href="./src/praisonai/praisonai/cli/commands/config.py">--help</a></code>
* <code title="cli">praisonai config reset <a href="./src/praisonai/praisonai/cli/commands/config.py">--help</a></code>
* <code title="cli">praisonai config set <a href="./src/praisonai/praisonai/cli/commands/config.py">--help</a></code>
* <code title="cli">praisonai context add <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context clear <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context compact <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context export <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context grep <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context list <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context show <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context stats <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai context tail <a href="./src/praisonai/praisonai/cli/commands/context.py">--help</a></code>
* <code title="cli">praisonai debug acp <a href="./src/praisonai/praisonai/cli/commands/debug.py">--help</a></code>
* <code title="cli">praisonai debug debug-callback <a href="./src/praisonai/praisonai/cli/commands/debug.py">--help</a></code>
* <code title="cli">praisonai debug interactive <a href="./src/praisonai/praisonai/cli/commands/debug.py">--help</a></code>
* <code title="cli">praisonai debug lsp <a href="./src/praisonai/praisonai/cli/commands/debug.py">--help</a></code>
* <code title="cli">praisonai debug trace <a href="./src/praisonai/praisonai/cli/commands/debug.py">--help</a></code>
* <code title="cli">praisonai deploy aws <a href="./src/praisonai/praisonai/cli/commands/deploy.py">--help</a></code>
* <code title="cli">praisonai deploy azure <a href="./src/praisonai/praisonai/cli/commands/deploy.py">--help</a></code>
* <code title="cli">praisonai deploy docker <a href="./src/praisonai/praisonai/cli/commands/deploy.py">--help</a></code>
* <code title="cli">praisonai deploy gcp <a href="./src/praisonai/praisonai/cli/commands/deploy.py">--help</a></code>
* <code title="cli">praisonai diag diag-callback <a href="./src/praisonai/praisonai/cli/commands/diag.py">--help</a></code>
* <code title="cli">praisonai diag export <a href="./src/praisonai/praisonai/cli/commands/diag.py">--help</a></code>
* <code title="cli">praisonai docs api-md <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai docs generate <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai docs list <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai docs report <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai docs run <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai docs run-all <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai docs serve <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai docs stats <a href="./src/praisonai/praisonai/cli/commands/docs.py">--help</a></code>
* <code title="cli">praisonai doctor cleanup <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor config <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor db <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor doctor-callback <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor env <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor mcp <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor network <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor performance <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor selftest <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor tools <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai doctor troubleshoot <a href="./src/praisonai/praisonai/cli/commands/doctor.py">--help</a></code>
* <code title="cli">praisonai endpoints list <a href="./src/praisonai/praisonai/cli/commands/endpoints.py">--help</a></code>
* <code title="cli">praisonai endpoints test <a href="./src/praisonai/praisonai/cli/commands/endpoints.py">--help</a></code>
* <code title="cli">praisonai environment check <a href="./src/praisonai/praisonai/cli/commands/environment.py">--help</a></code>
* <code title="cli">praisonai environment doctor <a href="./src/praisonai/praisonai/cli/commands/environment.py">--help</a></code>
* <code title="cli">praisonai environment view <a href="./src/praisonai/praisonai/cli/commands/environment.py">--help</a></code>
* <code title="cli">praisonai eval accuracy <a href="./src/praisonai/praisonai/cli/commands/eval.py">--help</a></code>
* <code title="cli">praisonai eval performance <a href="./src/praisonai/praisonai/cli/commands/eval.py">--help</a></code>
* <code title="cli">praisonai examples info <a href="./src/praisonai/praisonai/cli/commands/examples.py">--help</a></code>
* <code title="cli">praisonai examples list <a href="./src/praisonai/praisonai/cli/commands/examples.py">--help</a></code>
* <code title="cli">praisonai examples report <a href="./src/praisonai/praisonai/cli/commands/examples.py">--help</a></code>
* <code title="cli">praisonai examples run <a href="./src/praisonai/praisonai/cli/commands/examples.py">--help</a></code>
* <code title="cli">praisonai examples run-all <a href="./src/praisonai/praisonai/cli/commands/examples.py">--help</a></code>
* <code title="cli">praisonai examples stats <a href="./src/praisonai/praisonai/cli/commands/examples.py">--help</a></code>
* <code title="cli">praisonai hooks add <a href="./src/praisonai/praisonai/cli/commands/hooks.py">--help</a></code>
* <code title="cli">praisonai hooks list <a href="./src/praisonai/praisonai/cli/commands/hooks.py">--help</a></code>
* <code title="cli">praisonai hooks remove <a href="./src/praisonai/praisonai/cli/commands/hooks.py">--help</a></code>
* <code title="cli">praisonai knowledge add <a href="./src/praisonai/praisonai/cli/commands/knowledge.py">--help</a></code>
* <code title="cli">praisonai knowledge index <a href="./src/praisonai/praisonai/cli/commands/knowledge.py">--help</a></code>
* <code title="cli">praisonai knowledge list <a href="./src/praisonai/praisonai/cli/commands/knowledge.py">--help</a></code>
* <code title="cli">praisonai knowledge search <a href="./src/praisonai/praisonai/cli/commands/knowledge.py">--help</a></code>
* <code title="cli">praisonai lsp logs <a href="./src/praisonai/praisonai/cli/commands/lsp.py">--help</a></code>
* <code title="cli">praisonai lsp lsp-callback <a href="./src/praisonai/praisonai/cli/commands/lsp.py">--help</a></code>
* <code title="cli">praisonai lsp start <a href="./src/praisonai/praisonai/cli/commands/lsp.py">--help</a></code>
* <code title="cli">praisonai lsp status <a href="./src/praisonai/praisonai/cli/commands/lsp.py">--help</a></code>
* <code title="cli">praisonai lsp stop <a href="./src/praisonai/praisonai/cli/commands/lsp.py">--help</a></code>
* <code title="cli">praisonai mcp add <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp auth <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp describe <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp list <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp logout <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp mcp-callback <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp remove <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp run <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp status <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp sync <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp test <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai mcp tools <a href="./src/praisonai/praisonai/cli/commands/mcp.py">--help</a></code>
* <code title="cli">praisonai memory add <a href="./src/praisonai/praisonai/cli/commands/memory.py">--help</a></code>
* <code title="cli">praisonai memory clear <a href="./src/praisonai/praisonai/cli/commands/memory.py">--help</a></code>
* <code title="cli">praisonai memory search <a href="./src/praisonai/praisonai/cli/commands/memory.py">--help</a></code>
* <code title="cli">praisonai memory show <a href="./src/praisonai/praisonai/cli/commands/memory.py">--help</a></code>
* <code title="cli">praisonai memory status <a href="./src/praisonai/praisonai/cli/commands/memory.py">--help</a></code>
* <code title="cli">praisonai package install <a href="./src/praisonai/praisonai/cli/commands/package.py">--help</a></code>
* <code title="cli">praisonai package list <a href="./src/praisonai/praisonai/cli/commands/package.py">--help</a></code>
* <code title="cli">praisonai package uninstall <a href="./src/praisonai/praisonai/cli/commands/package.py">--help</a></code>
* <code title="cli">praisonai profile imports <a href="./src/praisonai/praisonai/cli/commands/profile.py">--help</a></code>
* <code title="cli">praisonai profile optimize <a href="./src/praisonai/praisonai/cli/commands/profile.py">--help</a></code>
* <code title="cli">praisonai profile profile-callback <a href="./src/praisonai/praisonai/cli/commands/profile.py">--help</a></code>
* <code title="cli">praisonai profile query <a href="./src/praisonai/praisonai/cli/commands/profile.py">--help</a></code>
* <code title="cli">praisonai profile snapshot <a href="./src/praisonai/praisonai/cli/commands/profile.py">--help</a></code>
* <code title="cli">praisonai profile startup <a href="./src/praisonai/praisonai/cli/commands/profile.py">--help</a></code>
* <code title="cli">praisonai profile suite <a href="./src/praisonai/praisonai/cli/commands/profile.py">--help</a></code>
* <code title="cli">praisonai rag chat <a href="./src/praisonai/praisonai/cli/commands/rag.py">--help</a></code>
* <code title="cli">praisonai rag eval <a href="./src/praisonai/praisonai/cli/commands/rag.py">--help</a></code>
* <code title="cli">praisonai rag index <a href="./src/praisonai/praisonai/cli/commands/rag.py">--help</a></code>
* <code title="cli">praisonai rag query <a href="./src/praisonai/praisonai/cli/commands/rag.py">--help</a></code>
* <code title="cli">praisonai rag serve <a href="./src/praisonai/praisonai/cli/commands/rag.py">--help</a></code>
* <code title="cli">praisonai realtime realtime-main <a href="./src/praisonai/praisonai/cli/commands/realtime.py">--help</a></code>
* <code title="cli">praisonai recipe install <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe list <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe run <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai registry list <a href="./src/praisonai/praisonai/cli/commands/registry.py">--help</a></code>
* <code title="cli">praisonai registry serve <a href="./src/praisonai/praisonai/cli/commands/registry.py">--help</a></code>
* <code title="cli">praisonai replay cleanup <a href="./src/praisonai/praisonai/cli/commands/replay.py">--help</a></code>
* <code title="cli">praisonai replay context <a href="./src/praisonai/praisonai/cli/commands/replay.py">--help</a></code>
* <code title="cli">praisonai replay dashboard <a href="./src/praisonai/praisonai/cli/commands/replay.py">--help</a></code>
* <code title="cli">praisonai replay delete <a href="./src/praisonai/praisonai/cli/commands/replay.py">--help</a></code>
* <code title="cli">praisonai replay flow <a href="./src/praisonai/praisonai/cli/commands/replay.py">--help</a></code>
* <code title="cli">praisonai replay list <a href="./src/praisonai/praisonai/cli/commands/replay.py">--help</a></code>
* <code title="cli">praisonai replay show <a href="./src/praisonai/praisonai/cli/commands/replay.py">--help</a></code>
* <code title="cli">praisonai research research-main <a href="./src/praisonai/praisonai/cli/commands/research.py">--help</a></code>
* <code title="cli">praisonai retrieval index <a href="./src/praisonai/praisonai/cli/commands/retrieval.py">--help</a></code>
* <code title="cli">praisonai retrieval query <a href="./src/praisonai/praisonai/cli/commands/retrieval.py">--help</a></code>
* <code title="cli">praisonai retrieval search <a href="./src/praisonai/praisonai/cli/commands/retrieval.py">--help</a></code>
* <code title="cli">praisonai rules add <a href="./src/praisonai/praisonai/cli/commands/rules.py">--help</a></code>
* <code title="cli">praisonai rules clear <a href="./src/praisonai/praisonai/cli/commands/rules.py">--help</a></code>
* <code title="cli">praisonai rules list <a href="./src/praisonai/praisonai/cli/commands/rules.py">--help</a></code>
* <code title="cli">praisonai run <a href="./src/praisonai/praisonai/cli/main.py">--help</a></code>
* <code title="cli">praisonai run run-main <a href="./src/praisonai/praisonai/cli/commands/run.py">--help</a></code>
* <code title="cli">praisonai schedule delete <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule describe <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule list <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule logs <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule restart <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule schedule-callback <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule start <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule stats <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule stop <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai serve serve-callback <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve start <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve status <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve stop <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai session delete <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session export <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session import <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session list <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session resume <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session show <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai skills create <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai skills info <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai skills install <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai skills list <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai skills search <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai skills validate <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai standardise check <a href="./src/praisonai/praisonai/cli/commands/standardise.py">--help</a></code>
* <code title="cli">praisonai standardise fix <a href="./src/praisonai/praisonai/cli/commands/standardise.py">--help</a></code>
* <code title="cli">praisonai standardise init <a href="./src/praisonai/praisonai/cli/commands/standardise.py">--help</a></code>
* <code title="cli">praisonai standardise report <a href="./src/praisonai/praisonai/cli/commands/standardise.py">--help</a></code>
* <code title="cli">praisonai templates create <a href="./src/praisonai/praisonai/cli/commands/templates.py">--help</a></code>
* <code title="cli">praisonai templates list <a href="./src/praisonai/praisonai/cli/commands/templates.py">--help</a></code>
* <code title="cli">praisonai test info <a href="./src/praisonai/praisonai/cli/commands/test.py">--help</a></code>
* <code title="cli">praisonai test interactive <a href="./src/praisonai/praisonai/cli/commands/test.py">--help</a></code>
* <code title="cli">praisonai test run <a href="./src/praisonai/praisonai/cli/commands/test.py">--help</a></code>
* <code title="cli">praisonai todo add <a href="./src/praisonai/praisonai/cli/commands/todo.py">--help</a></code>
* <code title="cli">praisonai todo done <a href="./src/praisonai/praisonai/cli/commands/todo.py">--help</a></code>
* <code title="cli">praisonai todo list <a href="./src/praisonai/praisonai/cli/commands/todo.py">--help</a></code>
* <code title="cli">praisonai tools info <a href="./src/praisonai/praisonai/cli/commands/tools.py">--help</a></code>
* <code title="cli">praisonai tools list <a href="./src/praisonai/praisonai/cli/commands/tools.py">--help</a></code>
* <code title="cli">praisonai tools test <a href="./src/praisonai/praisonai/cli/commands/tools.py">--help</a></code>
* <code title="cli">praisonai traces disable <a href="./src/praisonai/praisonai/cli/commands/traces.py">--help</a></code>
* <code title="cli">praisonai traces enable <a href="./src/praisonai/praisonai/cli/commands/traces.py">--help</a></code>
* <code title="cli">praisonai traces list <a href="./src/praisonai/praisonai/cli/commands/traces.py">--help</a></code>
* <code title="cli">praisonai traces status <a href="./src/praisonai/praisonai/cli/commands/traces.py">--help</a></code>
* <code title="cli">praisonai train agents <a href="./src/praisonai/praisonai/cli/commands/train.py">--help</a></code>
* <code title="cli">praisonai train list <a href="./src/praisonai/praisonai/cli/commands/train.py">--help</a></code>
* <code title="cli">praisonai train llm <a href="./src/praisonai/praisonai/cli/commands/train.py">--help</a></code>
* <code title="cli">praisonai train show <a href="./src/praisonai/praisonai/cli/commands/train.py">--help</a></code>
* <code title="cli">praisonai train train-callback <a href="./src/praisonai/praisonai/cli/commands/train.py">--help</a></code>
* <code title="cli">praisonai ui chat <a href="./src/praisonai/praisonai/cli/commands/ui.py">--help</a></code>
* <code title="cli">praisonai ui code <a href="./src/praisonai/praisonai/cli/commands/ui.py">--help</a></code>
* <code title="cli">praisonai ui gradio <a href="./src/praisonai/praisonai/cli/commands/ui.py">--help</a></code>
* <code title="cli">praisonai ui realtime <a href="./src/praisonai/praisonai/cli/commands/ui.py">--help</a></code>
* <code title="cli">praisonai ui ui-main <a href="./src/praisonai/praisonai/cli/commands/ui.py">--help</a></code>
* <code title="cli">praisonai version check <a href="./src/praisonai/praisonai/cli/commands/version.py">--help</a></code>
* <code title="cli">praisonai version show <a href="./src/praisonai/praisonai/cli/commands/version.py">--help</a></code>
* <code title="cli">praisonai version version-callback <a href="./src/praisonai/praisonai/cli/commands/version.py">--help</a></code>
* <code title="cli">praisonai workflow create <a href="./src/praisonai/praisonai/cli/commands/workflow.py">--help</a></code>
* <code title="cli">praisonai workflow list <a href="./src/praisonai/praisonai/cli/commands/workflow.py">--help</a></code>
* <code title="cli">praisonai workflow run <a href="./src/praisonai/praisonai/cli/commands/workflow.py">--help</a></code>

# TypeScript

Types/Exports:
```ts
export { Agent, Agents, PraisonAIAgents, Router } from "./agent";
export type { PraisonAIAgentsConfig, SimpleAgentConfig, SimpleRouteConfig, SimpleRouterConfig } from "./agent";
export { AudioAgent, createAudioAgent } from "./agent/audio";
export type { AudioAgentConfig, AudioProvider, AudioSpeakOptions, AudioSpeakResult, AudioTranscribeOptions, AudioTranscribeResult } from "./agent/audio";
export { ContextAgent, createContextAgent } from "./agent/context";
export { Handoff, handoff, handoffFilters } from "./agent/handoff";
export { ImageAgent, createImageAgent } from "./agent/image";
export { PromptExpanderAgent, createPromptExpanderAgent } from "./agent/prompt-expander";
export { QueryRewriterAgent, createQueryRewriterAgent } from "./agent/query-rewriter";
export { DeepResearchAgent, createDeepResearchAgent } from "./agent/research";
export { RouterAgent, createRouter, routeConditions } from "./agent/router";
export { // Agent loop
  createAgentLoop, // DevTools
  enableDevTools, // MCP
  createMCP, // Middleware (renamed to avoid conflicts)
  createCachingMiddleware, // Models
  createModel, // Multimodal
  createImagePart, // Next.js
  createRouteHandler, // OAuth for MCP
  type OAuthClientProvider, // Server adapters
  createHttpHandler, // Speech & Transcription
  generateSpeech, // Telemetry (AI SDK v6 parity)
  configureTelemetry, // Tool Approval (AI SDK v6 parity)
  ApprovalManager, // Tools
  defineTool, // UI Message (AI SDK v6 parity)
  convertToModelMessages, AIAgentStep, AIEmbedManyResult, AIEmbedOptions, AIEmbedResult, AIFilePart, AIGenerateImageOptions, AIGenerateImageResult, AIGenerateObjectOptions, AIGenerateObjectResult, AIGenerateTextOptions, AIGenerateTextResult, AIImagePart, AIMiddleware, AIMiddlewareConfig, AIModelMessage, AISpan, AISpanKind, AISpanOptions, AISpanStatus, AIStreamObjectOptions, AIStreamObjectResult, AIStreamTextOptions, AIStreamTextResult, AITelemetryEvent, AITelemetrySettings, AITextPart, AIToolDefinition, AITracer, AgentLoop, DANGEROUS_PATTERNS, MCPClientType, MODEL_ALIASES, SPEECH_MODELS, TRANSCRIPTION_MODELS, ToolApprovalDeniedError, ToolApprovalTimeoutError, aiEmbed, aiEmbedMany, aiGenerateImage, aiGenerateObject, aiGenerateText, aiStreamObject, aiStreamText, applyMiddleware, autoEnableDevTools, base64ToUint8Array, clearAICache, clearEvents, closeAllMCPClients, closeMCPClient, convertToUIMessages, createAILoggingMiddleware, createAISpan, createApprovalResponse, createDangerousPatternChecker, createDevToolsMiddleware, createExpressHandler, createFastifyHandler, createFilePart, createHonoHandler, createMultimodalMessage, createNestHandler, createPagesHandler, createPdfPart, createSystemMessage, createTelemetryMiddleware, createTelemetrySettings, createTextMessage, createTextPart, createToolSet, disableAITelemetry, disableDevTools, enableAITelemetry, functionToTool, getAICacheStats, getApprovalManager, getDevToolsState, getDevToolsUrl, getEvents, getMCPClient, getModel, getTelemetrySettings, getToolsNeedingApproval, getTracer, hasModelAlias, hasPendingApprovals, initOpenTelemetry, isDangerous, isDataUrl, isDevToolsEnabled, isTelemetryEnabled, isUrl, listModelAliases, mcpToolsToAITools, parseModel, pipeUIMessageStreamToResponse, recordEvent, resolveModelAlias, safeValidateUIMessages, setApprovalManager, stopAfterSteps, stopWhen, stopWhenNoToolCalls, toMessageContent, toUIMessageStreamResponse, transcribe, uint8ArrayToBase64, validateUIMessages, withApproval, withSpan, wrapModel } from "./ai";
export { AutoAgents, createAutoAgents } from "./auto";
export { BaseCache, FileCache, MemoryCache, createFileCache, createMemoryCache } from "./cache";
export { CLI_SPEC_VERSION, executeCommand, parseArgs } from "./cli";
export { // Autonomy Mode
  AutonomyManager, // Background Jobs
  JobQueue, // Checkpoints
  CheckpointManager, // Cost Tracker
  CostTracker, // External Agents
  BaseExternalAgent, // Fast Context
  FastContext, // Flow Display
  FlowDisplay, // Git Integration
  GitManager, // Interactive TUI
  InteractiveTUI, // N8N Integration
  N8NIntegration, // Repo Map
  RepoMap, // Sandbox Executor
  SandboxExecutor, // Scheduler
  Scheduler, // Slash Commands
  SlashCommandHandler, AiderAgent, ClaudeCodeAgent, CodexCliAgent, CommandValidator, CostTokenUsage, DEFAULT_BLOCKED_COMMANDS, DEFAULT_BLOCKED_PATHS, DEFAULT_IGNORE_PATTERNS, DiffViewer, FileCheckpointStorage, FileJobStorage, GeminiCliAgent, GenericExternalAgent, HistoryManager, MODEL_PRICING, MODE_POLICIES, MemoryCheckpointStorage, MemoryJobStorage, StatusDisplay, cliApprovalPrompt, createAutonomyManager, createCheckpointManager, createCostTracker, createDiffViewer, createExternalAgent, createFastContext, createFileCheckpointStorage, createFileJobStorage, createFlowDisplay, createGitManager, createHistoryManager, createInteractiveTUI, createJobQueue, createN8NIntegration, createRepoMap, createSandboxExecutor, createScheduler, createSlashCommandHandler, createStatusDisplay, cronExpressions, estimateTokens, executeSlashCommand, externalAgentAsTool, formatCost, getExternalAgentRegistry, getQuickContext, getRepoTree, isSlashCommand, parseSlashCommand, registerCommand, renderWorkflow, sandboxExec, triggerN8NWebhook } from "./cli/features";
export { createDbAdapter, db, getDefaultDbAdapter, setDefaultDbAdapter } from "./db";
export type { DbAdapter, DbConfig, DbMessage, DbRun, DbTrace } from "./db";
export { MemoryPostgresAdapter, NeonPostgresAdapter, PostgresSessionStorage, createMemoryPostgres, createNeonPostgres, createPostgresSessionStorage } from "./db/postgres";
export { MemoryRedisAdapter, UpstashRedisAdapter, createMemoryRedis, createUpstashRedis } from "./db/redis";
export { SQLiteAdapter, createSQLiteAdapter } from "./db/sqlite";
export { EvalResults, EvalSuite, Evaluator, accuracyEval, containsKeywordsCriterion, createDefaultEvaluator, createEvalResults, createEvaluator, lengthCriterion, noHarmfulContentCriterion, performanceEval, relevanceCriterion, reliabilityEval } from "./eval";
export { AgentEventBus, AgentEvents, EventEmitterPubSub, PubSub, createEventBus, createPubSub } from "./events";
export { LLMGuardrail, createLLMGuardrail } from "./guardrails/llm-guardrail";
export { DisplayTypes, HooksManager, WorkflowHooksExecutor, clearAllCallbacks, clearApprovalCallback, createHooksManager, createLoggingOperationHooks, createLoggingWorkflowHooks, createTimingWorkflowHooks, createValidationOperationHooks, createWorkflowHooks, executeCallback, executeSyncCallback, getRegisteredDisplayTypes, hasApprovalCallback, registerApprovalCallback, registerDisplayCallback, requestApproval, unregisterDisplayCallback } from "./hooks";
export { // Computer Use
  createComputerUse, ComputerUseClient, createCLIApprovalPrompt, createComputerUseAgent } from "./integrations/computer-use";
export { BaseObservabilityProvider, ConsoleObservabilityProvider, LangfuseObservabilityProvider, MemoryObservabilityProvider, ObservabilityTraceContext, createConsoleObservability, createLangfuseObservability, createMemoryObservability } from "./integrations/observability";
export { // Natural Language Postgres
  createNLPostgres, NLPostgresClient, NLPostgresConfig, createPostgresTool } from "./integrations/postgres";
export { // Slack
  createSlackBot, SlackBot, parseSlackMessage, verifySlackSignature } from "./integrations/slack";
export { BaseVectorStore, ChromaVectorStore, MemoryVectorStore, PineconeVectorStore, QdrantVectorStore, VectorQueryResult, WeaviateVectorStore, createChromaStore, createMemoryVectorStore, createPineconeStore, createQdrantStore, createWeaviateStore } from "./integrations/vector";
export { BaseVoiceProvider, ElevenLabsVoiceProvider, OpenAIVoiceProvider, createElevenLabsVoice, createOpenAIVoice } from "./integrations/voice";
export { GraphRAG, GraphStore, createGraphRAG } from "./knowledge/graph-rag";
export { BaseReranker, CohereReranker, CrossEncoderReranker, LLMReranker, createCohereReranker, createCrossEncoderReranker, createLLMReranker } from "./knowledge/reranker";
export { // Provider classes
  OpenAIProvider, // Provider factory and utilities
  createProvider, // Provider registry (extensibility API)
  ProviderRegistry, // Types
  type LLMProvider, AnthropicProvider, BaseProvider, GoogleProvider, ProviderMessage, ProviderToolDefinition, createProviderRegistry, getAvailableProviders, getDefaultProvider, getDefaultRegistry, hasProvider, isProviderAvailable, listProviders, parseModelString, registerBuiltinProviders, registerProvider, unregisterProvider } from "./llm/providers";
export { ADAPTERS, AISDK_PROVIDERS, COMMUNITY_PROVIDERS, PROVIDER_ALIASES } from "./llm/providers/ai-sdk/types";
export { MCPClient, MCPSecurity, MCPServer, MCPSessionManager, createApiKeyPolicy, createMCPClient, createMCPSecurity, createMCPServer, createMCPSession, createRateLimitPolicy, getMCPTools } from "./mcp";
export { AutoMemory, AutoMemoryKnowledgeBase, AutoMemoryVectorStore, DEFAULT_POLICIES, createAutoMemory, createLLMSummarizer } from "./memory/auto-memory";
export { DocsManager, createDocsManager } from "./memory/docs-manager";
export { FileMemory, createFileMemory } from "./memory/file-memory";
export { MemoryHooks, createEncryptionHooks, createLoggingHooks, createMemoryHooks, createValidationHooks } from "./memory/hooks";
export { Memory, createMemory } from "./memory/memory";
export type { MemoryConfig, MemoryEntry } from "./memory/memory";
export { RulesManager, createRulesManager, createSafetyRules } from "./memory/rules-manager";
export { // Adapters
  NoopObservabilityAdapter, // Constants
  OBSERVABILITY_TOOLS, // Global adapter management
  setObservabilityAdapter, // Types
  type SpanKind, ConsoleObservabilityAdapter, MemoryObservabilityAdapter, clearAdapterCache, createConsoleAdapter, createMemoryAdapter, createObservabilityAdapter, getObservabilityAdapter, getObservabilityToolInfo, hasObservabilityToolEnvVar, listObservabilityTools, noopAdapter, resetObservabilityAdapter, trace } from "./observability";
export { Plan, PlanStep, PlanStorage, PlanningAgent, TaskAgent, TodoItem, TodoList, createPlan, createPlanStorage, createPlanningAgent, createTaskAgent, createTodoList } from "./planning";
export { SkillManager, createSkillManager, parseSkillFile } from "./skills";
export { AgentTelemetry, PerformanceMonitor, TelemetryCollector, TelemetryIntegration, cleanupTelemetry, createAgentTelemetry, createConsoleSink, createHTTPSink, createPerformanceMonitor, createTelemetryIntegration, disableTelemetry, enableTelemetry, getTelemetry } from "./telemetry";
export { // Subagent Tool (agent-as-tool pattern)
  SubagentTool, BaseTool, FunctionTool, ToolRegistry, ToolResult, ToolValidationError, createDelegator, createSubagentTool, createSubagentTools, createTool, getRegistry, getTool, registerTool, tool, validateTool } from "./tools";
export { airweaveSearch, bedrockBrowserClick, bedrockBrowserFill, bedrockBrowserNavigate, bedrockCodeInterpreter, codeExecution, codeMode, createCustomTool, exaSearch, firecrawlCrawl, firecrawlScrape, parallelSearch, perplexitySearch, registerCustomTool, registerLocalTool, registerNpmTool, superagentGuard, superagentRedact, superagentVerify, tavilyCrawl, tavilyExtract, tavilySearch, valyuBioSearch, valyuCompanyResearch, valyuEconomicsSearch, valyuFinanceSearch, valyuPaperSearch, valyuPatentSearch, valyuSecSearch, valyuWebSearch } from "./tools/builtins";
export { MissingDependencyError, MissingEnvVarError, ToolsRegistry, composeMiddleware, createLoggingMiddleware, createRateLimitMiddleware, createRedactionMiddleware, createRetryMiddleware, createTimeoutMiddleware, createToolsRegistry, createTracingMiddleware, createValidationMiddleware, getToolsRegistry, resetToolsRegistry } from "./tools/registry";
export type { InstallHints, PraisonTool, RedactionHooks, RegisteredTool, ToolCapabilities, ToolExecutionContext, ToolExecutionResult, ToolFactory, ToolHooks, ToolInstallStatus, ToolLimits, ToolLogger, ToolMetadata, ToolMiddleware, ToolParameterProperty, ToolParameterSchema } from "./tools/registry";
export { registerBuiltinTools, tools } from "./tools/tools";
export { // New: Python-parity Loop and Repeat classes
  Loop, // WorkflowStep class
  WorkflowStep, Repeat, Workflow, loop, loopPattern, parallel, repeat, repeatPattern, route } from "./workflows";
export type { LoopConfig, LoopResult, RepeatConfig, RepeatContext, RepeatResult, StepContextConfig, StepExecutionConfig, StepOutputConfig, StepResult, StepRoutingConfig, WorkflowContext, WorkflowStepConfig } from "./workflows";
export { createWorkflowFromYAML, loadWorkflowFromFile, parseYAMLWorkflow, validateWorkflowDefinition } from "./workflows/yaml-parser";
```

# Optional Plugins

External tools are available via `praisonai-tools` package:

```bash
pip install praisonai-tools
```

See [PraisonAI-tools](https://github.com/MervinPraison/PraisonAI-tools) for available tools.
