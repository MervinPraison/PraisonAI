# PraisonAI API Reference

This file is auto-generated. Do not edit manually.
Regenerate with: `praisonai docs api-md --write`

# Shared Types

Types:
```python
from praisonaiagents import ContextPolicy, GuardrailResult, HandoffConfig, HandoffCycleError, HandoffDepthError, HandoffError, HandoffInputData, HandoffResult, HandoffTimeoutError, ReflectionOutput, StepResult, TaskOutput, ToolResult, ToolValidationError, WorkflowContext
```

Methods:

* <code title="class GuardrailResult">GuardrailResult.<a href="./src/praisonai-agents/praisonaiagents/guardrails/guardrail_result.py">from_tuple</a>(result: Tuple[bool, Any]) -> 'GuardrailResult'</code>
* <code title="class HandoffConfig">HandoffConfig.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">from_dict</a>(data: Dict[str, Any]) -> 'HandoffConfig'</code>
* <code title="class HandoffConfig">HandoffConfig.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class TaskOutput">TaskOutput.<a href="./src/praisonai-agents/praisonaiagents/main.py">json</a>() -> Optional[str]</code>
* <code title="class TaskOutput">TaskOutput.<a href="./src/praisonai-agents/praisonaiagents/main.py">to_dict</a>() -> dict</code>
* <code title="class ToolResult">ToolResult.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">to_dict</a>() -> Dict[str, Any]</code>

# Agents

Types:
```python
from praisonaiagents import Agent, AutoAgents, AutoRagAgent, ContextAgent, DeepResearchAgent, ImageAgent, PlanningAgent, PromptExpanderAgent, QueryRewriterAgent, create_context_agent
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
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">chat</a>(prompt, temperature = 1.0, tools = None, output_json = None, output_pydantic = None, reasoning_steps = False, stream = None, task_name = None, task_description = None, task_id = None, config = None, force_retrieval = False, skip_retrieval = False, attachments = None, tool_choice = None)</code>
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
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">run_autonomous</a>(prompt: str, max_iterations: Optional[int] = None, timeout_seconds: Optional[float] = None, completion_promise: Optional[str] = None, clear_context: bool = False)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">run_autonomous_async</a>(prompt: str, max_iterations: Optional[int] = None, timeout_seconds: Optional[float] = None, completion_promise: Optional[str] = None, clear_context: bool = False)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">session_id</a>() -> Optional[str]</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">skill_manager</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">start</a>(prompt: str = None, **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">store_memory</a>(content: str, memory_type: str = 'short_term', **kwargs)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">stream_emitter</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">stream_emitter</a>(value)</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">switch_model</a>(new_model: str) -> None</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">thinking_budget</a>()</code>
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent/agent.py">thinking_budget</a>(value)</code>
* <code title="class AutoAgents">AutoAgents.<a href="./src/praisonai-agents/praisonaiagents/agents/autoagents.py">astart</a>()</code>
* <code title="class AutoAgents">AutoAgents.<a href="./src/praisonai-agents/praisonaiagents/agents/autoagents.py">start</a>()</code>
* <code title="class AutoRagAgent">AutoRagAgent.<a href="./src/praisonai-agents/praisonaiagents/agents/auto_rag_agent.py">achat</a>(message: str, **kwargs) -> str</code>
* <code title="class AutoRagAgent">AutoRagAgent.<a href="./src/praisonai-agents/praisonaiagents/agents/auto_rag_agent.py">chat</a>(message: str, **kwargs) -> str</code>
* <code title="class AutoRagAgent">AutoRagAgent.<a href="./src/praisonai-agents/praisonaiagents/agents/auto_rag_agent.py">name</a>() -> str</code>
* <code title="class AutoRagAgent">AutoRagAgent.<a href="./src/praisonai-agents/praisonaiagents/agents/auto_rag_agent.py">rag</a>() -> Optional['RAG']</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">aanalyze_codebase</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">acreate_implementation_blueprint</a>(feature_request: str, context_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">agenerate_prp</a>(feature_request: str, context_analysis: Optional[Dict[str, Any]] = None) -> str</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">analyze_codebase</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">analyze_codebase_with_gitingest</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">analyze_integration_points</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">analyze_test_patterns</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">build_implementation_blueprint</a>(feature_request: str, context_analysis: Dict[str, Any] = None) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">compile_context_documentation</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">create_implementation_blueprint</a>(feature_request: str, context_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">create_quality_gates</a>(requirements: List[str]) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">create_validation_framework</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">execute_prp</a>(prp_file_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">extract_implementation_patterns</a>(project_path: str, ast_analysis: Dict[str, Any] = None) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">generate_comprehensive_prp</a>(feature_request: str, context_analysis: Dict[str, Any] = None) -> str</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">generate_feature_prp</a>(feature_request: str) -> str</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">generate_prp</a>(feature_request: str, context_analysis: Optional[Dict[str, Any]] = None) -> str</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">get_agent_interaction_summary</a>() -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">log_debug</a>(message: str, **kwargs)</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">perform_ast_analysis</a>(project_path: str) -> Dict[str, Any]</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">save_comprehensive_session_report</a>()</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">save_markdown_output</a>(content: str, filename: str, section_title: str = 'Output')</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">setup_logging</a>()</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">setup_output_directories</a>()</code>
* <code title="class ContextAgent">ContextAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">start</a>(input_text: str) -> str</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">aresearch</a>(query: str, instructions: Optional[str] = None, model: Optional[str] = None, summary_mode: Optional[Literal['auto', 'detailed', 'concise']] = None, web_search: Optional[bool] = None, code_interpreter: Optional[bool] = None, mcp_servers: Optional[List[Dict[str, Any]]] = None, file_ids: Optional[List[str]] = None, file_search: Optional[bool] = None, file_search_stores: Optional[List[str]] = None) -> DeepResearchResponse</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">async_openai_client</a>()</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">clarify</a>(query: str, model: Optional[str] = None) -> str</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">follow_up</a>(query: str, previous_interaction_id: str, model: Optional[str] = None) -> DeepResearchResponse</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">gemini_client</a>()</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">openai_client</a>()</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">research</a>(query: str, instructions: Optional[str] = None, model: Optional[str] = None, summary_mode: Optional[Literal['auto', 'detailed', 'concise']] = None, web_search: Optional[bool] = None, code_interpreter: Optional[bool] = None, mcp_servers: Optional[List[Dict[str, Any]]] = None, file_ids: Optional[List[str]] = None, file_search: Optional[bool] = None, file_search_stores: Optional[List[str]] = None, stream: bool = True) -> DeepResearchResponse</code>
* <code title="class DeepResearchAgent">DeepResearchAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/deep_research_agent.py">rewrite_query</a>(query: str, model: Optional[str] = None) -> str</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">achat</a>(prompt: str, temperature: float = 0.2, tools: Optional[List[Any]] = None, output_json: Optional[str] = None, output_pydantic: Optional[Any] = None, reasoning_steps: bool = False, **kwargs) -> Union[str, Dict[str, Any]]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">aedit</a>(image: str, prompt: str, mask: Optional[str] = None, n: int = 1, size: Optional[str] = None, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">agenerate</a>(prompt: str, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">agenerate_image</a>(prompt: str, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">avariation</a>(image: str, n: int = 1, size: Optional[str] = None, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">chat</a>(prompt: str, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">edit</a>(image: str, prompt: str, mask: Optional[str] = None, n: int = 1, size: Optional[str] = None, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">generate</a>(prompt: str, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">generate_image</a>(prompt: str, **kwargs) -> Dict[str, Any]</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">litellm</a>()</code>
* <code title="class ImageAgent">ImageAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/image_agent.py">variation</a>(image: str, n: int = 1, size: Optional[str] = None, **kwargs) -> Dict[str, Any]</code>
* <code title="class PlanningAgent">PlanningAgent.<a href="./src/praisonai-agents/praisonaiagents/planning/planner.py">analyze_context</a>(context: str) -> str</code>
* <code title="class PlanningAgent">PlanningAgent.<a href="./src/praisonai-agents/praisonaiagents/planning/planner.py">analyze_context_sync</a>(context: str) -> str</code>
* <code title="class PlanningAgent">PlanningAgent.<a href="./src/praisonai-agents/praisonaiagents/planning/planner.py">create_plan</a>(request: str, agents: List['Agent'], tasks: Optional[List['Task']] = None, context: Optional[str] = None) -> Plan</code>
* <code title="class PlanningAgent">PlanningAgent.<a href="./src/praisonai-agents/praisonaiagents/planning/planner.py">create_plan_sync</a>(request: str, agents: List['Agent'], tasks: Optional[List['Task']] = None, context: Optional[str] = None) -> Plan</code>
* <code title="class PlanningAgent">PlanningAgent.<a href="./src/praisonai-agents/praisonaiagents/planning/planner.py">is_tool_allowed</a>(tool_name: str) -> bool</code>
* <code title="class PlanningAgent">PlanningAgent.<a href="./src/praisonai-agents/praisonaiagents/planning/planner.py">refine_plan</a>(plan: Plan, feedback: str) -> Plan</code>
* <code title="class PlanningAgent">PlanningAgent.<a href="./src/praisonai-agents/praisonaiagents/planning/planner.py">refine_plan_sync</a>(plan: Plan, feedback: str) -> Plan</code>
* <code title="class PromptExpanderAgent">PromptExpanderAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/prompt_expander_agent.py">agent</a>()</code>
* <code title="class PromptExpanderAgent">PromptExpanderAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/prompt_expander_agent.py">expand</a>(prompt: str, strategy: ExpandStrategy = ..., context: Optional[str] = None) -> ExpandResult</code>
* <code title="class PromptExpanderAgent">PromptExpanderAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/prompt_expander_agent.py">expand_basic</a>(prompt: str, context: Optional[str] = None) -> ExpandResult</code>
* <code title="class PromptExpanderAgent">PromptExpanderAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/prompt_expander_agent.py">expand_creative</a>(prompt: str, context: Optional[str] = None) -> ExpandResult</code>
* <code title="class PromptExpanderAgent">PromptExpanderAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/prompt_expander_agent.py">expand_detailed</a>(prompt: str, context: Optional[str] = None) -> ExpandResult</code>
* <code title="class PromptExpanderAgent">PromptExpanderAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/prompt_expander_agent.py">expand_structured</a>(prompt: str, context: Optional[str] = None) -> ExpandResult</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">add_abbreviation</a>(abbrev: str, expansion: str) -> None</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">add_abbreviations</a>(abbreviations: Dict[str, str]) -> None</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">agent</a>()</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">rewrite</a>(query: str, strategy: RewriteStrategy = ..., chat_history: Optional[List[Dict[str, str]]] = None, context: Optional[str] = None, num_queries: int = None) -> RewriteResult</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">rewrite_basic</a>(query: str) -> RewriteResult</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">rewrite_contextual</a>(query: str, chat_history: List[Dict[str, str]]) -> RewriteResult</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">rewrite_hyde</a>(query: str) -> RewriteResult</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">rewrite_multi_query</a>(query: str, num_queries: int = None) -> RewriteResult</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">rewrite_step_back</a>(query: str) -> RewriteResult</code>
* <code title="class QueryRewriterAgent">QueryRewriterAgent.<a href="./src/praisonai-agents/praisonaiagents/agent/query_rewriter_agent.py">rewrite_sub_queries</a>(query: str) -> RewriteResult</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/agent/context_agent.py">create_context_agent</a>(llm: Optional[Union[str, Any]] = None, **kwargs) -> ContextAgent</code>

# Tools

Types:
```python
from praisonaiagents import BaseTool, FunctionTool, ToolRegistry, Tools, get_registry, get_tool, register_tool, tool, validate_tool
```

Methods:

* <code title="class BaseTool">BaseTool.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">__call__</a>(**kwargs) -> Any</code>
* <code title="class BaseTool">BaseTool.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">get_schema</a>() -> Dict[str, Any]</code>
* <code title="class BaseTool">BaseTool.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">run</a>(**kwargs) -> Any</code>
* <code title="class BaseTool">BaseTool.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">safe_run</a>(**kwargs) -> ToolResult</code>
* <code title="class BaseTool">BaseTool.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">validate</a>() -> bool</code>
* <code title="class BaseTool">BaseTool.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">validate_class</a>() -> bool</code>
* <code title="class FunctionTool">FunctionTool.<a href="./src/praisonai-agents/praisonaiagents/tools/decorator.py">__call__</a>(*args, **kwargs) -> Any</code>
* <code title="class FunctionTool">FunctionTool.<a href="./src/praisonai-agents/praisonaiagents/tools/decorator.py">injected_params</a>() -> Dict[str, Any]</code>
* <code title="class FunctionTool">FunctionTool.<a href="./src/praisonai-agents/praisonaiagents/tools/decorator.py">run</a>(**kwargs) -> Any</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">clear</a>() -> None</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">discover_plugins</a>() -> int</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">discover_single_file_plugins</a>() -> int</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">get</a>(name: str) -> Optional[Union[BaseTool, Callable]]</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">get_all</a>() -> Dict[str, Union[BaseTool, Callable]]</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">list_base_tools</a>() -> List[BaseTool]</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">list_tools</a>() -> List[str]</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">register</a>(tool: Union[BaseTool, Callable], name: Optional[str] = None, overwrite: bool = False) -> None</code>
* <code title="class ToolRegistry">ToolRegistry.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">unregister</a>(name: str) -> bool</code>
* <code title="class Tools">Tools.<a href="./src/praisonai-agents/praisonaiagents/tools/tools.py">internet_search</a>(*args, **kwargs)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">get_registry</a>() -> ToolRegistry</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">get_tool</a>(name: str) -> Optional[Union[BaseTool, Callable]]</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/tools/registry.py">register_tool</a>(tool: Union[BaseTool, Callable], name: Optional[str] = None) -> None</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/tools/decorator.py">tool</a>(func: Optional[Callable] = None) -> Union[FunctionTool, Callable[[Callable], FunctionTool]]</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/tools/base.py">validate_tool</a>(tool: Any) -> bool</code>

# Workflows

Types:
```python
from praisonaiagents import Loop, Parallel, Pipeline, Repeat, Route, Task, Workflow, loop, parallel, repeat, route
```

Methods:

* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">depends_on</a>()</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">depends_on</a>(value)</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">evaluate_when</a>(context: Dict[str, Any]) -> bool</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">execute_callback</a>(task_output: TaskOutput) -> None</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">execute_callback_sync</a>(task_output: TaskOutput) -> None</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">get_next_task</a>(context: Dict[str, Any]) -> Optional[str]</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">initialize_memory</a>()</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">store_in_memory</a>(content: str, agent_name: str = None, task_id: str = None)</code>
* <code title="class Task">Task.<a href="./src/praisonai-agents/praisonaiagents/task/task.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">loop</a>(step: Any = None, steps: Optional[List[Any]] = None, over: Optional[str] = None, from_csv: Optional[str] = None, from_file: Optional[str] = None, var_name: str = 'item', parallel: bool = False, max_workers: Optional[int] = None, output_variable: Optional[str] = None) -> Loop</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">parallel</a>(steps: List) -> Parallel</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">repeat</a>(step: Any, until: Optional[Callable[[WorkflowContext], bool]] = None, max_iterations: int = 10) -> Repeat</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">route</a>(routes: Dict[str, List], default: Optional[List] = None) -> Route</code>

# DB

Types:
```python
from praisonaiagents import db
```

# Memory

Types:
```python
from praisonaiagents import Memory, MemoryBackend, MemoryConfig
```

Methods:

* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">build_context_for_task</a>(task_descr: str, user_id: Optional[str] = None, additional: str = '', max_items: int = 3, include_in_output: Optional[bool] = None) -> str</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">calculate_quality_metrics</a>(output: str, expected_output: str, llm: Optional[str] = None, custom_prompt: Optional[str] = None) -> Dict[str, float]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">compute_quality_score</a>(completeness: float, relevance: float, clarity: float, accuracy: float, weights: Dict[str, float] = None) -> float</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">delete_long_term</a>(memory_id: str) -> bool</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">delete_memories</a>(memory_ids: List[str]) -> int</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">delete_memories_matching</a>(query: str, memory_type: Optional[str] = None, limit: int = 10) -> int</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">delete_memory</a>(memory_id: str, memory_type: Optional[str] = None) -> bool</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">delete_short_term</a>(memory_id: str) -> bool</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">finalize_task_output</a>(content: str, agent_name: str, quality_score: float, threshold: float = 0.7, metrics: Dict[str, Any] = None, task_id: str = None)</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">get_all_memories</a>() -> List[Dict[str, Any]]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">get_learn_context</a>() -> str</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">learn</a>()</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">reset_all</a>()</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">reset_entity_only</a>()</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">reset_long_term</a>()</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">reset_short_term</a>()</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">reset_user_memory</a>()</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">search</a>(query: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, limit: int = 5, rerank: bool = False, **kwargs) -> List[Dict[str, Any]]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">search_entity</a>(query: str, limit: int = 5) -> List[Dict[str, Any]]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">search_long_term</a>(query: str, limit: int = 5, relevance_cutoff: float = 0.0, min_quality: float = 0.0, rerank: bool = False, **kwargs) -> List[Dict[str, Any]]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">search_short_term</a>(query: str, limit: int = 5, min_quality: float = 0.0, relevance_cutoff: float = 0.0, rerank: bool = False, **kwargs) -> List[Dict[str, Any]]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">search_user_memory</a>(user_id: str, query: str, limit: int = 5, rerank: bool = False, **kwargs) -> List[Dict[str, Any]]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">search_with_quality</a>(query: str, min_quality: float = 0.0, memory_type: Literal['short', 'long'] = 'long', limit: int = 5) -> List[Dict[str, Any]]</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">store_entity</a>(name: str, type_: str, desc: str, relations: str)</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">store_long_term</a>(text: str, metadata: Dict[str, Any] = None, completeness: float = None, relevance: float = None, clarity: float = None, accuracy: float = None, weights: Dict[str, float] = None, evaluator_quality: float = None)</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">store_quality</a>(text: str, quality_score: float, task_id: Optional[str] = None, iteration: Optional[int] = None, metrics: Optional[Dict[str, float]] = None, memory_type: Literal['short', 'long'] = 'long') -> None</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">store_short_term</a>(text: str, metadata: Dict[str, Any] = None, completeness: float = None, relevance: float = None, clarity: float = None, accuracy: float = None, weights: Dict[str, float] = None, evaluator_quality: float = None)</code>
* <code title="class Memory">Memory.<a href="./src/praisonai-agents/praisonaiagents/memory/memory.py">store_user_memory</a>(user_id: str, text: str, extra: Dict[str, Any] = None)</code>
* <code title="class MemoryConfig">MemoryConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>

# Knowledge

Types:
```python
from praisonaiagents import Chunking, ChunkingStrategy, Knowledge, KnowledgeConfig
```

Methods:

* <code title="class Chunking">Chunking.<a href="./src/praisonai-agents/praisonaiagents/knowledge/chunking.py">SUPPORTED_CHUNKERS</a>() -> Dict[str, Any]</code>
* <code title="class Chunking">Chunking.<a href="./src/praisonai-agents/praisonaiagents/knowledge/chunking.py">__call__</a>(text: Union[str, List[str]], **kwargs) -> Union[List[Any], List[List[Any]]]</code>
* <code title="class Chunking">Chunking.<a href="./src/praisonai-agents/praisonaiagents/knowledge/chunking.py">chunk</a>(text: Union[str, List[str]], **kwargs) -> Union[List[Any], List[List[Any]]]</code>
* <code title="class Chunking">Chunking.<a href="./src/praisonai-agents/praisonaiagents/knowledge/chunking.py">chunker</a>()</code>
* <code title="class Chunking">Chunking.<a href="./src/praisonai-agents/praisonaiagents/knowledge/chunking.py">embedding_model</a>()</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">add</a>(file_path, user_id = None, agent_id = None, run_id = None, metadata = None)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">chunker</a>()</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">config</a>()</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">delete</a>(memory_id)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">delete_all</a>(user_id = None, agent_id = None, run_id = None)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">get</a>(memory_id)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">get_all</a>(user_id = None, agent_id = None, run_id = None)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">get_corpus_stats</a>()</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">history</a>(memory_id)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">index</a>(path: str, incremental: bool = True, force: bool = False, include_glob: list = None, exclude_glob: list = None, user_id: str = None, agent_id: str = None, run_id: str = None)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">markdown</a>()</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">memory</a>()</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">normalize_content</a>(content)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">reset</a>()</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">search</a>(query, user_id = None, agent_id = None, run_id = None, rerank = None, **kwargs)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">store</a>(content, user_id = None, agent_id = None, run_id = None, metadata = None)</code>
* <code title="class Knowledge">Knowledge.<a href="./src/praisonai-agents/praisonaiagents/knowledge/knowledge.py">update</a>(memory_id, data)</code>
* <code title="class KnowledgeConfig">KnowledgeConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>

# RAG

Types:
```python
from praisonaiagents import CitationsMode, ContextPack, RAG, RAGCitation, RAGConfig, RAGResult, RetrievalConfig, RetrievalPolicy
```

Methods:

* <code title="class ContextPack">ContextPack.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">format_for_prompt</a>(include_sources: bool = True) -> str</code>
* <code title="class ContextPack">ContextPack.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">from_dict</a>(data: Dict[str, Any]) -> 'ContextPack'</code>
* <code title="class ContextPack">ContextPack.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">has_citations</a>() -> bool</code>
* <code title="class ContextPack">ContextPack.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">aquery</a>(question: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, **kwargs) -> RAGResult</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">aretrieve</a>(query: str, **kwargs) -> ContextPack</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">astream</a>(question: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, **kwargs) -> AsyncIterator[str]</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">get_citations</a>(question: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, **kwargs) -> List[Citation]</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">llm</a>()</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">query</a>(question: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, **kwargs) -> RAGResult</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">retrieve</a>(query: str, **kwargs) -> ContextPack</code>
* <code title="class RAG">RAG.<a href="./src/praisonai-agents/praisonaiagents/rag/pipeline.py">stream</a>(question: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, run_id: Optional[str] = None, **kwargs) -> Iterator[str]</code>
* <code title="class RAGCitation">RAGCitation.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">from_dict</a>(data: Dict[str, Any]) -> 'Citation'</code>
* <code title="class RAGCitation">RAGCitation.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class RAGConfig">RAGConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">from_dict</a>(data: Dict[str, Any]) -> 'RAGConfig'</code>
* <code title="class RAGConfig">RAGConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class RAGResult">RAGResult.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">format_answer_with_citations</a>() -> str</code>
* <code title="class RAGResult">RAGResult.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">from_dict</a>(data: Dict[str, Any]) -> 'RAGResult'</code>
* <code title="class RAGResult">RAGResult.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">has_citations</a>() -> bool</code>
* <code title="class RAGResult">RAGResult.<a href="./src/praisonai-agents/praisonaiagents/rag/models.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class RetrievalConfig">RetrievalConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/retrieval_config.py">from_dict</a>(data: Dict[str, Any]) -> 'RetrievalConfig'</code>
* <code title="class RetrievalConfig">RetrievalConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/retrieval_config.py">get_strategy</a>(corpus_stats = None)</code>
* <code title="class RetrievalConfig">RetrievalConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/retrieval_config.py">get_token_budget</a>(model_name: Optional[str] = None)</code>
* <code title="class RetrievalConfig">RetrievalConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/retrieval_config.py">should_retrieve</a>(query: str, force: bool = False, skip: bool = False) -> bool</code>
* <code title="class RetrievalConfig">RetrievalConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/retrieval_config.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class RetrievalConfig">RetrievalConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/retrieval_config.py">to_knowledge_config</a>() -> Dict[str, Any]</code>
* <code title="class RetrievalConfig">RetrievalConfig.<a href="./src/praisonai-agents/praisonaiagents/rag/retrieval_config.py">to_rag_config</a>() -> Dict[str, Any]</code>

# Handoff

Types:
```python
from praisonaiagents import Handoff, RECOMMENDED_PROMPT_PREFIX, handoff, handoff_filters, prompt_with_handoff_instructions
```

Methods:

* <code title="class Handoff">Handoff.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">default_tool_description</a>() -> str</code>
* <code title="class Handoff">Handoff.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">default_tool_name</a>() -> str</code>
* <code title="class Handoff">Handoff.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">execute_async</a>(source_agent: 'Agent', prompt: str, context: Optional[Dict[str, Any]] = None) -> HandoffResult</code>
* <code title="class Handoff">Handoff.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">execute_programmatic</a>(source_agent: 'Agent', prompt: str, context: Optional[Dict[str, Any]] = None) -> HandoffResult</code>
* <code title="class Handoff">Handoff.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">to_tool_function</a>(source_agent: 'Agent') -> Callable</code>
* <code title="class Handoff">Handoff.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">tool_description</a>() -> str</code>
* <code title="class Handoff">Handoff.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">tool_name</a>() -> str</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">handoff</a>(agent: 'Agent', tool_name_override: Optional[str] = None, tool_description_override: Optional[str] = None, on_handoff: Optional[Callable] = None, input_type: Optional[type] = None, input_filter: Optional[Callable[[HandoffInputData], HandoffInputData]] = None, config: Optional[HandoffConfig] = None, context_policy: Optional[str] = None, timeout_seconds: Optional[float] = None, max_concurrent: Optional[int] = None, detect_cycles: Optional[bool] = None, max_depth: Optional[int] = None) -> Handoff</code>
* <code title="class handoff_filters">handoff_filters.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">keep_last_n_messages</a>(n: int) -> Callable[[HandoffInputData], HandoffInputData]</code>
* <code title="class handoff_filters">handoff_filters.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">remove_all_tools</a>(data: HandoffInputData) -> HandoffInputData</code>
* <code title="class handoff_filters">handoff_filters.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">remove_system_messages</a>(data: HandoffInputData) -> HandoffInputData</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/agent/handoff.py">prompt_with_handoff_instructions</a>(base_prompt: str, agent: 'Agent') -> str</code>

# Guardrails

Types:
```python
from praisonaiagents import GuardrailAction, GuardrailConfig, LLMGuardrail
```

Methods:

* <code title="class GuardrailConfig">GuardrailConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class LLMGuardrail">LLMGuardrail.<a href="./src/praisonai-agents/praisonaiagents/guardrails/llm_guardrail.py">__call__</a>(task_output: TaskOutput) -> Tuple[bool, Union[str, TaskOutput]]</code>

# Planning

Types:
```python
from praisonaiagents import ApprovalCallback, Plan, PlanStep, PlanStorage, PlanningConfig, READ_ONLY_TOOLS, RESTRICTED_TOOLS, TodoItem, TodoList
```

Methods:

* <code title="class ApprovalCallback">ApprovalCallback.<a href="./src/praisonai-agents/praisonaiagents/planning/approval.py">__call__</a>(plan: 'Plan') -> bool</code>
* <code title="class ApprovalCallback">ApprovalCallback.<a href="./src/praisonai-agents/praisonaiagents/planning/approval.py">always_approve</a>(plan: 'Plan') -> bool</code>
* <code title="class ApprovalCallback">ApprovalCallback.<a href="./src/praisonai-agents/praisonaiagents/planning/approval.py">always_reject</a>(plan: 'Plan') -> bool</code>
* <code title="class ApprovalCallback">ApprovalCallback.<a href="./src/praisonai-agents/praisonaiagents/planning/approval.py">approve_if_no_dangerous_tools</a>(plan: 'Plan') -> bool</code>
* <code title="class ApprovalCallback">ApprovalCallback.<a href="./src/praisonai-agents/praisonaiagents/planning/approval.py">approve_if_small</a>(plan: 'Plan', max_steps: int = 5) -> bool</code>
* <code title="class ApprovalCallback">ApprovalCallback.<a href="./src/praisonai-agents/praisonaiagents/planning/approval.py">async_call</a>(plan: 'Plan') -> bool</code>
* <code title="class ApprovalCallback">ApprovalCallback.<a href="./src/praisonai-agents/praisonaiagents/planning/approval.py">console_approval</a>(plan: 'Plan') -> bool</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">add_step</a>(step: PlanStep) -> None</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">approve</a>() -> None</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">cancel</a>() -> None</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">complete</a>() -> None</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">completed_step_ids</a>() -> List[str]</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">from_dict</a>(data: Dict[str, Any]) -> 'Plan'</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">from_markdown</a>(markdown: str) -> 'Plan'</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">get_next_steps</a>() -> List[PlanStep]</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">get_step</a>(step_id: str) -> Optional[PlanStep]</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">is_complete</a>() -> bool</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">progress</a>() -> float</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">remove_step</a>(step_id: str) -> bool</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">start_execution</a>() -> None</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">to_markdown</a>() -> str</code>
* <code title="class Plan">Plan.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">update_step_status</a>(step_id: str, status: str) -> bool</code>
* <code title="class PlanStep">PlanStep.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">from_dict</a>(data: Dict[str, Any]) -> 'PlanStep'</code>
* <code title="class PlanStep">PlanStep.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">is_ready</a>(completed_steps: List[str]) -> bool</code>
* <code title="class PlanStep">PlanStep.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">mark_complete</a>() -> None</code>
* <code title="class PlanStep">PlanStep.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">mark_in_progress</a>() -> None</code>
* <code title="class PlanStep">PlanStep.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">mark_skipped</a>() -> None</code>
* <code title="class PlanStep">PlanStep.<a href="./src/praisonai-agents/praisonaiagents/planning/plan.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">cleanup_old_plans</a>(keep_count: int = 10) -> int</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">delete_plan</a>(plan_id: str) -> bool</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">delete_todo</a>(name: str) -> bool</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">get_latest_plan</a>() -> Optional[Plan]</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">list_plans</a>() -> List[Dict[str, Any]]</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">list_todos</a>() -> List[str]</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">load_plan</a>(plan_id: str) -> Optional[Plan]</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">load_plan_from_file</a>(path: str) -> Optional[Plan]</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">load_todo</a>(name: str = 'current') -> Optional[TodoList]</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">save_plan</a>(plan: Plan, filename: Optional[str] = None) -> str</code>
* <code title="class PlanStorage">PlanStorage.<a href="./src/praisonai-agents/praisonaiagents/planning/storage.py">save_todo</a>(todo: TodoList, name: str = 'current') -> str</code>
* <code title="class PlanningConfig">PlanningConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class TodoItem">TodoItem.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">complete</a>() -> None</code>
* <code title="class TodoItem">TodoItem.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">from_dict</a>(data: Dict[str, Any]) -> 'TodoItem'</code>
* <code title="class TodoItem">TodoItem.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">is_ready</a>(completed_ids: List[str]) -> bool</code>
* <code title="class TodoItem">TodoItem.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">reset</a>() -> None</code>
* <code title="class TodoItem">TodoItem.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">start</a>() -> None</code>
* <code title="class TodoItem">TodoItem.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">add</a>(item: Union[TodoItem, str]) -> TodoItem</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">complete</a>(item_id: str) -> bool</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">completed</a>() -> List[TodoItem]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">completed_ids</a>() -> List[str]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">from_dict</a>(data: Dict[str, Any]) -> 'TodoList'</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">from_json</a>(json_str: str) -> 'TodoList'</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">from_markdown</a>(markdown: str) -> 'TodoList'</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">from_plan</a>(plan: 'Plan') -> 'TodoList'</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">get</a>(item_id: str) -> Optional[TodoItem]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">get_ready_items</a>() -> List[TodoItem]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">in_progress</a>() -> List[TodoItem]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">is_complete</a>() -> bool</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">pending</a>() -> List[TodoItem]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">progress</a>() -> float</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">remove</a>(item_id: str) -> bool</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">start</a>(item_id: str) -> bool</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">sync_with_plan</a>(plan: 'Plan') -> None</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">to_json</a>() -> str</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">to_markdown</a>() -> str</code>
* <code title="class TodoList">TodoList.<a href="./src/praisonai-agents/praisonaiagents/planning/todo.py">update_from_plan</a>(plan: 'Plan') -> None</code>

# Skills

Types:
```python
from praisonaiagents import SkillLoader, SkillManager, SkillMetadata, SkillProperties, SkillsConfig
```

Methods:

* <code title="class SkillLoader">SkillLoader.<a href="./src/praisonai-agents/praisonaiagents/skills/loader.py">activate</a>(skill: LoadedSkill) -> bool</code>
* <code title="class SkillLoader">SkillLoader.<a href="./src/praisonai-agents/praisonaiagents/skills/loader.py">load</a>(skill_path: str, activate: bool = False) -> Optional[LoadedSkill]</code>
* <code title="class SkillLoader">SkillLoader.<a href="./src/praisonai-agents/praisonaiagents/skills/loader.py">load_all_resources</a>(skill: LoadedSkill) -> None</code>
* <code title="class SkillLoader">SkillLoader.<a href="./src/praisonai-agents/praisonaiagents/skills/loader.py">load_assets</a>(skill: LoadedSkill) -> dict</code>
* <code title="class SkillLoader">SkillLoader.<a href="./src/praisonai-agents/praisonaiagents/skills/loader.py">load_metadata</a>(skill_path: str) -> Optional[LoadedSkill]</code>
* <code title="class SkillLoader">SkillLoader.<a href="./src/praisonai-agents/praisonaiagents/skills/loader.py">load_references</a>(skill: LoadedSkill) -> dict</code>
* <code title="class SkillLoader">SkillLoader.<a href="./src/praisonai-agents/praisonaiagents/skills/loader.py">load_scripts</a>(skill: LoadedSkill) -> dict</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">activate</a>(skill: LoadedSkill) -> bool</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">activate_by_name</a>(name: str) -> bool</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">add_skill</a>(skill_path: str) -> Optional[LoadedSkill]</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">clear</a>() -> None</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">discover</a>(skill_dirs: Optional[List[str]] = None, include_defaults: bool = True) -> int</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">get_available_skills</a>() -> List[SkillMetadata]</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">get_instructions</a>(name: str) -> Optional[str]</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">get_skill</a>(name: str) -> Optional[LoadedSkill]</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">load_resources</a>(name: str) -> bool</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">skill_names</a>() -> List[str]</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">skills</a>() -> List[LoadedSkill]</code>
* <code title="class SkillManager">SkillManager.<a href="./src/praisonai-agents/praisonaiagents/skills/manager.py">to_prompt</a>() -> str</code>
* <code title="class SkillMetadata">SkillMetadata.<a href="./src/praisonai-agents/praisonaiagents/skills/models.py">from_properties</a>(props: SkillProperties) -> 'SkillMetadata'</code>
* <code title="class SkillProperties">SkillProperties.<a href="./src/praisonai-agents/praisonaiagents/skills/models.py">to_dict</a>() -> dict</code>
* <code title="class SkillsConfig">SkillsConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>

# Session

Types:
```python
from praisonaiagents import Session
```

Methods:

* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">Agent</a>(name: str, role: str = 'Assistant', instructions: Optional[str] = None, tools: Optional[List[Any]] = None, memory: bool = True, knowledge: Optional[List[str]] = None, **kwargs) -> 'Agent'</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">add_knowledge</a>(source: str) -> None</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">add_memory</a>(text: str, memory_type: str = 'long', **metadata) -> None</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">chat</a>(message: str, **kwargs) -> str</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">clear_memory</a>(memory_type: str = 'all') -> None</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">create_agent</a>(*args, **kwargs) -> 'Agent'</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">get_context</a>(query: str, max_items: int = 3) -> str</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">get_state</a>(key: str, default: Any = None) -> Any</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">increment_state</a>(key: str, increment: int = 1, default: int = 0) -> None</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">knowledge</a>() -> 'Knowledge'</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">memory</a>() -> 'Memory'</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">restore_state</a>() -> Dict[str, Any]</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">save_state</a>(state_data: Dict[str, Any]) -> None</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">search_knowledge</a>(query: str, limit: int = 5) -> List[Dict[str, Any]]</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">search_memory</a>(query: str, memory_type: str = 'long', limit: int = 5) -> List[Dict[str, Any]]</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">send_message</a>(message: str, **kwargs) -> str</code>
* <code title="class Session">Session.<a href="./src/praisonai-agents/praisonaiagents/session/api.py">set_state</a>(key: str, value: Any) -> None</code>

# MCP

Types:
```python
from praisonaiagents import MCP
```

Methods:

* <code title="class MCP">MCP.<a href="./src/praisonai-agents/praisonaiagents/mcp/mcp.py">get_tools</a>() -> List[Callable]</code>
* <code title="class MCP">MCP.<a href="./src/praisonai-agents/praisonaiagents/mcp/mcp.py">shutdown</a>()</code>
* <code title="class MCP">MCP.<a href="./src/praisonai-agents/praisonaiagents/mcp/mcp.py">to_openai_tool</a>()</code>

# Telemetry

Types:
```python
from praisonaiagents import MinimalTelemetry, TelemetryCollector, cleanup_telemetry_resources, disable_performance_mode, disable_telemetry, enable_performance_mode, enable_telemetry, get_telemetry
```

Methods:

* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">flush</a>()</code>
* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">get_metrics</a>() -> Dict[str, Any]</code>
* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">shutdown</a>()</code>
* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">track_agent_execution</a>(agent_name: str = None, success: bool = True, async_mode: bool = False)</code>
* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">track_error</a>(error_type: str = None)</code>
* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">track_feature_usage</a>(feature_name: str)</code>
* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">track_task_completion</a>(task_name: str = None, success: bool = True)</code>
* <code title="class MinimalTelemetry">MinimalTelemetry.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">track_tool_usage</a>(tool_name: str, success: bool = True, execution_time: float = None)</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">get_metrics</a>() -> Dict[str, Any]</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">record_cost</a>(cost: float, model: str = None)</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">record_tokens</a>(prompt_tokens: int, completion_tokens: int, model: str = None)</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">start</a>()</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">stop</a>()</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">trace_agent_execution</a>(agent_name: str, **attributes)</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">trace_llm_call</a>(model: str = None, **attributes)</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">trace_task_execution</a>(task_name: str, agent_name: str = None, **attributes)</code>
* <code title="class TelemetryCollector">TelemetryCollector.<a href="./src/praisonai-agents/praisonaiagents/telemetry/telemetry.py">trace_tool_call</a>(tool_name: str, **attributes)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/telemetry/__init__.py">cleanup_telemetry_resources</a>()</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/telemetry/__init__.py">disable_performance_mode</a>()</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/telemetry/__init__.py">disable_telemetry</a>()</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/telemetry/__init__.py">enable_performance_mode</a>()</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/telemetry/__init__.py">enable_telemetry</a>()</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/telemetry/__init__.py">get_telemetry</a>() -> 'MinimalTelemetry'</code>

# Observability

Types:
```python
from praisonaiagents import FlowDisplay, obs, track_workflow
```

Methods:

* <code title="class FlowDisplay">FlowDisplay.<a href="./src/praisonai-agents/praisonaiagents/flow_display.py">display</a>()</code>
* <code title="class FlowDisplay">FlowDisplay.<a href="./src/praisonai-agents/praisonaiagents/flow_display.py">start</a>()</code>
* <code title="class FlowDisplay">FlowDisplay.<a href="./src/praisonai-agents/praisonaiagents/flow_display.py">stop</a>()</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/flow_display.py">track_workflow</a>()</code>

# Context

Types:
```python
from praisonaiagents import ContextManager, ManagerConfig
```

Methods:

* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">capture_llm_boundary</a>(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> SnapshotHookData</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">emergency_truncate</a>(messages: List[Dict[str, Any]], target_tokens: int) -> List[Dict[str, Any]]</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">estimate_tokens</a>(text: str, validate: bool = False) -> Tuple[int, Optional[EstimationMetrics]]</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">get_history</a>() -> List[Dict[str, Any]]</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">get_last_snapshot_hook</a>() -> Optional[SnapshotHookData]</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">get_resolved_config</a>() -> Dict[str, Any]</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">get_stats</a>() -> Dict[str, Any]</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">get_tool_budget</a>(tool_name: str) -> int</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">process</a>(messages: List[Dict[str, Any]], system_prompt: str = '', tools: Optional[List[Dict[str, Any]]] = None, trigger: Literal['turn', 'tool_call', 'manual', 'overflow'] = 'turn') -> Dict[str, Any]</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">register_snapshot_callback</a>(callback: Callable[[SnapshotHookData], None]) -> None</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">reset</a>() -> None</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">set_tool_budget</a>(tool_name: str, max_tokens: int, protected: bool = False) -> None</code>
* <code title="class ContextManager">ContextManager.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">truncate_tool_output</a>(tool_name: str, output: str) -> str</code>
* <code title="class ManagerConfig">ManagerConfig.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">from_env</a>() -> 'ManagerConfig'</code>
* <code title="class ManagerConfig">ManagerConfig.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">merge</a>(**overrides) -> 'ManagerConfig'</code>
* <code title="class ManagerConfig">ManagerConfig.<a href="./src/praisonai-agents/praisonaiagents/context/manager.py">to_dict</a>() -> Dict[str, Any]</code>

# Config

Types:
```python
from praisonaiagents import AutonomyConfig, AutonomyLevel, CachingConfig, ExecutionConfig, ExecutionPreset, GuardrailConfig, HooksConfig, KnowledgeConfig, MemoryConfig, MultiAgentExecutionConfig, MultiAgentHooksConfig, MultiAgentMemoryConfig, MultiAgentOutputConfig, MultiAgentPlanningConfig, OutputConfig, OutputPreset, PlanningConfig, ReflectionConfig, SkillsConfig, TemplateConfig, WebConfig, WebSearchProvider
```

Methods:

* <code title="class AutonomyConfig">AutonomyConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class CachingConfig">CachingConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class ExecutionConfig">ExecutionConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class GuardrailConfig">GuardrailConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class HooksConfig">HooksConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class KnowledgeConfig">KnowledgeConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class MemoryConfig">MemoryConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class MultiAgentExecutionConfig">MultiAgentExecutionConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class MultiAgentHooksConfig">MultiAgentHooksConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class MultiAgentMemoryConfig">MultiAgentMemoryConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class MultiAgentOutputConfig">MultiAgentOutputConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class MultiAgentPlanningConfig">MultiAgentPlanningConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class OutputConfig">OutputConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class PlanningConfig">PlanningConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class ReflectionConfig">ReflectionConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class SkillsConfig">SkillsConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class TemplateConfig">TemplateConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class WebConfig">WebConfig.<a href="./src/praisonai-agents/praisonaiagents/config/feature_configs.py">to_dict</a>() -> Dict[str, Any]</code>

# Display

Types:
```python
from praisonaiagents import async_display_callbacks, clean_triple_backticks, display_error, display_generating, display_instruction, display_interaction, display_self_reflection, display_tool_call, error_logs, register_display_callback, sync_display_callbacks
```

Methods:

* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">clean_triple_backticks</a>(text: str) -> str</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">display_error</a>(message: str, console = None)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">display_generating</a>(content: str = '', start_time: Optional[float] = None)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">display_instruction</a>(message: str, console = None, agent_name: str = None, agent_role: str = None, agent_tools: List[str] = None)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">display_interaction</a>(message, response, markdown = True, generation_time = None, console = None, agent_name = None, agent_role = None, agent_tools = None, task_name = None, task_description = None, task_id = None, metrics = None)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">display_self_reflection</a>(message: str, console = None)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">display_tool_call</a>(message: str, console = None, tool_name: str = None, tool_input: dict = None, tool_output: str = None, elapsed_time: float = None, success: bool = True)</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/main.py">register_display_callback</a>(display_type: str, callback_fn, is_async: bool = False)</code>

# Utilities

Types:
```python
from praisonaiagents import ArrayMode, is_policy_string, parse_policy_string, resolve, resolve_autonomy, resolve_caching, resolve_context, resolve_execution, resolve_guardrail_policies, resolve_guardrails, resolve_hooks, resolve_knowledge, resolve_memory, resolve_output, resolve_planning, resolve_reflection, resolve_routing, resolve_skills, resolve_web
```

Methods:

* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/parse_utils.py">is_policy_string</a>(value: str) -> bool</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/parse_utils.py">parse_policy_string</a>(value: str) -> tuple</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve</a>(value: Any, param_name: str, config_class: Optional[Type] = None, presets: Optional[Dict[str, Any]] = None, default: Any = None, instance_check: Optional[Callable[[Any], bool]] = None, url_schemes: Optional[Dict[str, str]] = None, array_mode: Optional[str] = None, string_mode: Optional[str] = None) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_autonomy</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_caching</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_context</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_execution</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_guardrail_policies</a>(policies: list, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_guardrails</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_hooks</a>(value: Any, config_class: Optional[Type] = None) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_knowledge</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_memory</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_output</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_planning</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_reflection</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_routing</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_skills</a>(value: Any, config_class: Type) -> Any</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/config/param_resolver.py">resolve_web</a>(value: Any, config_class: Type) -> Any</code>

# Other

Types:
```python
from praisonaiagents import AgentAppConfig, AgentAppProtocol, AgentFlow, AgentManager, AgentOSConfig, AgentOSProtocol, AgentTeam, EmbeddingResult, aembedding, aembeddings, embedding, embeddings, get_dimensions
```

Methods:

* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">arun</a>(input: str = '', llm: Optional[str] = None, verbose: bool = False) -> Dict[str, Any]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">astart</a>(input: str = '', llm: Optional[str] = None, verbose: bool = False) -> Dict[str, Any]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">from_template</a>(uri: str, config: Optional[Dict[str, Any]] = None, offline: bool = False, **kwargs) -> 'Workflow'</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">get_history</a>() -> List[Dict[str, Any]]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">memory_config</a>() -> Optional[Dict[str, Any]]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">on_step_complete</a>() -> Optional[Callable]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">on_step_error</a>() -> Optional[Callable]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">on_step_start</a>() -> Optional[Callable]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">on_workflow_complete</a>() -> Optional[Callable]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">on_workflow_start</a>() -> Optional[Callable]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">planning_llm</a>() -> Optional[str]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">reasoning</a>() -> bool</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">run</a>(input: str = '', llm: Optional[str] = None, verbose: bool = False, stream: bool = None) -> Dict[str, Any]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">start</a>(input: str = '', **kwargs) -> Dict[str, Any]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">stream</a>() -> bool</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">to_dict</a>() -> Dict[str, Any]</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">verbose</a>() -> bool</code>
* <code title="class AgentFlow">AgentFlow.<a href="./src/praisonai-agents/praisonaiagents/workflows/workflows.py">verbose</a>(value: bool)</code>
* <code title="class AgentOSProtocol">AgentOSProtocol.<a href="./src/praisonai-agents/praisonaiagents/app/protocols.py">get_app</a>() -> Any</code>
* <code title="class AgentOSProtocol">AgentOSProtocol.<a href="./src/praisonai-agents/praisonaiagents/app/protocols.py">serve</a>(host: Optional[str] = None, port: Optional[int] = None, reload: bool = False, **kwargs: Any) -> None</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">add_task</a>(task)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">aexecute_task</a>(task_id)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">append_to_state</a>(key: str, value: Any, max_length: Optional[int] = None) -> List[Any]</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">arun_all_tasks</a>()</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">arun_task</a>(task_id)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">astart</a>(content = None, return_dict = False, **kwargs)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">clean_json_output</a>(output: str) -> str</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">clear_state</a>() -> None</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">context_manager</a>()</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">current_plan</a>()</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">default_completion_checker</a>(task, agent_output)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">delete_state</a>(key: str) -> bool</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">display_token_usage</a>()</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">execute_task</a>(task_id)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_agent_details</a>(agent_name)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_all_state</a>() -> Dict[str, Any]</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_all_tasks_status</a>()</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_detailed_token_report</a>() -> Dict[str, Any]</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_plan_markdown</a>() -> str</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_state</a>(key: str, default: Any = None) -> Any</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_task_details</a>(task_id)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_task_result</a>(task_id)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_task_status</a>(task_id)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_todo_markdown</a>() -> str</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">get_token_usage_summary</a>() -> Dict[str, Any]</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">has_state</a>(key: str) -> bool</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">increment_state</a>(key: str, amount: float = 1, default: float = 0) -> float</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">launch</a>(path: str = '/agents', port: int = 8000, host: str = '0.0.0.0', debug: bool = False, protocol: str = 'http')</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">restore_session_state</a>(session_id: str) -> bool</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">run</a>(content = None, return_dict = False, **kwargs)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">run_all_tasks</a>()</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">run_task</a>(task_id)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">save_output_to_file</a>(task, task_output)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">save_session_state</a>(session_id: str, include_memory: bool = True) -> None</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">set_state</a>(key: str, value: Any) -> None</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">start</a>(content = None, return_dict = False, output = None, **kwargs)</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">todo_list</a>()</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">update_plan_step_status</a>(step_id: str, status: str) -> bool</code>
* <code title="class AgentTeam">AgentTeam.<a href="./src/praisonai-agents/praisonaiagents/agents/agents.py">update_state</a>(updates: Dict) -> None</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/embed.py">aembedding</a>(input: Union[str, List[str]], model: str = 'text-embedding-3-small', dimensions: Optional[int] = None, encoding_format: str = 'float', timeout: float = 600.0, api_key: Optional[str] = None, api_base: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> EmbeddingResult</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/embed.py">aembeddings</a>(input: Union[str, List[str]], model: str = 'text-embedding-3-small', dimensions: Optional[int] = None, encoding_format: str = 'float', timeout: float = 600.0, api_key: Optional[str] = None, api_base: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> EmbeddingResult</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/embed.py">embedding</a>(input: Union[str, List[str]], model: str = 'text-embedding-3-small', dimensions: Optional[int] = None, encoding_format: str = 'float', timeout: float = 600.0, api_key: Optional[str] = None, api_base: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> EmbeddingResult</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/embed.py">embeddings</a>(input: Union[str, List[str]], model: str = 'text-embedding-3-small', dimensions: Optional[int] = None, encoding_format: str = 'float', timeout: float = 600.0, api_key: Optional[str] = None, api_base: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> EmbeddingResult</code>
* <code title="function">praisonaiagents.<a href="./src/praisonai-agents/praisonaiagents/embedding/dimensions.py">get_dimensions</a>(model_name: str) -> int</code>

# Wrapper (praisonai)

Types:
```python
from praisonai import AgentApp, AgentOS, CloudProvider, Deploy, DeployConfig, DeployType, PraisonAI, __version__
```

# CLI

Methods:

* <code title="cli">praisonai <a href="./src/praisonai/praisonai/cli/main.py">--help</a></code>
* <code title="cli">praisonai acp acp-main <a href="./src/praisonai/praisonai/cli/commands/acp.py">--help</a></code>
* <code title="cli">praisonai agents create <a href="./src/praisonai/praisonai/cli/commands/agents.py">--help</a></code>
* <code title="cli">praisonai agents info <a href="./src/praisonai/praisonai/cli/commands/agents.py">--help</a></code>
* <code title="cli">praisonai agents list <a href="./src/praisonai/praisonai/cli/commands/agents.py">--help</a></code>
* <code title="cli">praisonai app app <a href="./src/praisonai/praisonai/cli/commands/app.py">--help</a></code>
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
* <code title="cli">praisonai bot bot-callback <a href="./src/praisonai/praisonai/cli/commands/bot.py">--help</a></code>
* <code title="cli">praisonai bot discord <a href="./src/praisonai/praisonai/cli/commands/bot.py">--help</a></code>
* <code title="cli">praisonai bot slack <a href="./src/praisonai/praisonai/cli/commands/bot.py">--help</a></code>
* <code title="cli">praisonai bot telegram <a href="./src/praisonai/praisonai/cli/commands/bot.py">--help</a></code>
* <code title="cli">praisonai browser browser-callback <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser click <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser navigate <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser open <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser profiles <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser screenshot <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser snapshot <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser status <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
* <code title="cli">praisonai browser type <a href="./src/praisonai/praisonai/cli/commands/browser.py">--help</a></code>
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
* <code title="cli">praisonai eval judge <a href="./src/praisonai/praisonai/cli/commands/eval.py">--help</a></code>
* <code title="cli">praisonai eval list-judges <a href="./src/praisonai/praisonai/cli/commands/eval.py">--help</a></code>
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
* <code title="cli">praisonai loop help <a href="./src/praisonai/praisonai/cli/commands/loop.py">--help</a></code>
* <code title="cli">praisonai loop loop-main <a href="./src/praisonai/praisonai/cli/commands/loop.py">--help</a></code>
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
* <code title="cli">praisonai plugins create <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins disable <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins discover <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins doctor <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins enable <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins info <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins install <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins list <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins plugins-callback <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
* <code title="cli">praisonai plugins remove <a href="./src/praisonai/praisonai/cli/commands/plugins.py">--help</a></code>
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
* <code title="cli">praisonai recipe apply <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe create <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe info <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe install <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe judge <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe list <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe optimize <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe run <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
* <code title="cli">praisonai recipe serve <a href="./src/praisonai/praisonai/cli/commands/recipe.py">--help</a></code>
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
* <code title="cli">praisonai sandbox explain <a href="./src/praisonai/praisonai/cli/commands/sandbox.py">--help</a></code>
* <code title="cli">praisonai sandbox list <a href="./src/praisonai/praisonai/cli/commands/sandbox.py">--help</a></code>
* <code title="cli">praisonai sandbox recreate <a href="./src/praisonai/praisonai/cli/commands/sandbox.py">--help</a></code>
* <code title="cli">praisonai sandbox sandbox-callback <a href="./src/praisonai/praisonai/cli/commands/sandbox.py">--help</a></code>
* <code title="cli">praisonai sandbox status <a href="./src/praisonai/praisonai/cli/commands/sandbox.py">--help</a></code>
* <code title="cli">praisonai schedule delete <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule describe <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule list <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule logs <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule restart <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule schedule-callback <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule start <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule stats <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai schedule stop <a href="./src/praisonai/praisonai/cli/commands/schedule.py">--help</a></code>
* <code title="cli">praisonai serve a2a <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve a2u <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve acp <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve agents <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve docs <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve gateway <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve lsp <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve mcp <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve rag <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve recipe <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve registry <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve scheduler <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve serve-callback <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve start <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve status <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve stop <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve ui <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai serve unified <a href="./src/praisonai/praisonai/cli/commands/serve.py">--help</a></code>
* <code title="cli">praisonai session delete <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session export <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session import <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session list <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session resume <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai session show <a href="./src/praisonai/praisonai/cli/commands/session.py">--help</a></code>
* <code title="cli">praisonai skills check <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai skills create <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
* <code title="cli">praisonai skills eligible <a href="./src/praisonai/praisonai/cli/commands/skills.py">--help</a></code>
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
* <code title="cli">praisonai tools validate <a href="./src/praisonai/praisonai/cli/commands/tools.py">--help</a></code>
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
export { Agent, AgentTeam, Agents, PraisonAIAgents, Router } from "./agent";
export type { AgentTeamConfig, PraisonAIAgentsConfig, SimpleAgentConfig, SimpleRouteConfig, SimpleRouterConfig } from "./agent";
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
export { AutoAgents, AutoTaskConfig, createAutoAgents } from "./auto";
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
export { // LLM-as-Judge
  Judge, AccuracyJudge, CriteriaJudge, EvalResults, EvalSuite, Evaluator, RecipeJudge, accuracyEval, addJudge, addOptimizationRule, containsKeywordsCriterion, createDefaultEvaluator, createEvalResults, createEvaluator, getJudge, getOptimizationRule, lengthCriterion, listJudges, listOptimizationRules, noHarmfulContentCriterion, parseJudgeResponse, performanceEval, relevanceCriterion, reliabilityEval, removeJudge, removeOptimizationRule } from "./eval";
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
export { AgentApp, AgentAppConfig, AgentAppProtocol, AgentOS, AgentOSConfig, AgentOSProtocol, DEFAULT_AGENTOS_CONFIG, mergeConfig } from "./os";
export type { AgentAppOptions, AgentOSOptions } from "./os";
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
  Loop, // Task class
  Task, AgentFlow, Pipeline, Repeat, Workflow, loop, loopPattern, parallel, repeat, repeatPattern, route } from "./workflows";
export type { LoopConfig, LoopResult, RepeatConfig, RepeatContext, RepeatResult, StepContextConfig, StepExecutionConfig, StepOutputConfig, StepResult, StepRoutingConfig, TaskConfig, WorkflowContext } from "./workflows";
export { createWorkflowFromYAML, loadWorkflowFromFile, parseYAMLWorkflow, validateWorkflowDefinition } from "./workflows/yaml-parser";
```

# Optional Plugins

External tools are available via `praisonai-tools` package:

```bash
pip install praisonai-tools
```

See [PraisonAI-tools](https://github.com/MervinPraison/PraisonAI-tools) for available tools.
