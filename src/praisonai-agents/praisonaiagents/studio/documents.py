"""Whiteboards and spreadsheets stored for one process.

Claude Whiteboards is a shared board of stickies, shapes, and arrows.
Claude Sheets is a workbook with tabs, formulas, and computed cells.
This is the same idea for an agent: tools mutate a document, and the
``markdown`` field is a fence the chat canvas renders.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_boards: Dict[str, Dict[str, Any]] = {}
_books: Dict[str, Dict[str, Any]] = {}

_CELL = re.compile(r"^([A-Z]+)(\d+)$")


def clear_studio() -> None:
    """Drop every board and workbook. Tests use this."""
    with _lock:
        _boards.clear()
        _books.clear()


def _id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:10]


def _fence(lang: str, doc: Dict[str, Any]) -> str:
    body = json.dumps(doc, ensure_ascii=False, indent=2)
    return f"```{lang} id={doc['id']}\n{body}\n```"


def _public(kind: str, doc: Dict[str, Any], summary: str) -> Dict[str, Any]:
    return {
        "id": doc["id"],
        "kind": kind,
        "title": doc.get("title") or doc["id"],
        "summary": summary,
        "document": doc,
        "markdown": _fence(kind, doc),
        "note": "Paste the markdown field into your reply unchanged so the canvas opens it.",
    }


# ── whiteboard ────────────────────────────────────────────────────────


def whiteboard_create(title: str, items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    board = {"id": _id("wb_"), "title": (title or "Whiteboard").strip() or "Whiteboard", "items": []}
    with _lock:
        _boards[board["id"]] = board
    added = whiteboard_add(board["id"], items or [])
    return added


def whiteboard_add(board_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    with _lock:
        board = _boards.get(board_id)
        if board is None:
            raise KeyError(f"whiteboard not found: {board_id}")
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            item = _normalize_item(raw)
            board["items"].append(item)
        doc = json.loads(json.dumps(board))
    return _public("whiteboard", doc, f"{len(doc['items'])} items on '{doc['title']}'")


def whiteboard_update(board_id: str, item_id: str, **fields: Any) -> Dict[str, Any]:
    with _lock:
        board = _boards.get(board_id)
        if board is None:
            raise KeyError(f"whiteboard not found: {board_id}")
        item = next((i for i in board["items"] if i["id"] == item_id), None)
        if item is None:
            raise KeyError(f"item not found: {item_id}")
        for key in ("text", "x", "y", "w", "h", "color", "shape"):
            if key in fields and fields[key] is not None:
                item[key] = fields[key]
        doc = json.loads(json.dumps(board))
    return _public("whiteboard", doc, f"updated {item_id}")


def whiteboard_remove(board_id: str, item_id: str) -> Dict[str, Any]:
    with _lock:
        board = _boards.get(board_id)
        if board is None:
            raise KeyError(f"whiteboard not found: {board_id}")
        board["items"] = [i for i in board["items"] if i["id"] != item_id]
        doc = json.loads(json.dumps(board))
    return _public("whiteboard", doc, f"removed {item_id}")


def whiteboard_get(board_id: str) -> Dict[str, Any]:
    with _lock:
        board = _boards.get(board_id)
        if board is None:
            raise KeyError(f"whiteboard not found: {board_id}")
        doc = json.loads(json.dumps(board))
    return _public("whiteboard", doc, f"{len(doc['items'])} items")


def _normalize_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(raw.get("type") or raw.get("kind") or "sticky").lower()
    if kind not in {"sticky", "shape", "text", "group", "arrow"}:
        kind = "sticky"
    item: Dict[str, Any] = {
        "id": str(raw.get("id") or _id("it_")),
        "type": kind,
        "text": str(raw.get("text") or raw.get("label") or ""),
        "x": _num(raw.get("x"), 40),
        "y": _num(raw.get("y"), 40),
        "w": _num(raw.get("w"), 180 if kind != "arrow" else 0),
        "h": _num(raw.get("h"), 110 if kind != "arrow" else 0),
    }
    if raw.get("color"):
        item["color"] = str(raw["color"])
    if kind == "shape":
        item["shape"] = str(raw.get("shape") or "rect")
    if kind == "arrow":
        item["from"] = str(raw.get("from") or raw.get("from_id") or "")
        item["to"] = str(raw.get("to") or raw.get("to_id") or "")
    return item


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ── sheets ────────────────────────────────────────────────────────────


def sheet_create(title: str, tabs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    book = {"id": _id("sh_"), "title": (title or "Sheet").strip() or "Sheet", "tabs": []}
    with _lock:
        _books[book["id"]] = book
    if not tabs:
        tabs = [{"name": "Sheet1", "headers": ["A", "B"], "rows": []}]
    for tab in tabs:
        sheet_add_tab(book["id"], tab.get("name") or "Sheet", tab)
    return sheet_get(book["id"])


def sheet_add_tab(book_id: str, name: str, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    spec = spec or {}
    grid = _grid_from_spec(spec)
    with _lock:
        book = _books.get(book_id)
        if book is None:
            raise KeyError(f"sheet not found: {book_id}")
        label = (name or "Sheet").strip() or "Sheet"
        book["tabs"] = [t for t in book["tabs"] if t["name"] != label]
        book["tabs"].append({"name": label, "grid": grid})
        doc = _display_book(book)
    return _public("sheet", doc, f"tab '{label}' on '{doc['title']}'")


def sheet_set_cells(book_id: str, tab: str, cells: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        book = _books.get(book_id)
        if book is None:
            raise KeyError(f"sheet not found: {book_id}")
        found = next((t for t in book["tabs"] if t["name"] == tab), None)
        if found is None:
            raise KeyError(f"tab not found: {tab}")
        grid: List[List[str]] = found["grid"]
        for addr, value in (cells or {}).items():
            col, row = _addr(str(addr))
            _ensure(grid, row, col)
            grid[row][col] = "" if value is None else str(value)
        doc = _display_book(book)
    return _public("sheet", doc, f"updated {len(cells or {})} cells on '{tab}'")


def sheet_get(book_id: str) -> Dict[str, Any]:
    with _lock:
        book = _books.get(book_id)
        if book is None:
            raise KeyError(f"sheet not found: {book_id}")
        doc = _display_book(book)
    return _public("sheet", doc, f"{len(doc['tabs'])} tabs")


def _grid_from_spec(spec: Dict[str, Any]) -> List[List[str]]:
    if isinstance(spec.get("cells"), dict):
        grid: List[List[str]] = []
        for addr, value in spec["cells"].items():
            col, row = _addr(str(addr))
            _ensure(grid, row, col)
            grid[row][col] = "" if value is None else str(value)
        return grid
    headers = [str(h) for h in (spec.get("headers") or spec.get("columns") or [])]
    rows = spec.get("rows") or []
    grid = []
    if headers:
        grid.append(headers)
    for row in rows:
        grid.append(["" if c is None else str(c) for c in row])
    width = max((len(r) for r in grid), default=0)
    for row in grid:
        row.extend([""] * (width - len(row)))
    return grid or [[]]


def _ensure(grid: List[List[str]], row: int, col: int) -> None:
    while len(grid) <= row:
        width = len(grid[0]) if grid else 0
        grid.append([""] * width)
    width = max(col + 1, max((len(r) for r in grid), default=0))
    for r in grid:
        r.extend([""] * (width - len(r)))


def _addr(addr: str) -> tuple[int, int]:
    match = _CELL.match(addr.strip().upper())
    if not match:
        raise ValueError(f"not a cell address: {addr}")
    col = 0
    for ch in match.group(1):
        col = col * 26 + (ord(ch) - 64)
    return col - 1, int(match.group(2)) - 1


def _display_book(book: Dict[str, Any]) -> Dict[str, Any]:
    tabs = []
    for tab in book["tabs"]:
        grid = tab["grid"]
        values = _evaluate(grid)
        tabs.append({"name": tab["name"], "grid": grid, "values": values})
    return {"id": book["id"], "title": book["title"], "tabs": tabs}


def _evaluate(grid: List[List[str]]) -> List[List[Any]]:
    cache: Dict[tuple[int, int], Any] = {}
    stack: set[tuple[int, int]] = set()

    def cell(col: int, row: int) -> Any:
        key = (col, row)
        if key in cache:
            return cache[key]
        if key in stack:
            return "#CYCLE"
        raw = grid[row][col] if row < len(grid) and col < len(grid[row]) else ""
        if not isinstance(raw, str) or not raw.startswith("="):
            cache[key] = _literal(raw)
            return cache[key]
        stack.add(key)
        try:
            value = _parse(raw[1:].strip(), cell)
        except Exception:
            value = "#ERR"
        stack.discard(key)
        cache[key] = value
        return value

    height = len(grid)
    width = max((len(r) for r in grid), default=0)
    return [[cell(c, r) for c in range(width)] for r in range(height)]


def _literal(raw: Any) -> Any:
    if raw is None:
        return ""
    text = str(raw)
    if text == "":
        return ""
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse(expr: str, cell) -> Any:
    pos = 0

    def peek() -> str:
        return expr[pos : pos + 1]

    def skip() -> None:
        nonlocal pos
        while peek() == " ":
            pos += 1

    def parse_expr() -> Any:
        nonlocal pos
        skip()
        value = parse_term()
        while True:
            skip()
            op = peek()
            if op not in {"+", "-"}:
                break
            pos += 1
            right = parse_term()
            value = _arith(value, op, right)
        return value

    def parse_term() -> Any:
        nonlocal pos
        skip()
        value = parse_unary()
        while True:
            skip()
            op = peek()
            if op not in {"*", "/"}:
                break
            pos += 1
            right = parse_unary()
            value = _arith(value, op, right)
        return value

    def parse_unary() -> Any:
        nonlocal pos
        skip()
        if peek() == "-":
            pos += 1
            return _arith(0, "-", parse_unary())
        return parse_primary()

    def parse_primary() -> Any:
        nonlocal pos
        skip()
        if peek() == "(":
            pos += 1
            value = parse_expr()
            skip()
            if peek() == ")":
                pos += 1
            return value
        if peek() == '"':
            pos += 1
            start = pos
            while pos < len(expr) and expr[pos] != '"':
                pos += 1
            text = expr[start:pos]
            if peek() == '"':
                pos += 1
            return text
        match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", expr[pos:])
        if match and expr[pos + match.end() : pos + match.end() + 1] == "(":
            name = match.group(0).upper()
            pos += match.end() + 1
            args: List[Any] = []
            skip()
            if peek() != ")":
                while True:
                    args.append(parse_arg())
                    skip()
                    if peek() == ",":
                        pos += 1
                        continue
                    break
            if peek() == ")":
                pos += 1
            return _call(name, args)
        ref = re.match(r"[A-Za-z]+\d+", expr[pos:])
        if ref:
            pos += ref.end()
            col, row = _addr(ref.group(0))
            return cell(col, row)
        num = re.match(r"\d+(?:\.\d+)?", expr[pos:])
        if num:
            pos += num.end()
            token = num.group(0)
            return float(token) if "." in token else int(token)
        raise ValueError(expr[pos:] or "empty")

    def parse_arg() -> Any:
        nonlocal pos
        skip()
        rng = re.match(r"[A-Za-z]+\d+:[A-Za-z]+\d+", expr[pos:])
        if rng:
            pos += rng.end()
            return _range_values(rng.group(0), cell)
        return parse_expr()

    value = parse_expr()
    return value


def _range_values(token: str, cell) -> List[Any]:
    start, end = token.split(":")
    c1, r1 = _addr(start)
    c2, r2 = _addr(end)
    out = []
    for row in range(min(r1, r2), max(r1, r2) + 1):
        for col in range(min(c1, c2), max(c1, c2) + 1):
            out.append(cell(col, row))
    return out


def _call(name: str, args: List[Any]) -> Any:
    flat: List[Any] = []
    for arg in args:
        if isinstance(arg, list):
            flat.extend(arg)
        else:
            flat.append(arg)
    nums = [n for n in (_as_num(v) for v in flat) if n is not None]
    if name == "SUM":
        return sum(nums)
    if name == "AVERAGE":
        return sum(nums) / len(nums) if nums else "#DIV/0"
    if name == "MIN":
        return min(nums) if nums else "#ERR"
    if name == "MAX":
        return max(nums) if nums else "#ERR"
    if name == "COUNT":
        return len(nums)
    return "#NAME"


def _as_num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _arith(left: Any, op: str, right: Any) -> Any:
    a = _as_num(left)
    b = _as_num(right)
    if a is None or b is None:
        return "#VALUE"
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return "#DIV/0" if b == 0 else a / b
    return "#ERR"
