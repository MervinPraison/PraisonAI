import logging
import json
import time
from typing import List, Optional, Any, Dict, Union, Literal
from rich.console import Console
from rich.live import Live
from ..main import (
    display_error,
    display_tool_call,
    display_instruction,
    display_interaction,
    display_generating,
    display_self_reflection,
    ReflectionOutput,
    client,
    error_logs
)

class Agent:
    def _generate_tool_definition(self, function_name):
        """
        Generate a tool definition from a function name by inspecting the function.
        """
        # First try to get the tool definition if it exists
        tool_def_name = f"{function_name}_definition"
        tool_def = globals().get(tool_def_name)
        if not tool_def:
            import __main__
            tool_def = getattr(__main__, tool_def_name, None)
        
        if tool_def:
            return tool_def

        # If no definition exists, try to generate one from the function
        func = globals().get(function_name)
        if not func:
            import __main__
            func = getattr(__main__, function_name, None)

        if not func or not callable(func):
            return None

        import inspect
        sig = inspect.signature(func)
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Parse docstring for parameter descriptions
        docstring = inspect.getdoc(func)
        param_descriptions = {}
        if docstring:
            import re
            param_section = re.split(r'\s*Args:\s*', docstring)
            if len(param_section) > 1:
                param_lines = param_section[1].split('\n')
                for line in param_lines:
                    line = line.strip()
                    if line and ':' in line:
                        param_name, param_desc = line.split(':', 1)
                        param_descriptions[param_name.strip()] = param_desc.strip()

        for name, param in sig.parameters.items():
            param_type = "string"  # Default type
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == list:
                    param_type = "array"
                elif param.annotation == dict:
                    param_type = "object"
            
            param_info = {"type": param_type}
            if name in param_descriptions:
                param_info["description"] = param_descriptions[name]
            
            parameters["properties"][name] = param_info
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(name)

        # Extract description from docstring
        description = docstring.split('\n')[0] if docstring else f"Function {function_name}"

        return {
            "type": "function",
            "function": {
                "name": function_name,
                "description": description,
                "parameters": parameters
            }
        }

    def __init__(
        self,
        name: str,
        role: str,
        goal: str,
        backstory: str,
        llm: Optional[Union[str, Any]] = "gpt-4o-mini",
        tools: Optional[List[Any]] = None,
        function_calling_llm: Optional[Any] = None,
        max_iter: int = 20,
        max_rpm: Optional[int] = None,
        max_execution_time: Optional[int] = None,
        memory: bool = True,
        verbose: bool = False,
        allow_delegation: bool = False,
        step_callback: Optional[Any] = None,
        cache: bool = True,
        system_template: Optional[str] = None,
        prompt_template: Optional[str] = None,
        response_template: Optional[str] = None,
        allow_code_execution: Optional[bool] = False,
        max_retry_limit: int = 2,
        respect_context_window: bool = True,
        code_execution_mode: Literal["safe", "unsafe"] = "safe",
        embedder_config: Optional[Dict[str, Any]] = None,
        knowledge_sources: Optional[List[Any]] = None,
        use_system_prompt: Optional[bool] = True,
        markdown: bool = True,
        self_reflect: bool = True,
        max_reflection_iter: int = 3
    ):
        self.name = name
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.llm = llm
        self.tools = tools if tools else []  # Store original tools
        self.function_calling_llm = function_calling_llm
        self.max_iter = max_iter
        self.max_rpm = max_rpm
        self.max_execution_time = max_execution_time
        self.memory = memory
        self.verbose = verbose
        self.allow_delegation = allow_delegation
        self.step_callback = step_callback
        self.cache = cache
        self.system_template = system_template
        self.prompt_template = prompt_template
        self.response_template = response_template
        self.allow_code_execution = allow_code_execution
        self.max_retry_limit = max_retry_limit
        self.respect_context_window = respect_context_window
        self.code_execution_mode = code_execution_mode
        self.embedder_config = embedder_config
        self.knowledge_sources = knowledge_sources
        self.use_system_prompt = use_system_prompt
        self.chat_history = []
        self.markdown = markdown
        self.self_reflect = self_reflect
        self.max_reflection_iter = max_reflection_iter

    def execute_tool(self, function_name, arguments):
        """
        Execute a tool dynamically based on the function name and arguments.
        """
        logging.debug(f"{self.name} executing tool {function_name} with arguments: {arguments}")

        # Try to get the function from globals first
        func = globals().get(function_name)
        if not func:
            # Then try to get from the main module
            import __main__
            func = getattr(__main__, function_name, None)

        if func and callable(func):
            try:
                return func(**arguments)
            except Exception as e:
                return {"error": str(e)}
        
        return {"error": f"Tool '{function_name}' is not callable"}

    def clear_history(self):
        self.chat_history = []

    def __str__(self):
        return f"Agent(name='{self.name}', role='{self.role}', goal='{self.goal}')"

    def _chat_completion(self, messages, temperature=0.2, tools=None, stream=True):
        console = Console()
        start_time = time.time()
        logging.debug(f"{self.name} sending messages to LLM: {messages}")

        formatted_tools = []
        if tools is None:
            tools = self.tools
        if tools:
            for tool in tools:
                if isinstance(tool, str):
                    # Generate tool definition for string tool names
                    tool_def = self._generate_tool_definition(tool)
                    if tool_def:
                        formatted_tools.append(tool_def)
                    else:
                        logging.warning(f"Could not generate definition for tool: {tool}")
                elif isinstance(tool, dict):
                    formatted_tools.append(tool)
                elif hasattr(tool, "to_openai_tool"):
                    formatted_tools.append(tool.to_openai_tool())
                elif callable(tool):
                    formatted_tools.append(self._generate_tool_definition(tool.__name__))
                else:
                    logging.warning(f"Tool {tool} not recognized")

        try:
            initial_response = client.chat.completions.create(
                model=self.llm,
                messages=messages,
                temperature=temperature,
                tools=formatted_tools if formatted_tools else None,
                stream=False
            )

            tool_calls = getattr(initial_response.choices[0].message, 'tool_calls', None)

            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": initial_response.choices[0].message.content,
                    "tool_calls": tool_calls
                })

                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)

                    if self.verbose:
                        display_tool_call(f"Agent {self.name} is calling function '{function_name}' with arguments: {arguments}")

                    tool_result = self.execute_tool(function_name, arguments)
                    results_str = json.dumps(tool_result) if tool_result else "Function returned an empty output"

                    if self.verbose:
                        display_tool_call(f"Function '{function_name}' returned: {results_str}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": results_str
                    })

            if stream:
                response_stream = client.chat.completions.create(
                    model=self.llm,
                    messages=messages,
                    temperature=temperature,
                    stream=True
                )
                full_response_text = ""
                with Live(display_generating("", start_time), refresh_per_second=4) as live:
                    for chunk in response_stream:
                        if chunk.choices[0].delta.content:
                            full_response_text += chunk.choices[0].delta.content
                            live.update(display_generating(full_response_text, start_time))

                final_response = client.chat.completions.create(
                    model=self.llm,
                    messages=messages,
                    temperature=temperature,
                    stream=False
                )
                return final_response
            else:
                if tool_calls:
                    final_response = client.chat.completions.create(
                        model=self.llm,
                        messages=messages,
                        temperature=temperature,
                        stream=False
                    )
                    return final_response
                else:
                    return initial_response

        except Exception as e:
            display_error(f"Error in chat completion: {e}")
            return None

    def chat(self, prompt, temperature=0.2, tools=None, output_json=None):
        if self.use_system_prompt:
            system_prompt = f"""{self.backstory}\n
            Your Role: {self.role}\n
            Your Goal: {self.goal}
            """
        else:
            system_prompt = None
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(self.chat_history)
        messages.append({"role": "user", "content": prompt})

        final_response_text = None
        reflection_count = 0
        start_time = time.time()

        while True:
            try:
                if self.verbose:
                    display_instruction(f"Agent {self.name} is processing prompt: {prompt}")

                response = self._chat_completion(messages, temperature=temperature, tools=tools if tools else None)
                if not response:
                    return None
                    
                tool_calls = getattr(response.choices[0].message, 'tool_calls', None)

                if tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": response.choices[0].message.content,
                        "tool_calls": tool_calls
                    })
                    
                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)

                        if self.verbose:
                            display_tool_call(f"Agent {self.name} is calling function '{function_name}' with arguments: {arguments}")

                        tool_result = self.execute_tool(function_name, arguments)

                        if tool_result:
                            if self.verbose:
                                display_tool_call(f"Function '{function_name}' returned: {tool_result}")
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(tool_result)
                            })
                        else:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": "Function returned an empty output"
                            })
                        
                    response = self._chat_completion(messages, temperature=temperature)
                    if not response:
                        return None
                    response_text = response.choices[0].message.content.strip()
                else:
                    response_text = response.choices[0].message.content.strip()

                if not self.self_reflect:
                    self.chat_history.append({"role": "user", "content": prompt})
                    self.chat_history.append({"role": "assistant", "content": response_text})
                    if self.verbose:
                        logging.info(f"Agent {self.name} final response: {response_text}")
                    display_interaction(prompt, response_text, markdown=self.markdown, generation_time=time.time() - start_time)
                    return response_text

                reflection_prompt = f"""
                Reflect on your previous response: '{response_text}'.
                Identify any flaws, improvements, or actions.
                Provide a "satisfactory" status ('yes' or 'no').
                Output MUST be JSON with 'reflection' and 'satisfactory'.
                """
                logging.debug(f"{self.name} reflection attempt {reflection_count+1}, sending prompt: {reflection_prompt}")
                messages.append({"role": "user", "content": reflection_prompt})

                try:
                    reflection_response = client.beta.chat.completions.parse(
                        model=self.llm,
                        messages=messages,
                        temperature=temperature,
                        response_format=ReflectionOutput
                    )

                    reflection_output = reflection_response.choices[0].message.parsed

                    if self.verbose:
                        display_self_reflection(f"Agent {self.name} self reflection: reflection='{reflection_output.reflection}' satisfactory='{reflection_output.satisfactory}'")

                    messages.append({"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"})

                    if reflection_output.satisfactory == "yes":
                        if self.verbose:
                            display_self_reflection("Agent marked the response as satisfactory")
                        self.chat_history.append({"role": "assistant", "content": response_text})
                        display_interaction(prompt, response_text, markdown=self.markdown, generation_time=time.time() - start_time)
                        return response_text

                    logging.debug(f"{self.name} reflection not satisfactory, requesting regeneration.")
                    messages.append({"role": "user", "content": "Now regenerate your response using the reflection you made"})
                    response = self._chat_completion(messages, temperature=temperature, tools=None, stream=True)
                    response_text = response.choices[0].message.content.strip()
                except Exception as e:
                    display_error(f"Error in parsing self-reflection json {e}. Retrying")
                    logging.error("Reflection parsing failed.", exc_info=True)
                    messages.append({"role": "assistant", "content": f"Self Reflection failed."})
                
                reflection_count += 1

                self.chat_history.append({"role": "user", "content": prompt})
                self.chat_history.append({"role": "assistant", "content": response_text})

                if self.verbose:
                    logging.info(f"Agent {self.name} final response: {response_text}")
                display_interaction(prompt, response_text, markdown=self.markdown, generation_time=time.time() - start_time)
                return response_text
            except Exception as e:
                display_error(f"Error in chat: {e}")
                return None 