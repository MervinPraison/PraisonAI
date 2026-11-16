"""
Scoped warning filters for specific noisy third-party warnings.
Uses ``warnings.filterwarnings`` only; ``warnings.warn`` is never replaced.
"""

import warnings

# Message-scoped filters (regex matched from the start of the message)
warnings.filterwarnings("ignore", message=".*There is no current event loop.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*Pydantic serializer warnings.*")
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")
warnings.filterwarnings("ignore", message=".*Expected \\d+ fields but got.*")
warnings.filterwarnings("ignore", message=".*Expected `StreamingChoices` but got.*")
warnings.filterwarnings("ignore", message=".*serialized value may not be as expected.*")
warnings.filterwarnings("ignore", message=".*Use 'content=<...>' to upload raw bytes/text content.*")
warnings.filterwarnings("ignore", message=".*The `dict` method is deprecated.*")
warnings.filterwarnings("ignore", message=".*Mixing V1 models and V2 models.*")
warnings.filterwarnings("ignore", message=".*Please upgrade `Settings` to V2.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")
