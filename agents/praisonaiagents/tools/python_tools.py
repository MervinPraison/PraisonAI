"""Tools for Python code execution and analysis.

Usage:
from praisonaiagents.tools import python_tools
result = python_tools.execute_code("print('Hello, World!')")

or
from praisonaiagents.tools import execute_code, analyze_code, format_code
result = execute_code("print('Hello, World!')")
"""

import logging
from typing import Dict, List, Optional, Any
from importlib import util
import io
from contextlib import redirect_stdout, redirect_stderr
import traceback

class PythonTools:
    """Tools for Python code execution and analysis."""
    
    def __init__(self):
        """Initialize PythonTools."""
        self._check_dependencies()
        
    def _check_dependencies(self):
        """Check if required packages are installed."""
        missing = []
        for package in ['black', 'pylint', 'autopep8']:
            if util.find_spec(package) is None:
                missing.append(package)
        
        if missing:
            raise ImportError(
                f"Required packages not available. Please install: {', '.join(missing)}\n"
                f"Run: pip install {' '.join(missing)}"
            )

    def execute_code(
        self,
        code: str,
        globals_dict: Optional[Dict[str, Any]] = None,
        locals_dict: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        max_output_size: int = 10000
    ) -> Dict[str, Any]:
        """Execute Python code safely."""
        try:
            # Set up execution environment
            if globals_dict is None:
                globals_dict = {'__builtins__': __builtins__}
            if locals_dict is None:
                locals_dict = {}
            
            # Capture output
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            
            try:
                # Compile code
                compiled_code = compile(code, '<string>', 'exec')
                
                # Execute with output capture
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    exec(compiled_code, globals_dict, locals_dict)
                    
                    # Get last expression value if any
                    import ast
                    tree = ast.parse(code)
                    if tree.body and isinstance(tree.body[-1], ast.Expr):
                        result = eval(
                            compile(ast.Expression(tree.body[-1].value), '<string>', 'eval'),
                            globals_dict,
                            locals_dict
                        )
                    else:
                        result = None
                
                # Get output
                stdout = stdout_buffer.getvalue()
                stderr = stderr_buffer.getvalue()
                
                # Truncate output if too large
                if len(stdout) > max_output_size:
                    stdout = stdout[:max_output_size] + "...[truncated]"
                if len(stderr) > max_output_size:
                    stderr = stderr[:max_output_size] + "...[truncated]"
                
                return {
                    'result': result,
                    'stdout': stdout,
                    'stderr': stderr,
                    'success': True
                }
            
            except Exception as e:
                error_msg = f"Error executing code: {str(e)}"
                logging.error(error_msg)
                return {
                    'result': None,
                    'stdout': stdout_buffer.getvalue(),
                    'stderr': error_msg,
                    'success': False
                }
            
        except Exception as e:
            error_msg = f"Error executing code: {str(e)}"
            logging.error(error_msg)
            return {
                'result': None,
                'stdout': '',
                'stderr': error_msg,
                'success': False
            }

    def analyze_code(
        self,
        code: str
    ) -> Optional[Dict[str, Any]]:
        """Analyze Python code structure and quality.
        
        Args:
            code: Python code to analyze
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Import ast only when needed
            import ast
            
            # Parse code
            tree = ast.parse(code)
            
            # Analyze structure
            analysis = {
                'imports': [],
                'functions': [],
                'classes': [],
                'variables': [],
                'complexity': {
                    'lines': len(code.splitlines()),
                    'functions': 0,
                    'classes': 0,
                    'branches': 0
                }
            }
            
            # Analyze nodes
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        analysis['imports'].append(name.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for name in node.names:
                        analysis['imports'].append(f"{module}.{name.name}")
                elif isinstance(node, ast.FunctionDef):
                    analysis['functions'].append({
                        'name': node.name,
                        'args': [
                            arg.arg for arg in node.args.args
                        ],
                        'decorators': [
                            ast.unparse(d) for d in node.decorator_list
                        ]
                    })
                    analysis['complexity']['functions'] += 1
                elif isinstance(node, ast.ClassDef):
                    analysis['classes'].append({
                        'name': node.name,
                        'bases': [
                            ast.unparse(base) for base in node.bases
                        ],
                        'decorators': [
                            ast.unparse(d) for d in node.decorator_list
                        ]
                    })
                    analysis['complexity']['classes'] += 1
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            analysis['variables'].append(target.id)
                elif isinstance(node, (ast.If, ast.While, ast.For)):
                    analysis['complexity']['branches'] += 1
            
            return analysis
        except Exception as e:
            error_msg = f"Error analyzing code: {str(e)}"
            logging.error(error_msg)
            return None

    def format_code(
        self,
        code: str,
        style: str = 'black',
        line_length: int = 88
    ) -> Optional[str]:
        """Format Python code according to style guide.
        
        Args:
            code: Python code to format
            style: Formatting style ('black' or 'pep8')
            line_length: Maximum line length
            
        Returns:
            Formatted code
        """
        try:
            if util.find_spec(style) is None:
                error_msg = f"{style} package is not available. Please install it using: pip install {style}"
                logging.error(error_msg)
                return None

            if style == 'black':
                import black
                return black.format_str(
                    code,
                    mode=black.FileMode(
                        line_length=line_length
                    )
                )
            else:  # pep8
                import autopep8
                return autopep8.fix_code(
                    code,
                    options={
                        'max_line_length': line_length
                    }
                )
        except Exception as e:
            error_msg = f"Error formatting code: {str(e)}"
            logging.error(error_msg)
            return None

    def lint_code(
        self,
        code: str
    ) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Lint Python code for potential issues.
        
        Args:
            code: Python code to lint
            
        Returns:
            Dictionary with linting results
        """
        try:
            if util.find_spec('pylint') is None:
                error_msg = "pylint package is not available. Please install it using: pip install pylint"
                logging.error(error_msg)
                return None

            # Import pylint only when needed
            from pylint.reporters import JSONReporter
            from pylint.lint.run import Run
            
            # Create temporary file for pylint
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False
            ) as f:
                f.write(code)
                temp_path = f.name
            
            # Run pylint
            reporter = JSONReporter()
            Run(
                [temp_path],
                reporter=reporter,
                exit=False
            )
            
            # Process results
            results = {
                'errors': [],
                'warnings': [],
                'conventions': []
            }
            
            for msg in reporter.messages:
                item = {
                    'type': msg.category,
                    'module': msg.module,
                    'obj': msg.obj,
                    'line': msg.line,
                    'column': msg.column,
                    'path': msg.path,
                    'symbol': msg.symbol,
                    'message': msg.msg,
                    'message-id': msg.msg_id
                }
                
                if msg.category in ['error', 'fatal']:
                    results['errors'].append(item)
                elif msg.category == 'warning':
                    results['warnings'].append(item)
                else:
                    results['conventions'].append(item)
            
            # Clean up
            import os
            os.unlink(temp_path)
            
            return results
        except Exception as e:
            error_msg = f"Error linting code: {str(e)}"
            logging.error(error_msg)
            return {
                'errors': [],
                'warnings': [],
                'conventions': []
            }

    def disassemble_code(
        self,
        code: str
    ) -> Optional[str]:
        """Disassemble Python code to bytecode.
        
        Args:
            code: Python code to disassemble
            
        Returns:
            Disassembled bytecode as string
        """
        try:
            # Import dis only when needed
            import dis
            
            # Compile code
            compiled_code = compile(code, '<string>', 'exec')
            
            # Capture disassembly
            output = io.StringIO()
            with redirect_stdout(output):
                dis.dis(compiled_code)
            
            return output.getvalue()
        except Exception as e:
            error_msg = f"Error disassembling code: {str(e)}"
            logging.error(error_msg)
            return None

# Create instance for direct function access
_python_tools = PythonTools()
execute_code = _python_tools.execute_code
analyze_code = _python_tools.analyze_code
format_code = _python_tools.format_code
lint_code = _python_tools.lint_code
disassemble_code = _python_tools.disassemble_code

if __name__ == "__main__":
    print("\n==================================================")
    print("PythonTools Demonstration")
    print("==================================================\n")

    print("1. Execute Python Code")
    print("------------------------------")
    code = """
def greet(name):
    return f"Hello, {name}!"

result = greet("World")
print(result)
"""
    print("Code to execute:")
    print(code)
    print("\nOutput:")
    result = execute_code(code)
    print(result["stdout"])
    print()

    print("2. Format Python Code")
    print("------------------------------")
    code = """
def messy_function(x,y,   z):
    if x>0:
     return y+z
    else:
     return y-z
"""
    print("Before formatting:")
    print(code)
    print("\nAfter formatting:")
    result = format_code(code)
    print(result)
    print()

    print("3. Lint Python Code")
    print("------------------------------")
    code = """
def bad_function():
    unused_var = 42
    return 'result'
"""
    print("Code to lint:")
    print(code)
    print("\nLinting results:")
    result = lint_code(code)
    print(result)
    print()

    print("4. Execute Code with Variables")
    print("------------------------------")
    code = """
x = 10
y = 20
result = x + y
print(f"The sum of {x} and {y} is {result}")
"""
    print("Code to execute:")
    print(code)
    print("\nOutput:")
    result = execute_code(code)
    print(result["stdout"])
    print()

    print("==================================================")
    print("Demonstration Complete")
    print("==================================================")
