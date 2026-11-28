"""Agent tools for a spreadsheet with tabs and formulas.

Formulas start with ``=`` and may use A1 refs, ranges, and SUM, AVERAGE,
MIN, MAX, COUNT. Paste the returned ``markdown`` fence into the reply so
the canvas opens the sheet.
"""

from typing import Any, Dict, List, Optional

from .decorator import tool


@tool
def sheet_create(title: str, tabs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Create a workbook.

    A tab may use headers plus rows, or a cells map of A1 addresses to
    values. A cell that starts with = is a formula (``=SUM(B2:B4)``).
    Paste the returned markdown field into the reply unchanged.

    Args:
        title: Workbook title.
        tabs: Optional list of tab dicts (name, headers, rows, or cells).

    Returns:
        The workbook with computed values and a sheet markdown fence.
    """
    from praisonaiagents.studio.documents import sheet_create as _create

    try:
        return _create(title, tabs)
    except Exception as exc:
        return {"error": str(exc)}


@tool
def sheet_set_cells(book_id: str, tab: str, cells: Dict[str, Any]) -> Dict[str, Any]:
    """Write cells on one tab. Keys are A1 addresses.

    Args:
        book_id: Id from sheet_create (sh_...).
        tab: Tab name.
        cells: Map of address to value or formula.

    Returns:
        The workbook with computed values and a markdown fence.
    """
    from praisonaiagents.studio.documents import sheet_set_cells as _set

    try:
        return _set(book_id, tab, cells)
    except Exception as exc:
        return {"error": str(exc)}


@tool
def sheet_add_tab(book_id: str, name: str, headers: Optional[List[str]] = None, rows: Optional[List[List[Any]]] = None) -> Dict[str, Any]:
    """Add or replace a tab.

    Args:
        book_id: Workbook id.
        name: Tab name.
        headers: Optional header row.
        rows: Optional body rows.

    Returns:
        The workbook and a markdown fence.
    """
    from praisonaiagents.studio.documents import sheet_add_tab as _add

    try:
        return _add(book_id, name, {"headers": headers or [], "rows": rows or []})
    except Exception as exc:
        return {"error": str(exc)}


@tool
def sheet_get(book_id: str) -> Dict[str, Any]:
    """Read a workbook, including computed formula values.

    Args:
        book_id: Workbook id.

    Returns:
        The workbook and a markdown fence.
    """
    from praisonaiagents.studio.documents import sheet_get as _get

    try:
        return _get(book_id)
    except Exception as exc:
        return {"error": str(exc)}
