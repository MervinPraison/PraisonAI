"""In-memory whiteboards and sheets the agent edits with the user."""

from .documents import (
    clear_studio,
    excalidraw_create,
    excalidraw_get,
    sheet_get,
    sheet_set_cells,
    whiteboard_add,
    whiteboard_create,
    whiteboard_get,
    whiteboard_remove,
    whiteboard_update,
)

__all__ = [
    "clear_studio",
    "sheet_add_tab",
    "sheet_create",
    "sheet_get",
    "sheet_set_cells",
    "whiteboard_add",
    "whiteboard_create",
    "whiteboard_get",
    "whiteboard_remove",
    "whiteboard_update",
]
