"""
Recipe Exceptions

Custom exceptions for recipe operations.
"""


class RecipeError(Exception):
    """Base exception for recipe operations."""
    
    def __init__(self, message: str, recipe: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.recipe = recipe
        self.details = details or {}


class RecipeNotFoundError(RecipeError):
    """Recipe not found."""
    pass


class RecipeDependencyError(RecipeError):
    """Missing dependencies for recipe execution."""
    
    def __init__(self, message: str, recipe: str = None, missing: list = None):
        super().__init__(message, recipe, {"missing": missing or []})
        self.missing = missing or []


class RecipePolicyError(RecipeError):
    """Security policy blocked execution."""
    
    def __init__(self, message: str, recipe: str = None, policy: str = None):
        super().__init__(message, recipe, {"policy": policy})
        self.policy = policy


class RecipeValidationError(RecipeError):
    """Recipe validation failed."""
    
    def __init__(self, message: str, recipe: str = None, errors: list = None):
        super().__init__(message, recipe, {"errors": errors or []})
        self.errors = errors or []


class RecipeTimeoutError(RecipeError):
    """Recipe execution timed out."""
    pass


class RecipeExecutionError(RecipeError):
    """Recipe execution failed."""
    pass
