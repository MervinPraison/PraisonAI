"""
Auto-instrumentation module for PraisonAI Performance Monitoring

This module provides automatic instrumentation of PraisonAI components
without requiring any code changes. It uses monkey patching to add
performance tracking to key functions and methods.
"""

import functools
import importlib
import sys
import types
from typing import Any, Callable, List, Set
import logging

from .performance_monitor import get_performance_monitor, track_api_performance


class AutoInstrument:
    """
    Automatic instrumentation system for PraisonAI components.
    
    This class provides non-invasive performance monitoring by monkey patching
    existing functions and methods with performance tracking code.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.instrumented_functions: Set[str] = set()
        self.original_functions = {}  # Store original functions for restoration
        
        # Define what to instrument
        self.instrument_config = {
            # Core agent methods
            'praisonaiagents.agent.agent': [
                'Agent.chat',
                'Agent.achat',
                'Agent.execute',
                'Agent.aexecute'
            ],
            
            # Multi-agent orchestration
            'praisonaiagents.agents.agents': [
                'PraisonAIAgents.start',
                'PraisonAIAgents.astart',
                'PraisonAIAgents.execute_task',
                'PraisonAIAgents.aexecute_task'
            ],
            
            # Task execution
            'praisonaiagents.task.task': [
                'Task.execute',
                'Task.aexecute'
            ],
            
            # Tool calls
            'praisonaiagents.tools.tools': [
                'Tools.execute_tool'
            ],
            
            # LLM calls
            'praisonaiagents.llm.llm': [
                'LLM.get_response',
                'LLM.aget_response',
                'LLM.chat_completion',
                'LLM.achat_completion'
            ],
            
            # Memory operations
            'praisonaiagents.memory.memory': [
                'Memory.add',
                'Memory.search',
                'Memory.get'
            ],
            
            # Knowledge operations
            'praisonaiagents.knowledge.knowledge': [
                'Knowledge.add',
                'Knowledge.search',
                'Knowledge.process_documents'
            ]
        }
        
        # API call patterns to track
        self.api_patterns = {
            'litellm': {
                'module': 'litellm',
                'functions': ['completion', 'acompletion'],
                'api_type': 'llm'
            },
            'openai': {
                'module': 'openai', 
                'functions': ['ChatCompletion.create'],
                'api_type': 'llm'
            },
            'requests': {
                'module': 'requests',
                'functions': ['get', 'post', 'put', 'delete', 'patch'],
                'api_type': 'http'
            },
            'httpx': {
                'module': 'httpx',
                'functions': ['get', 'post', 'put', 'delete', 'patch'],
                'api_type': 'http'  
            }
        }
        
    def instrument_all(self):
        """Instrument all configured functions and APIs."""
        if not get_performance_monitor().is_enabled():
            self.logger.debug("Performance monitoring disabled, skipping instrumentation")
            return
            
        self.logger.info("Starting auto-instrumentation of PraisonAI components")
        
        # Instrument PraisonAI functions
        self._instrument_praisonai_functions()
        
        # Instrument API calls
        self._instrument_api_calls()
        
        self.logger.info(f"Auto-instrumentation complete. Instrumented {len(self.instrumented_functions)} functions")
        
    def _instrument_praisonai_functions(self):
        """Instrument core PraisonAI functions."""
        for module_name, functions in self.instrument_config.items():
            try:
                module = importlib.import_module(module_name)
                
                for func_path in functions:
                    self._instrument_function(module, func_path, module_name)
                    
            except ImportError as e:
                self.logger.debug(f"Module {module_name} not available for instrumentation: {e}")
                continue
            except Exception as e:
                self.logger.warning(f"Error instrumenting module {module_name}: {e}")
                continue
                
    def _instrument_function(self, module: types.ModuleType, func_path: str, module_name: str):
        """Instrument a specific function or method."""
        try:
            # Parse function path (e.g., "Agent.chat" -> class Agent, method chat)
            parts = func_path.split('.')
            
            if len(parts) == 1:
                # Module-level function
                func_name = parts[0]
                if hasattr(module, func_name):
                    original_func = getattr(module, func_name)
                    instrumented_func = self._create_instrumented_function(
                        original_func, f"{module_name}.{func_name}"
                    )
                    
                    # Store original and replace with instrumented version
                    self.original_functions[f"{module_name}.{func_name}"] = original_func
                    setattr(module, func_name, instrumented_func)
                    self.instrumented_functions.add(f"{module_name}.{func_name}")
                    
            elif len(parts) == 2:
                # Class method
                class_name, method_name = parts
                if hasattr(module, class_name):
                    cls = getattr(module, class_name)
                    if hasattr(cls, method_name):
                        original_method = getattr(cls, method_name)
                        instrumented_method = self._create_instrumented_method(
                            original_method, f"{module_name}.{class_name}.{method_name}"
                        )
                        
                        # Store original and replace with instrumented version
                        self.original_functions[f"{module_name}.{func_path}"] = original_method
                        setattr(cls, method_name, instrumented_method)
                        self.instrumented_functions.add(f"{module_name}.{func_path}")
                        
        except Exception as e:
            self.logger.warning(f"Failed to instrument {func_path} in {module_name}: {e}")
            
    def _create_instrumented_function(self, original_func: Callable, full_name: str) -> Callable:
        """Create an instrumented version of a function."""
        @functools.wraps(original_func)
        def instrumented_func(*args, **kwargs):
            monitor = get_performance_monitor()
            func_name = full_name.split('.')[-1]
            module_name = '.'.join(full_name.split('.')[:-1])
            
            with monitor.track_function(func_name, module_name):
                return original_func(*args, **kwargs)
                
        return instrumented_func
    
    def _create_instrumented_method(self, original_method: Callable, full_name: str) -> Callable:
        """Create an instrumented version of a method."""
        @functools.wraps(original_method)
        def instrumented_method(self, *args, **kwargs):
            monitor = get_performance_monitor()
            method_name = full_name.split('.')[-1]
            module_name = '.'.join(full_name.split('.')[:-1])
            
            with monitor.track_function(method_name, module_name):
                return original_method(self, *args, **kwargs)
                
        return instrumented_method
        
    def _instrument_api_calls(self):
        """Instrument API calls for detailed tracking."""
        for pattern_name, config in self.api_patterns.items():
            try:
                self._instrument_api_module(pattern_name, config)
            except Exception as e:
                self.logger.debug(f"Could not instrument API module {pattern_name}: {e}")
                
    def _instrument_api_module(self, pattern_name: str, config: dict):
        """Instrument a specific API module."""
        module_name = config['module']
        api_type = config['api_type']
        
        try:
            # Handle modules that might not be available
            if module_name not in sys.modules:
                try:
                    importlib.import_module(module_name)
                except ImportError:
                    return  # Module not available, skip
                    
            module = sys.modules[module_name]
            
            for func_name in config['functions']:
                try:
                    if '.' in func_name:
                        # Nested attribute (e.g., ChatCompletion.create)
                        parts = func_name.split('.')
                        obj = module
                        for part in parts[:-1]:
                            obj = getattr(obj, part)
                        
                        method_name = parts[-1]
                        if hasattr(obj, method_name):
                            original_func = getattr(obj, method_name)
                            instrumented_func = self._create_instrumented_api_call(
                                original_func, f"{module_name}.{func_name}", api_type
                            )
                            
                            self.original_functions[f"{module_name}.{func_name}"] = original_func
                            setattr(obj, method_name, instrumented_func)
                            self.instrumented_functions.add(f"{module_name}.{func_name}")
                    else:
                        # Direct module function
                        if hasattr(module, func_name):
                            original_func = getattr(module, func_name)
                            instrumented_func = self._create_instrumented_api_call(
                                original_func, f"{module_name}.{func_name}", api_type
                            )
                            
                            self.original_functions[f"{module_name}.{func_name}"] = original_func
                            setattr(module, func_name, instrumented_func)
                            self.instrumented_functions.add(f"{module_name}.{func_name}")
                            
                except Exception as e:
                    self.logger.debug(f"Failed to instrument {func_name} in {module_name}: {e}")
                    
        except Exception as e:
            self.logger.debug(f"Failed to instrument API module {module_name}: {e}")
            
    def _create_instrumented_api_call(self, original_func: Callable, full_name: str, api_type: str) -> Callable:
        """Create an instrumented version of an API call."""
        @functools.wraps(original_func)
        def instrumented_api_call(*args, **kwargs):
            monitor = get_performance_monitor()
            
            # Extract endpoint and provider information
            endpoint = self._extract_endpoint(full_name, args, kwargs)
            provider = self._extract_provider(full_name, args, kwargs)
            model = self._extract_model(args, kwargs) if api_type == 'llm' else None
            method = self._extract_method(full_name, args, kwargs)
            
            with track_api_performance(api_type, endpoint, method, provider, model):
                return original_func(*args, **kwargs)
                
        return instrumented_api_call
        
    def _extract_endpoint(self, full_name: str, args: tuple, kwargs: dict) -> str:
        """Extract endpoint information from API call."""
        # Default to function name
        endpoint = full_name.split('.')[-1]
        
        # Try to get more specific endpoint info
        if 'url' in kwargs:
            endpoint = kwargs['url']
        elif len(args) > 0 and isinstance(args[0], str) and ('http' in args[0] or 'api' in args[0]):
            endpoint = args[0]
        elif 'model' in kwargs:
            endpoint = kwargs['model']
            
        return endpoint
        
    def _extract_provider(self, full_name: str, args: tuple, kwargs: dict) -> str:
        """Extract provider information from API call."""
        if 'openai' in full_name.lower():
            return 'openai'
        elif 'anthropic' in full_name.lower():
            return 'anthropic'  
        elif 'gemini' in full_name.lower() or 'google' in full_name.lower():
            return 'google'
        elif 'litellm' in full_name.lower():
            # For LiteLLM, try to extract actual provider from model
            if 'model' in kwargs:
                model = kwargs['model']
                if 'gpt' in model:
                    return 'openai'
                elif 'claude' in model:
                    return 'anthropic'
                elif 'gemini' in model:
                    return 'google'
            return 'litellm'
        else:
            return full_name.split('.')[0]  # Use module name
            
    def _extract_model(self, args: tuple, kwargs: dict) -> str:
        """Extract model information from LLM API call."""
        if 'model' in kwargs:
            return kwargs['model']
        elif len(args) > 0 and isinstance(args[0], str):
            return args[0]
        return None
        
    def _extract_method(self, full_name: str, args: tuple, kwargs: dict) -> str:
        """Extract HTTP method from API call."""
        func_name = full_name.split('.')[-1].lower()
        
        if func_name in ['get', 'post', 'put', 'delete', 'patch']:
            return func_name.upper()
        elif 'completion' in func_name:
            return 'POST'
        else:
            return 'POST'  # Default
            
    def restore_all(self):
        """Restore all instrumented functions to their original versions."""
        restored_count = 0
        
        for full_name in list(self.instrumented_functions):
            try:
                if full_name in self.original_functions:
                    self._restore_function(full_name)
                    restored_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to restore {full_name}: {e}")
                
        self.instrumented_functions.clear()
        self.original_functions.clear()
        
        self.logger.info(f"Restored {restored_count} instrumented functions")
        
    def _restore_function(self, full_name: str):
        """Restore a specific function to its original version."""
        original_func = self.original_functions[full_name]
        parts = full_name.split('.')
        
        # Get the module
        module_name = '.'.join(parts[:-2]) if len(parts) > 2 else parts[0]
        module = sys.modules.get(module_name)
        
        if module is None:
            return
            
        if len(parts) == 2:
            # Module-level function
            func_name = parts[-1]
            setattr(module, func_name, original_func)
        elif len(parts) == 3:
            # Class method
            class_name, method_name = parts[-2], parts[-1]
            if hasattr(module, class_name):
                cls = getattr(module, class_name)
                setattr(cls, method_name, original_func)


# Global auto-instrumentation instance
_auto_instrument = None


def get_auto_instrument() -> AutoInstrument:
    """Get the global auto-instrumentation instance."""
    global _auto_instrument
    if _auto_instrument is None:
        _auto_instrument = AutoInstrument()
    return _auto_instrument


def enable_auto_instrumentation():
    """Enable automatic performance monitoring instrumentation."""
    instrument = get_auto_instrument()
    instrument.instrument_all()


def disable_auto_instrumentation():
    """Disable automatic instrumentation and restore original functions."""
    instrument = get_auto_instrument()
    instrument.restore_all()