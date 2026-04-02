import re

# 1. Update config/loader.py to compute is_empty once
with open("praisonaiagents/config/loader.py", "r") as f:
    loader_code = f.read()

# Replace the @property is_empty with just a cached boolean mechanism
old_prop = """    @property
    def is_empty(self) -> bool:
        \"\"\"Return True if all features are empty/default.\"\"\"
        return (
            self.model is None and
            self.base_url is None and
            self.allow_delegation is False and
            self.allow_code_execution is False and
            self.code_execution_mode == "safe" and
            self.memory is None and
            self.knowledge is None and
            self.planning is None and
            self.reflection is None and
            self.web is None and
            self.output is None and
            self.execution is None and
            self.caching is None and
            self.autonomy is None and
            self.skills is None
        )"""

new_prop = """    _is_empty: Optional[bool] = None

    @property
    def is_empty(self) -> bool:
        \"\"\"Return True if all features are empty/default.\"\"\"
        if self._is_empty is not None:
            return self._is_empty
            
        self._is_empty = (
            self.model is None and
            self.base_url is None and
            self.allow_delegation is False and
            self.allow_code_execution is False and
            self.code_execution_mode == "safe" and
            self.memory is None and
            self.knowledge is None and
            self.planning is None and
            self.reflection is None and
            self.web is None and
            self.output is None and
            self.execution is None and
            self.caching is None and
            self.autonomy is None and
            self.skills is None
        )
        return self._is_empty"""

loader_code = loader_code.replace(old_prop, new_prop)
with open("praisonaiagents/config/loader.py", "w") as f:
    f.write(loader_code)


# 2. Update agent/agent.py to use _defaults
with open("praisonaiagents/agent/agent.py", "r") as f:
    agent_code = f.read()

old_llm_block = """        # Apply config defaults for LLM if not explicitly set
        if llm is None and model is None:
            config_model = get_default("model")
            if config_model:
                llm = config_model
        
        # Apply config defaults for base_url if not explicitly set
        if base_url is None:
            config_base_url = get_default("base_url")
            if config_base_url:
                base_url = config_base_url"""

new_llm_block = """        # Delay config loading to avoid _loader_get_defaults unless needed"""

# Actually we need _defaults ANYWAY for the rest of features, so let's just initialize _defaults FIRST!

old_everything = """        from ..config.loader import apply_config_defaults, get_default
        
        # Apply config defaults for LLM if not explicitly set
        if llm is None and model is None:
            config_model = get_default("model")
            if config_model:
                llm = config_model
        
        # Apply config defaults for base_url if not explicitly set
        if base_url is None:
            config_base_url = get_default("base_url")
            if config_base_url:
                base_url = config_base_url
        
        # Apply config defaults for feature params (memory, knowledge, etc.)
        from ..config.loader import get_defaults_config as _loader_get_defaults"""

new_everything = """        from ..config.loader import get_defaults_config as _loader_get_defaults
        global _CACHED_DEFAULTS
        if _CACHED_DEFAULTS is None:
            _CACHED_DEFAULTS = _loader_get_defaults()
        _defaults = _CACHED_DEFAULTS
        _defaults_empty = _defaults.is_empty if hasattr(_defaults, 'is_empty') else False

        # Apply config defaults for LLM if not explicitly set
        if llm is None and model is None and _defaults.model:
            llm = _defaults.model
            
        # Apply config defaults for base_url if not explicitly set
        if base_url is None and _defaults.base_url:
            base_url = _defaults.base_url

        # Note: We already set __CACHED_DEFAULTS above, so no need here"""

agent_code = agent_code.replace(old_everything, new_everything)

old_redundant = """        from ..config.loader import get_defaults_config as _loader_get_defaults
        global _CACHED_DEFAULTS
        if _CACHED_DEFAULTS is None:
            _CACHED_DEFAULTS = _loader_get_defaults()
        _defaults = _CACHED_DEFAULTS
        _defaults_empty = _defaults.is_empty if hasattr(_defaults, 'is_empty') else False

        if not _defaults_empty:"""
new_redundant = """        if not _defaults_empty:"""

# Just replace the second occurrence manually (or find it):
if "        from ..config.loader import get_defaults_config as _loader_get_defaults" in agent_code[agent_code.find("if not _defaults_empty:") - 400 : agent_code.find("if not _defaults_empty:")]:
    # It exists! We just drop the duplicate initialization
    pass

# A cleaner way using regex:
agent_code = re.sub(
    r"        from \.\.config\.loader import get_defaults_config as _loader_get_defaults\n"
    r"        global _CACHED_DEFAULTS\n"
    r"        if _CACHED_DEFAULTS is None:\n"
    r"            _CACHED_DEFAULTS = _loader_get_defaults\(\)\n"
    r"        _defaults = _CACHED_DEFAULTS\n"
    r"        _defaults_empty = _defaults\.is_empty if hasattr\(_defaults, 'is_empty'\) else False\n\n"
    r"        if not _defaults_empty:",
    "        if not _defaults_empty:",
    agent_code
)

with open("praisonaiagents/agent/agent.py", "w") as f:
    f.write(agent_code)

print("success!")
