"""CodeAgent - Code generation, execution, review, and refactoring with sandboxing."""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
import asyncio
import logging


@dataclass
class CodeConfig:
    """Configuration for CodeAgent.
    
    Attributes:
        sandbox: Enable sandboxed execution (default: True for safety)
        timeout: Execution timeout in seconds
        allowed_languages: List of allowed programming languages
        max_output_length: Maximum output length in characters
        working_directory: Working directory for code execution
        environment: Environment variables for execution
    """
    sandbox: bool = True
    timeout: int = 30
    allowed_languages: List[str] = field(default_factory=lambda: ["python"])
    max_output_length: int = 10000
    working_directory: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class CodeAgent:
    """Agent for code generation, execution, review, and refactoring.
    
    This agent provides capabilities for:
    - Generating code from natural language descriptions
    - Executing code in a sandboxed environment
    - Reviewing code for issues and improvements
    - Refactoring and fixing code
    - Explaining code functionality
    
    Example:
        ```python
        from praisonaiagents import CodeAgent
        
        agent = CodeAgent(name="Coder")
        
        # Generate code
        code = agent.generate("Write a function to calculate fibonacci")
        
        # Execute code
        result = agent.execute("print('Hello, World!')")
        
        # Review code
        review = agent.review(code)
        ```
    """
    
    def __init__(
        self,
        name: str = "CodeAgent",
        llm: Optional[str] = None,
        code: Optional[Union[bool, Dict, CodeConfig]] = None,
        instructions: Optional[str] = None,
        verbose: bool = True,
        **kwargs
    ):
        """Initialize CodeAgent.
        
        Args:
            name: Agent name
            llm: LLM model (default: gpt-4o-mini)
            code: Code configuration (bool, dict, or CodeConfig)
            instructions: System instructions
            verbose: Enable verbose output
            **kwargs: Additional arguments
        """
        self.name = name
        self.llm = llm or "gpt-4o-mini"
        self.instructions = instructions
        self.verbose = verbose
        
        # Resolve configuration (Precedence Ladder)
        if code is None or code is True:
            self._code_config = CodeConfig()
        elif isinstance(code, dict):
            self._code_config = CodeConfig(**code)
        elif isinstance(code, CodeConfig):
            self._code_config = code
        else:
            self._code_config = CodeConfig()
        
        # Lazy-loaded dependencies
        self._litellm = None
        self._console = None
        
        # Configure logging
        self._logger = logging.getLogger(f"CodeAgent.{name}")
        if not verbose:
            self._logger.setLevel(logging.WARNING)
    
    @property
    def console(self):
        """Lazy load Rich console."""
        if self._console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                pass
        return self._console
    
    @property
    def litellm(self):
        """Lazy load litellm."""
        if self._litellm is None:
            try:
                import litellm
                self._litellm = litellm
            except ImportError:
                raise ImportError(
                    "litellm required for CodeAgent. "
                    "Install with: pip install litellm"
                )
        return self._litellm
    
    def _log(self, message: str, style: str = ""):
        """Log message if verbose."""
        if self.verbose and self.console:
            self.console.print(f"[{style}]{message}[/{style}]" if style else message)
    
    # =========================================================================
    # Code Generation Methods
    # =========================================================================
    
    def generate(self, prompt: str, language: str = "python", **kwargs) -> str:
        """Generate code from natural language description.
        
        Args:
            prompt: Natural language description of desired code
            language: Target programming language
            **kwargs: Additional arguments for LLM
            
        Returns:
            Generated code as string
        """
        self._log(f"Generating {language} code...", "cyan")
        
        system_prompt = f"""You are an expert {language} programmer.
Generate clean, well-documented, production-ready code.
Only output the code, no explanations unless asked.
Follow best practices and coding standards."""
        
        if self.instructions:
            system_prompt += f"\n\nAdditional instructions: {self.instructions}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        response = self.litellm.completion(
            model=kwargs.get("model", self.llm),
            messages=messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        )
        
        code = response.choices[0].message.content
        self._log("Code generated successfully", "green")
        return code
    
    def generate_code(self, prompt: str, language: str = "python", **kwargs) -> str:
        """Alias for generate() method."""
        return self.generate(prompt, language, **kwargs)
    
    async def agenerate(self, prompt: str, language: str = "python", **kwargs) -> str:
        """Generate code asynchronously.
        
        Args:
            prompt: Natural language description
            language: Target programming language
            **kwargs: Additional arguments
            
        Returns:
            Generated code as string
        """
        self._log(f"Generating {language} code (async)...", "cyan")
        
        system_prompt = f"""You are an expert {language} programmer.
Generate clean, well-documented, production-ready code.
Only output the code, no explanations unless asked.
Follow best practices and coding standards."""
        
        if self.instructions:
            system_prompt += f"\n\nAdditional instructions: {self.instructions}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.litellm.acompletion(
            model=kwargs.get("model", self.llm),
            messages=messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        )
        
        code = response.choices[0].message.content
        self._log("Code generated successfully", "green")
        return code
    
    # =========================================================================
    # Code Execution Methods
    # =========================================================================
    
    def execute(self, code: str, language: str = "python", **kwargs) -> Dict[str, Any]:
        """Execute code in sandboxed environment.
        
        Args:
            code: Code to execute
            language: Programming language
            **kwargs: Additional execution options
            
        Returns:
            Dictionary with stdout, stderr, return_code, and execution_time
        """
        if language not in self._code_config.allowed_languages:
            return {
                "stdout": "",
                "stderr": f"Language '{language}' not allowed. Allowed: {self._code_config.allowed_languages}",
                "return_code": 1,
                "execution_time": 0
            }
        
        self._log(f"Executing {language} code...", "cyan")
        
        if language == "python":
            return self._execute_python(code, **kwargs)
        else:
            return {
                "stdout": "",
                "stderr": f"Execution for '{language}' not implemented",
                "return_code": 1,
                "execution_time": 0
            }
    
    def execute_code(self, code: str, language: str = "python", **kwargs) -> Dict[str, Any]:
        """Alias for execute() method."""
        return self.execute(code, language, **kwargs)
    
    def _execute_python(self, code: str, **kwargs) -> Dict[str, Any]:
        """Execute Python code."""
        import subprocess
        import time
        import tempfile
        import os
        
        start_time = time.time()
        
        # Write code to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Execute in subprocess (basic sandboxing)
            env = os.environ.copy()
            env.update(self._code_config.environment)
            
            result = subprocess.run(
                ["python", temp_file],
                capture_output=True,
                text=True,
                timeout=self._code_config.timeout,
                cwd=self._code_config.working_directory,
                env=env
            )
            
            execution_time = time.time() - start_time
            
            stdout = result.stdout[:self._code_config.max_output_length]
            stderr = result.stderr[:self._code_config.max_output_length]
            
            self._log(f"Execution completed in {execution_time:.2f}s", "green")
            
            return {
                "stdout": stdout,
                "stderr": stderr,
                "return_code": result.returncode,
                "execution_time": execution_time
            }
            
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {self._code_config.timeout}s",
                "return_code": -1,
                "execution_time": self._code_config.timeout
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "execution_time": time.time() - start_time
            }
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file)
            except:
                pass
    
    async def aexecute(self, code: str, language: str = "python", **kwargs) -> Dict[str, Any]:
        """Execute code asynchronously.
        
        Args:
            code: Code to execute
            language: Programming language
            **kwargs: Additional options
            
        Returns:
            Execution result dictionary
        """
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.execute(code, language, **kwargs))
    
    # =========================================================================
    # Code Review Methods
    # =========================================================================
    
    def review(self, code: str, language: str = "python", **kwargs) -> str:
        """Review code for issues, bugs, and improvements.
        
        Args:
            code: Code to review
            language: Programming language
            **kwargs: Additional arguments
            
        Returns:
            Review feedback as string
        """
        self._log("Reviewing code...", "cyan")
        
        system_prompt = f"""You are an expert {language} code reviewer.
Analyze the code for:
1. Bugs and potential issues
2. Security vulnerabilities
3. Performance problems
4. Code style and best practices
5. Suggestions for improvement

Provide clear, actionable feedback."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Review this {language} code:\n\n```{language}\n{code}\n```"}
        ]
        
        response = self.litellm.completion(
            model=kwargs.get("model", self.llm),
            messages=messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        )
        
        review = response.choices[0].message.content
        self._log("Review completed", "green")
        return review
    
    # =========================================================================
    # Code Explanation Methods
    # =========================================================================
    
    def explain(self, code: str, language: str = "python", **kwargs) -> str:
        """Explain what code does in plain language.
        
        Args:
            code: Code to explain
            language: Programming language
            **kwargs: Additional arguments
            
        Returns:
            Explanation as string
        """
        self._log("Explaining code...", "cyan")
        
        system_prompt = f"""You are an expert {language} programmer and teacher.
Explain the code in clear, simple terms that anyone can understand.
Include:
1. What the code does overall
2. Key components and their purpose
3. How data flows through the code
4. Any important patterns or techniques used"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Explain this {language} code:\n\n```{language}\n{code}\n```"}
        ]
        
        response = self.litellm.completion(
            model=kwargs.get("model", self.llm),
            messages=messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        )
        
        explanation = response.choices[0].message.content
        self._log("Explanation completed", "green")
        return explanation
    
    # =========================================================================
    # Code Refactoring Methods
    # =========================================================================
    
    def refactor(self, code: str, instructions: str = "", language: str = "python", **kwargs) -> str:
        """Refactor code to improve quality.
        
        Args:
            code: Code to refactor
            instructions: Specific refactoring instructions
            language: Programming language
            **kwargs: Additional arguments
            
        Returns:
            Refactored code as string
        """
        self._log("Refactoring code...", "cyan")
        
        system_prompt = f"""You are an expert {language} programmer.
Refactor the code to improve:
1. Readability and maintainability
2. Performance where possible
3. Code organization
4. Following best practices

Only output the refactored code."""
        
        user_prompt = f"Refactor this {language} code:\n\n```{language}\n{code}\n```"
        if instructions:
            user_prompt += f"\n\nSpecific instructions: {instructions}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.litellm.completion(
            model=kwargs.get("model", self.llm),
            messages=messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        )
        
        refactored = response.choices[0].message.content
        self._log("Refactoring completed", "green")
        return refactored
    
    # =========================================================================
    # Bug Fixing Methods
    # =========================================================================
    
    def fix(self, code: str, error: str = "", language: str = "python", **kwargs) -> str:
        """Fix bugs in code.
        
        Args:
            code: Code with bugs
            error: Error message or description of the bug
            language: Programming language
            **kwargs: Additional arguments
            
        Returns:
            Fixed code as string
        """
        self._log("Fixing code...", "cyan")
        
        system_prompt = f"""You are an expert {language} debugger.
Fix the bugs in the code. Only output the fixed code.
Ensure the fix:
1. Addresses the root cause
2. Doesn't introduce new bugs
3. Maintains existing functionality"""
        
        user_prompt = f"Fix this {language} code:\n\n```{language}\n{code}\n```"
        if error:
            user_prompt += f"\n\nError/Bug description: {error}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.litellm.completion(
            model=kwargs.get("model", self.llm),
            messages=messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        )
        
        fixed = response.choices[0].message.content
        self._log("Fix completed", "green")
        return fixed
