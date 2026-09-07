"""Attachment routing for multimodal prompts.

The one invariant this module exists to enforce: **an attachment is never
dropped silently**. Every input either becomes a model-visible content part, or
produces a loud, actionable signal that names the file and says why.

Two failure classes are treated differently on purpose:

``raise`` -- *addressing* errors: the path does not exist, is a directory, is
    unreadable, or the attachment is not a type this API accepts. These are
    always caller mistakes (a typo, a wrong working directory, a stale path).
    They are fully actionable at the call site, there is no useful degraded
    answer, and continuing would produce a confident answer about a file the
    model never saw. Raising is the only way the caller can tell.

``warn + visible degrade`` -- *capability* limits: the file is there and
    readable, but the target model cannot ingest that media type. The run can
    still be useful, so we log a warning **and** put a marker part in the
    prompt so the model itself knows a file was withheld or converted and can
    say so. This is environmental, not a bug in the caller's code, and hard
    failing would make a model swap a breaking change.

Escape hatches (both default to the behaviour described above):

- ``PRAISONAI_ATTACHMENTS_ON_MISSING=warn`` downgrades the missing/unreadable
  raise to a warning + visible marker part.
- ``PRAISONAI_ATTACHMENTS_STRICT=1`` escalates capability degrades to raises,
  for pipelines that would rather fail than get a partial answer.

Part shapes emitted (OpenAI/LiteLLM chat-completions style):

- image      -> ``{"type": "image_url", "image_url": {"url": "data:...;base64,..."}}``
- pdf native -> ``{"type": "file", "file": {"filename": ..., "file_data": "data:application/pdf;base64,..."}}``
- audio      -> ``{"type": "input_audio", "input_audio": {"data": "<b64>", "format": "mp3"}}``
- text/degraded/withheld -> ``{"type": "text", "text": "[Attachment: ...] ..."}``
"""

import base64
import logging
import os
from typing import Any, Dict, List, Optional

from ..tools.base import file_part, image_part, text_part

__all__ = [
    "AttachmentError",
    "build_attachment_parts",
    "resolve_attachment_model_name",
    "IMAGE_EXTENSIONS",
    "PDF_EXTENSIONS",
    "AUDIO_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "TEXT_EXTENSIONS",
]


class AttachmentError(ValueError):
    """Raised when an attachment cannot be turned into a model content part.

    Subclasses ``ValueError`` so existing ``except ValueError`` handlers around
    ``chat()`` keep working.
    """


# --- Type tables -----------------------------------------------------------

# Unchanged from the original image-only implementation; images must keep
# producing byte-identical parts.
IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
IMAGE_EXTENSIONS = frozenset(IMAGE_MEDIA_TYPES)

PDF_EXTENSIONS = frozenset({".pdf"})

# Extension -> the ``format`` string sent in an ``input_audio`` part.
AUDIO_FORMATS = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".m4a": "m4a",
    ".ogg": "ogg",
    ".oga": "ogg",
    ".opus": "opus",
    ".flac": "flac",
    ".aac": "aac",
}
AUDIO_EXTENSIONS = frozenset(AUDIO_FORMATS)

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg", ".wmv"})

# Files we can safely inline as UTF-8 text. No model capability needed.
TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json",
    ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml",
    ".html", ".htm", ".sql", ".py", ".js", ".ts", ".tsx", ".jsx", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
    ".kt", ".sh", ".bash", ".zsh", ".env", ".tex", ".srt", ".vtt",
})

# Inlined text is truncated so one large file cannot blow the context window.
# Truncation is announced in the part itself, never silent.
MAX_INLINE_TEXT_CHARS = 100_000


# --- Helpers ---------------------------------------------------------------

def _on_missing_raises() -> bool:
    return os.environ.get("PRAISONAI_ATTACHMENTS_ON_MISSING", "error").strip().lower() not in (
        "warn", "warning", "ignore", "0", "false",
    )


def _strict_unsupported() -> bool:
    return os.environ.get("PRAISONAI_ATTACHMENTS_STRICT", "").strip().lower() in (
        "1", "true", "yes", "on", "error", "raise",
    )


def _fail(message: str) -> List[Dict[str, Any]]:
    """Addressing error: raise, unless explicitly downgraded to a warning."""
    if _on_missing_raises():
        raise AttachmentError(message)
    logging.warning("Attachment problem: %s", message)
    return [text_part(f"[Attachment could not be read: {message}]")]


def _degrade(message: str, marker: str) -> List[Dict[str, Any]]:
    """Capability limit: warn loudly and leave a marker the model can see."""
    if _strict_unsupported():
        raise AttachmentError(message + " (PRAISONAI_ATTACHMENTS_STRICT is set)")
    logging.warning("Attachment degraded: %s", message)
    return [text_part(marker)]


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _extract_pdf_text(path: str) -> Optional[str]:
    """Return a PDF's text, or ``None`` if no extractor is installed/usable."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return None
    try:
        reader = PdfReader(path)
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                pages.append(f"--- page {index} ---\n{page.extract_text() or ''}")
            except Exception as exc:  # noqa: BLE001 - one bad page must not kill the rest
                logging.debug("PDF page %d of %s failed to extract: %s", index, path, exc)
        text = "\n".join(pages).strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        logging.debug("PDF text extraction failed for %s: %s", path, exc)
        return None


def _truncate(text: str, label: str) -> str:
    if len(text) <= MAX_INLINE_TEXT_CHARS:
        return text
    logging.warning(
        "Attachment %s truncated to %d of %d characters", label, MAX_INLINE_TEXT_CHARS, len(text)
    )
    return (
        text[:MAX_INLINE_TEXT_CHARS]
        + f"\n\n[... truncated: {len(text) - MAX_INLINE_TEXT_CHARS} more characters not shown ...]"
    )


def resolve_attachment_model_name(agent: Any) -> str:
    """Best-effort model id for capability routing.

    Mirrors the resolution already used by the agent's other capability probes
    (``_model_supports_web_search`` and friends).
    """
    instance = getattr(agent, "llm_instance", None)
    model = getattr(instance, "model", None) if instance else None
    if isinstance(model, str) and model:
        return model
    llm = getattr(agent, "llm", None)
    if isinstance(llm, str) and llm:
        return llm
    if isinstance(llm, dict):
        model = llm.get("model")
        if isinstance(model, str) and model:
            return model
    return ""


# --- Per-type builders -----------------------------------------------------

def _image_message_part(path: str, ext: str) -> Dict[str, Any]:
    """Encode an image exactly as the original implementation did."""
    media_type = IMAGE_MEDIA_TYPES.get(ext, "image/jpeg")
    encoded = _b64(_read_bytes(path))
    # Canonical part first (shared vocabulary with tools/base.py), then the
    # provider-facing shape, so there is one definition of "an image part".
    canonical = image_part(encoded, mime=media_type, name=os.path.basename(path))
    logging.debug(
        "Successfully encoded image attachment: %s (%d bytes base64)", path, len(encoded)
    )
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{canonical['mime']};base64,{canonical['data']}"},
    }


def _pdf_parts(path: str, model_name: str) -> List[Dict[str, Any]]:
    name = os.path.basename(path)
    if _capability("pdf", model_name):
        canonical = file_part(
            _b64(_read_bytes(path)), mime="application/pdf", name=name
        )
        return [{
            "type": "file",
            "file": {
                "filename": canonical["name"],
                "file_data": f"data:{canonical['mime']};base64,{canonical['data']}",
            },
        }]

    text = _extract_pdf_text(path)
    if text:
        logging.warning(
            "Model %r cannot accept PDF attachments natively; sending locally "
            "extracted text of %s instead. Use a PDF-capable model (e.g. an "
            "Anthropic Claude or OpenAI gpt-4o/4.1 model) to send the document itself.",
            model_name or "<unknown>", path,
        )
        body = _truncate(text, name)
        return [text_part(
            f"[Attachment: {name} - PDF text extracted locally because model "
            f"{model_name or '<unknown>'!r} cannot accept PDF files directly; "
            f"layout, images and tables are lost]\n{body}"
        )]

    return _degrade(
        f"{path}: model {model_name or '<unknown>'!r} cannot accept PDFs natively and the "
        f"PDF's text could not be extracted (install 'pypdf', or use a PDF-capable model)",
        f"[Attachment omitted: {name} - the PDF could not be sent to model "
        f"{model_name or '<unknown>'!r} and its text could not be extracted locally. "
        f"Answer without it and say so.]",
    )


def _audio_parts(path: str, ext: str, model_name: str) -> List[Dict[str, Any]]:
    name = os.path.basename(path)
    if _capability("audio", model_name):
        canonical = file_part(
            _b64(_read_bytes(path)),
            mime=f"audio/{AUDIO_FORMATS.get(ext, 'mpeg')}",
            name=name,
        )
        return [{
            "type": "input_audio",
            "input_audio": {
                "data": canonical["data"],
                "format": AUDIO_FORMATS.get(ext, "mp3"),
            },
        }]

    return _degrade(
        f"{path}: model {model_name or '<unknown>'!r} cannot accept audio input "
        f"(use an audio-capable model such as gpt-4o-audio-preview or a Gemini model, "
        f"or transcribe the file first)",
        f"[Attachment omitted: {name} - audio was not sent because model "
        f"{model_name or '<unknown>'!r} cannot accept audio input. Answer without "
        f"it and say so.]",
    )


def _text_parts(path: str) -> List[Dict[str, Any]]:
    name = os.path.basename(path)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        return _fail(f"{path}: could not be read ({exc})")
    return [text_part(f"[Attachment: {name}]\n{_truncate(content, name)}")]


def _capability(kind: str, model_name: str) -> bool:
    """Capability probe, isolated so a broken/absent litellm never crashes a run."""
    try:
        from ..llm.model_capabilities import supports_audio_input, supports_pdf_input
    except Exception:  # noqa: BLE001
        return False
    try:
        if kind == "pdf":
            return bool(supports_pdf_input(model_name))
        if kind == "audio":
            return bool(supports_audio_input(model_name))
    except Exception as exc:  # noqa: BLE001
        logging.debug("Capability probe %s/%s failed: %s", kind, model_name, exc)
    return False


# --- Entry point -----------------------------------------------------------

def build_attachment_parts(attachment: Any, model_name: str = "") -> List[Dict[str, Any]]:
    """Turn one attachment into zero-or-more model content parts.

    Never returns an empty list for an input it could not handle: it either
    raises :class:`AttachmentError` or returns a visible marker part.
    """
    # Already-structured content parts pass through untouched.
    if isinstance(attachment, dict):
        if "type" not in attachment:
            logging.warning(
                "Attachment dict has no 'type' key and may be ignored by the provider: %r",
                attachment,
            )
        return [attachment]

    if isinstance(attachment, os.PathLike):
        attachment = os.fspath(attachment)

    if not isinstance(attachment, str):
        raise AttachmentError(
            f"Unsupported attachment type {type(attachment).__name__!r}: expected a file "
            f"path, an http(s)/data URL, or a content-part dict, got {attachment!r}"
        )

    if not attachment.strip():
        raise AttachmentError("Empty attachment path")

    if attachment.startswith(("http://", "https://", "data:")):
        return _remote_parts(attachment, model_name)

    if os.path.isdir(attachment):
        return _fail(f"{attachment}: is a directory, not a file")

    if not os.path.isfile(attachment):
        return _fail(
            f"{attachment}: no such file (attachment paths are resolved relative to the "
            f"current working directory {os.getcwd()!r})"
        )

    ext = os.path.splitext(attachment)[1].lower()
    name = os.path.basename(attachment)

    try:
        if ext in IMAGE_EXTENSIONS:
            return [_image_message_part(attachment, ext)]
        if ext in PDF_EXTENSIONS:
            return _pdf_parts(attachment, model_name)
        if ext in AUDIO_EXTENSIONS:
            return _audio_parts(attachment, ext, model_name)
        if ext in TEXT_EXTENSIONS:
            return _text_parts(attachment)
    except AttachmentError:
        raise
    except OSError as exc:
        return _fail(f"{attachment}: could not be read ({exc})")

    if ext in VIDEO_EXTENSIONS:
        return _degrade(
            f"{attachment}: video attachments are not supported on the chat-completions "
            f"path (extract frames as images, or a transcript as text, first)",
            f"[Attachment omitted: {name} - video attachments are not supported. "
            f"Answer without it and say so.]",
        )

    # Unknown extension. Rather than guess at a binary, try it as text when it
    # decodes cleanly as UTF-8; otherwise say plainly that it was not sent.
    sample_text = _maybe_text_file(attachment)
    if sample_text is not None:
        logging.warning(
            "Attachment %s has an unrecognised extension %r; inlining it as UTF-8 text.",
            attachment, ext or "(none)",
        )
        return [text_part(f"[Attachment: {name} (unrecognised type, sent as text)]\n"
                          f"{_truncate(sample_text, name)}")]

    return _degrade(
        f"{attachment}: unsupported attachment type {ext or '(no extension)'!r}. Supported: "
        f"images {sorted(IMAGE_EXTENSIONS)}, PDF, audio {sorted(AUDIO_EXTENSIONS)}, and "
        f"text-like files. Convert the file, or pass its text instead.",
        f"[Attachment omitted: {name} - unsupported file type "
        f"{ext or '(no extension)'!r}. Answer without it and say so.]",
    )


def _maybe_text_file(path: str) -> Optional[str]:
    """Return the file's text if it is valid UTF-8 and not obviously binary."""
    try:
        raw = _read_bytes(path)
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _remote_parts(url: str, model_name: str) -> List[Dict[str, Any]]:
    """Route an http(s) URL or data URI.

    Images (and anything without a recognisable non-image extension) keep the
    original behaviour: a straight ``image_url`` part. A URL that plainly names
    a non-image document is called out instead of being passed off as an image.
    """
    if url.startswith("data:"):
        mime = url[5:].split(";", 1)[0].split(",", 1)[0].lower()
        if mime and not mime.startswith("image/"):
            return _degrade(
                f"data URI with media type {mime!r} is not supported as an attachment; "
                f"only image data URIs are passed through",
                f"[Attachment omitted: a {mime} data URI was not sent to the model. "
                f"Answer without it and say so.]",
            )
        return [{"type": "image_url", "image_url": {"url": url}}]

    path = url.split("?", 1)[0].split("#", 1)[0]
    ext = os.path.splitext(path)[1].lower()
    if ext and ext not in IMAGE_EXTENSIONS and (
        ext in PDF_EXTENSIONS or ext in AUDIO_EXTENSIONS
        or ext in VIDEO_EXTENSIONS or ext in TEXT_EXTENSIONS
    ):
        return _degrade(
            f"{url}: remote {ext} attachments are not fetched (this function performs no "
            f"network I/O); download the file and pass the local path instead",
            f"[Attachment omitted: {url} - remote {ext} files are not downloaded "
            f"automatically. Answer without it and say so.]",
        )

    return [{"type": "image_url", "image_url": {"url": url}}]
