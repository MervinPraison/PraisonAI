"""Agent tool for a dedicated Excalidraw diagram.

This is not the sticky whiteboard. The chat loads the Excalidraw canvas
only when the reply includes the returned ``excalidraw`` fence.
"""

from typing import Any, Dict, List, Optional

from .decorator import tool


@tool
def excalidraw_create(title: str, elements: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Create a hand-drawn Excalidraw diagram, separate from the sticky whiteboard.

    Each element is a rectangle, ellipse, diamond, text, arrow, or line.
    Shapes use x, y, width, height, and optional text. Text uses x, y, and text.
    An arrow uses x, y, width, and height (the end point relative to the start).
    Paste the returned markdown field into the reply unchanged.

    Args:
        title: Diagram title.
        elements: Skeleton shapes for the Excalidraw canvas.

    Returns:
        The scene and an excalidraw markdown fence.
    """
    from praisonaiagents.studio.documents import excalidraw_create as _create

    try:
        return _create(title, elements)
    except Exception as exc:
        return {"error": str(exc)}


@tool
def excalidraw_get(scene_id: str) -> Dict[str, Any]:
    """Read an Excalidraw scene created earlier in this process.

    Args:
        scene_id: Id from excalidraw_create (ex_...).

    Returns:
        The scene and an excalidraw markdown fence.
    """
    from praisonaiagents.studio.documents import excalidraw_get as _get

    try:
        return _get(scene_id)
    except Exception as exc:
        return {"error": str(exc)}
