"""
Example External Harness using PreparedTurnContext.

This module demonstrates how external harnesses (plugins, managed backends,
CLI backends, etc.) can use the PreparedTurnContext pattern for consistent
runtime execution across different execution environments.

This serves as an example implementation for the acceptance criteria:
"At least one external harness uses the same plan object."
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .turn_context import (
    PreparedTurnContext,
    TurnRuntimeProtocol,
    RuntimeMode,
)
from .context_builder import default_context_builder
from ..streaming.events import StreamEvent, StreamEventType

if TYPE_CHECKING:
    from ..agent.protocols import AgentProtocol

logger = logging.getLogger(__name__)


class PluginHarnessRuntime:
    """
    Example plugin harness that uses PreparedTurnContext.
    
    This demonstrates how external harnesses can standardize on the
    PreparedTurnContext pattern instead of implementing their own
    scattered preparation logic.
    
    Before (scattered preparation):
    - Plugin gathers tools from agent
    - Plugin builds system prompt
    - Plugin manages streaming separately
    - Plugin handles context differently than native runtime
    
    After (unified with PreparedTurnContext):
    - Plugin receives prepared context
    - Same context used by native runtime
    - Consistent tool schemas, transcript, delivery channels
    - Enables consistent metrics and tracing
    """
    
    def __init__(self, plugin_config: Optional[Dict[str, Any]] = None):
        self.config = plugin_config or {}
        self.metrics = {}
        self._supported_modes = [RuntimeMode.SYNC, RuntimeMode.ASYNC, RuntimeMode.STREAM]

    async def run_turn(self, context: PreparedTurnContext) -> str:
        """
        Execute turn using plugin-specific logic with prepared context.
        
        This method demonstrates how an external harness uses the
        standardized PreparedTurnContext instead of implementing
        its own preparation logic.
        
        Args:
            context: The prepared turn context from the builder
            
        Returns:
            Plugin-processed response
        """
        start_time = time.time()
        
        try:
            logger.info(
                f"Plugin executing turn {context.correlation.turn_id} "
                f"with {len(context.tools)} tools in {context.runtime_mode.value} mode"
            )
            
            # Use prepared context data instead of rebuilding
            response = await self._execute_with_prepared_data(context)
            
            # Apply plugin-specific processing
            processed_response = await self._apply_plugin_processing(context, response)
            
            # Record metrics using correlation IDs from context
            self._record_metrics(context, start_time, len(processed_response))
            
            return processed_response
            
        except Exception as e:
            logger.error(f"Plugin execution failed for turn {context.correlation.turn_id}: {e}")
            raise

    async def _execute_with_prepared_data(self, context: PreparedTurnContext) -> str:
        """
        Execute using the prepared context data.
        
        This method shows how to use the standardized context components
        instead of re-implementing tool gathering, prompt building, etc.
        """
        # Extract prompt from prepared transcript (no need to rebuild)
        user_messages = [
            msg for msg in context.transcript.messages 
            if msg.get('role') == 'user'
        ]
        prompt = user_messages[-1]['content'] if user_messages else ""
        
        # Use prepared system prompt (no need to rebuild)
        system_prompt = context.transcript.system_prompt or "You are a helpful assistant."
        
        # Use prepared tool schemas (normalized format)
        available_tools = [
            f"- {tool.name}: {tool.description}" 
            for tool in context.tools
        ]
        tools_text = "\n".join(available_tools) if available_tools else "No tools available"
        
        # Use prepared model configuration
        model_id = context.model_ref.model_id
        temperature = context.model_ref.temperature or 0.7
        
        # Plugin-specific execution (simulated)
        plugin_response = f"""Plugin Response (Model: {model_id}, Temp: {temperature}):

User: {prompt}

System: {system_prompt}

Available Tools:
{tools_text}

Processing with plugin harness...
Response: I understand your request and would process it using the plugin infrastructure."""
        
        # Handle streaming if enabled in prepared delivery channels
        if context.delivery.has_streaming():
            return await self._stream_response(context, plugin_response)
        else:
            return plugin_response

    async def _stream_response(self, context: PreparedTurnContext, response: str) -> str:
        """
        Handle streaming using prepared delivery channels.
        
        Demonstrates using the prepared streaming configuration
        instead of setting up streaming from scratch.
        """
        if context.delivery.stream_emitter:
            # Use prepared stream emitter
            for chunk in response.split():
                await context.delivery.stream_emitter.emit_async(
                    StreamEvent(type=StreamEventType.DELTA_TEXT, content=chunk + " ")
                )
                await asyncio.sleep(0.01)  # Simulate streaming delay
        
        return response

    async def _apply_plugin_processing(
        self, 
        context: PreparedTurnContext, 
        response: str
    ) -> str:
        """
        Apply plugin-specific post-processing.
        
        This demonstrates how plugins can add their own processing
        while still using the standardized context pattern.
        """
        # Plugin-specific processing example
        if self.config.get('add_metadata', True):
            metadata = f"\n\n[Plugin Metadata: Session={context.correlation.session_id}, Turn={context.correlation.turn_id}]"
            response += metadata
        
        if self.config.get('apply_filters', False):
            # Apply content filters, transformations, etc.
            response = response.replace("error", "issue")  # Example filter
        
        return response

    def _record_metrics(self, context: PreparedTurnContext, start_time: float, response_length: int):
        """
        Record metrics using context correlation IDs.
        
        Demonstrates consistent metrics collection across harness types
        using the standardized context identifiers.
        """
        execution_time = time.time() - start_time
        
        # Use correlation IDs for consistent metrics
        session_id = context.correlation.session_id
        turn_id = context.correlation.turn_id
        
        # Record metrics
        self.metrics[turn_id] = {
            'session_id': session_id,
            'execution_time_ms': execution_time * 1000,
            'response_length': response_length,
            'model_used': context.model_ref.model_id,
            'tools_count': len(context.tools),
            'runtime_mode': context.runtime_mode.value,
            'timestamp': time.time()
        }
        
        logger.debug(
            f"Plugin metrics recorded: {execution_time:.3f}s, "
            f"{response_length} chars, {len(context.tools)} tools"
        )

    def supports_runtime_mode(self, mode: RuntimeMode) -> bool:
        """Check if this plugin supports the given runtime mode."""
        return mode in self._supported_modes

    def get_supported_modes(self) -> List[RuntimeMode]:
        """Get all supported runtime modes."""
        return self._supported_modes.copy()

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics."""
        return self.metrics.copy()


class CLIBackendHarness:
    """
    Example CLI backend harness using PreparedTurnContext.
    
    This demonstrates how CLI backends can use the same prepared
    context as the native runtime, eliminating duplication in
    tool assembly and message building.
    """
    
    def __init__(self, cli_config: Optional[Dict[str, Any]] = None):
        self.config = cli_config or {}
        self._supported_modes = [RuntimeMode.SYNC, RuntimeMode.ASYNC]

    async def run_turn(self, context: PreparedTurnContext) -> str:
        """Execute turn via CLI backend using prepared context."""
        logger.info(f"CLI backend executing turn {context.correlation.turn_id}")
        
        # Convert prepared context to CLI command
        cli_command = self._build_cli_command(context)
        
        # Execute CLI command (simulated)
        result = await self._execute_cli_command(cli_command)
        
        return f"CLI Backend Result: {result}"

    def _build_cli_command(self, context: PreparedTurnContext) -> Dict[str, Any]:
        """
        Build CLI command from prepared context.
        
        Shows how prepared context eliminates the need for CLI backends
        to implement their own tool gathering and prompt building logic.
        """
        # Extract prompt from prepared transcript
        user_messages = [msg for msg in context.transcript.messages if msg.get('role') == 'user']
        prompt = user_messages[-1]['content'] if user_messages else ""
        
        # Use prepared model reference
        model_config = context.model_ref.model_config.copy()
        model_config['model'] = context.model_ref.model_id
        
        # Use prepared tool schemas (convert to CLI format)
        tools = [
            {
                'name': tool.name,
                'description': tool.description,
                'source_type': tool.source_type
            }
            for tool in context.tools
        ]
        
        return {
            'prompt': prompt,
            'system_prompt': context.transcript.system_prompt,
            'model_config': model_config,
            'tools': tools,
            'session_id': context.correlation.session_id,
            'turn_id': context.correlation.turn_id
        }

    async def _execute_cli_command(self, command: Dict[str, Any]) -> str:
        """Execute the CLI command (simulated)."""
        # Simulate CLI execution delay
        await asyncio.sleep(0.1)
        
        return f"Processed '{command['prompt']}' with {len(command['tools'])} tools using {command['model_config']['model']}"

    def supports_runtime_mode(self, mode: RuntimeMode) -> bool:
        """Check if CLI backend supports the runtime mode."""
        return mode in self._supported_modes

    def get_supported_modes(self) -> List[RuntimeMode]:
        """Get supported runtime modes."""
        return self._supported_modes.copy()


# Example integration function
async def demonstrate_harness_integration():
    """
    Demonstrate how external harnesses use PreparedTurnContext.
    
    This function shows the complete flow from context preparation
    to execution across different harness types, proving that the
    same plan object can be used consistently.
    """
    print("Demonstrating PreparedTurnContext with external harnesses...\n")
    
    # Mock agent
    class MockAgent:
        def __init__(self):
            self.name = "DemoAgent"
            self.model = "gpt-3.5-turbo" 
            self.role = "assistant"
            self.goal = "demonstrate harnesses"
            self.tools = []
            self.chat_history = []
            self.use_system_prompt = True
        
        def _build_system_prompt(self):
            return f"You are {self.role}. Your goal: {self.goal}"

    agent = MockAgent()
    
    # Prepare single context (eliminates scattered preparation)
    context = default_context_builder.build_context(
        agent=agent,
        prompt="Demonstrate harness integration",
        temperature=0.8,
        session_id="demo-session"
    )
    
    print(f"Prepared context: {context.to_dict()}\n")
    
    # Execute with different harnesses using same context
    harnesses = [
        ("Plugin Harness", PluginHarnessRuntime({'add_metadata': True})),
        ("CLI Backend", CLIBackendHarness({'cli_mode': 'demo'}))
    ]
    
    results = {}
    for name, harness in harnesses:
        if harness.supports_runtime_mode(context.runtime_mode):
            print(f"Executing with {name}...")
            try:
                result = await harness.run_turn(context)
                results[name] = result[:100] + "..." if len(result) > 100 else result
                print(f"✓ {name} completed\n")
            except Exception as e:
                print(f"✗ {name} failed: {e}\n")
                results[name] = f"Error: {e}"
        else:
            print(f"✗ {name} doesn't support {context.runtime_mode.value} mode\n")
            results[name] = f"Unsupported mode: {context.runtime_mode.value}"
    
    # Display results
    print("Results:")
    for name, result in results.items():
        print(f"{name}: {result}")
    
    print(f"\n🎉 Demonstrated PreparedTurnContext with {len(harnesses)} external harnesses!")
    return results


if __name__ == "__main__":
    # Run the demonstration
    asyncio.run(demonstrate_harness_integration())