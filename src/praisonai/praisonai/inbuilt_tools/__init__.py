# Only try to import autogen_tools if either CrewAI or AG2 is available
CREWAI_AVAILABLE = False
AUTOGEN_AVAILABLE = False
PRAISONAI_TOOLS_AVAILABLE = False

try:
    from crewai import Agent, Task, Crew
    CREWAI_AVAILABLE = True
except ImportError:
    pass

try:
    # Try importing ag2 first (new package name)
    import ag2 as autogen
    AUTOGEN_AVAILABLE = True
except ImportError:
    try:
        # Fall back to pyautogen for backward compatibility
        import autogen
        AUTOGEN_AVAILABLE = True
    except ImportError:
        pass

# Only try to import tools if a framework is available
if CREWAI_AVAILABLE or AUTOGEN_AVAILABLE:
    try:
        from .autogen_tools import *
        PRAISONAI_TOOLS_AVAILABLE = True
    except ImportError:
        pass