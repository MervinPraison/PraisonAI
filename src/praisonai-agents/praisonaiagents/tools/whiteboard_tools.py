"""Agent tools for a shared whiteboard (stickies, shapes, arrows).

The canvas opens when the reply includes the tool result's ``markdown`` fence.
"""

from typing import Any, Dict, List, Optional

from .decorator import tool


@tool
def whiteboard_create(title: str, items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Create a whiteboard and optionally place the first items.

    Each item is sticky, shape, text, group, or arrow. Stickies and shapes
    use text, x, y, w, h, and an optional color. An arrow uses from and to
    item ids. Paste the returned markdown field into the reply unchanged.

    Args:
        title: Board title.
        items: Optional list of item dicts.

    Returns:
        The board, a short summary, and a whiteboard markdown fence.
    """
    from praisonaiagents.studio.documents import whiteboard_create as _create

    try:
        return _create(title, items or [])
    except Exception as exc:
        return {"error": str(exc)}


@tool
def whiteboard_add(board_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Add items to an existing whiteboard.

    Args:
        board_id: Id from whiteboard_create (wb_...).
        items: New stickies, shapes, text, groups, or arrows.

    Returns:
        The updated board and a markdown fence to paste into the reply.
    """
    from praisonaiagents.studio.documents import whiteboard_add as _add

    try:
        return _add(board_id, items)
    except Exception as exc:
        return {"error": str(exc)}


@tool
def whiteboard_update(board_id: str, item_id: str, text: str = "", x: Optional[float] = None, y: Optional[float] = None) -> Dict[str, Any]:
    """Change one whiteboard item's text or position.

    Args:
        board_id: Board id.
        item_id: Item id.
        text: New text. Empty leaves the text unchanged.
        x: New x, or omit.
        y: New y, or omit.

    Returns:
        The updated board and a markdown fence.
    """
    from praisonaiagents.studio.documents import whiteboard_update as _update

    fields: Dict[str, Any] = {}
    if text:
        fields["text"] = text
    if x is not None:
        fields["x"] = x
    if y is not None:
        fields["y"] = y
    try:
        return _update(board_id, item_id, **fields)
    except Exception as exc:
        return {"error": str(exc)}


@tool
def whiteboard_get(board_id: str) -> Dict[str, Any]:
    """Read a whiteboard.

    Args:
        board_id: Board id.

    Returns:
        The board and a markdown fence.
    """
    from praisonaiagents.studio.documents import whiteboard_get as _get

    try:
        return _get(board_id)
    except Exception as exc:
        return {"error": str(exc)}
