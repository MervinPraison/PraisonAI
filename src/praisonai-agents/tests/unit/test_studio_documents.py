"""Whiteboards, sheet formulas, and the agent tools."""

from praisonaiagents.studio.documents import (
    clear_studio,
    sheet_create,
    sheet_set_cells,
    whiteboard_add,
    whiteboard_create,
    whiteboard_update,
)


def setup_function():
    clear_studio()


def test_whiteboard_round_trip():
    created = whiteboard_create(
        "Retro",
        [
            {"id": "a", "type": "sticky", "text": "Slow deploys", "x": 20, "y": 20},
            {"id": "b", "type": "sticky", "text": "Ship a checklist", "x": 240, "y": 20},
            {"type": "arrow", "from": "a", "to": "b"},
        ],
    )
    assert created["kind"] == "whiteboard"
    assert created["document"]["title"] == "Retro"
    assert len(created["document"]["items"]) == 3
    assert "```whiteboard" in created["markdown"]
    updated = whiteboard_update(created["id"], "a", text="Deploys")
    sticky = next(i for i in updated["document"]["items"] if i["id"] == "a")
    assert sticky["text"] == "Deploys"
    again = whiteboard_add(created["id"], [{"type": "text", "text": "Theme", "x": 20, "y": 0}])
    assert len(again["document"]["items"]) == 4


def test_sheet_formulas():
    book = sheet_create(
        "Budget",
        [
            {
                "name": "Q1",
                "headers": ["Item", "Amount"],
                "rows": [["Ads", "100"], ["Tools", "40"], ["Total", "=SUM(B2:B3)"]],
            }
        ],
    )
    values = book["document"]["tabs"][0]["values"]
    assert values[0] == ["Item", "Amount"]
    assert values[3][1] == 140
    edited = sheet_set_cells(book["id"], "Q1", {"B2": "250"})
    assert edited["document"]["tabs"][0]["values"][3][1] == 290


def test_sheet_average_and_errors():
    book = sheet_create(
        "Model",
        [{"name": "Sheet1", "cells": {"A1": "10", "A2": "30", "A3": "=AVERAGE(A1:A2)", "B1": "=A1/0"}}],
    )
    values = book["document"]["tabs"][0]["values"]
    assert values[2][0] == 20
    assert values[0][1] == "#DIV/0"
