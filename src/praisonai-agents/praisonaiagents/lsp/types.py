"""
LSP Types for PraisonAI Agents.

Defines the core types for Language Server Protocol integration.
"""

from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


class DiagnosticSeverity(IntEnum):
    """Severity of a diagnostic."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


@dataclass
class Position:
    """Position in a text document (0-indexed)."""
    line: int
    character: int
    
    def to_dict(self) -> Dict[str, int]:
        return {"line": self.line, "character": self.character}
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "Position":
        return cls(line=data["line"], character=data["character"])


@dataclass
class Range:
    """Range in a text document."""
    start: Position
    end: Position
    
    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Range":
        return cls(
            start=Position.from_dict(data["start"]),
            end=Position.from_dict(data["end"])
        )


@dataclass
class Location:
    """Location in a document."""
    uri: str
    range: Range
    
    def to_dict(self) -> Dict[str, Any]:
        return {"uri": self.uri, "range": self.range.to_dict()}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Location":
        return cls(uri=data["uri"], range=Range.from_dict(data["range"]))


@dataclass
class Diagnostic:
    """Represents a diagnostic (error, warning, etc.)."""
    range: Range
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    code: Optional[str] = None
    source: Optional[str] = None
    related_information: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "range": self.range.to_dict(),
            "message": self.message,
            "severity": self.severity.value,
            "code": self.code,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Diagnostic":
        return cls(
            range=Range.from_dict(data["range"]),
            message=data["message"],
            severity=DiagnosticSeverity(data.get("severity", 1)),
            code=data.get("code"),
            source=data.get("source")
        )


@dataclass
class CompletionItem:
    """Represents a completion item."""
    label: str
    kind: int = 1  # Text
    detail: Optional[str] = None
    documentation: Optional[str] = None
    insert_text: Optional[str] = None
    sort_text: Optional[str] = None
    filter_text: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
            "documentation": self.documentation,
            "insertText": self.insert_text
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompletionItem":
        return cls(
            label=data["label"],
            kind=data.get("kind", 1),
            detail=data.get("detail"),
            documentation=data.get("documentation"),
            insert_text=data.get("insertText")
        )


@dataclass
class TextDocumentItem:
    """Represents a text document."""
    uri: str
    language_id: str
    version: int
    text: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "languageId": self.language_id,
            "version": self.version,
            "text": self.text
        }


@dataclass
class TextDocumentIdentifier:
    """Identifies a text document."""
    uri: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"uri": self.uri}


@dataclass
class TextDocumentPositionParams:
    """Parameters for text document position requests."""
    text_document: TextDocumentIdentifier
    position: Position
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "textDocument": self.text_document.to_dict(),
            "position": self.position.to_dict()
        }
