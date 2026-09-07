"""Attachments must never be dropped silently.

Regression tests for the defect where ``_build_multimodal_prompt`` appended a
content part only for image extensions: a PDF, an audio file, a text file, or a
typo'd path produced no part, no warning and no error, and the model answered
from the text prompt alone.

Stubbed capability lookups; no network, no LLM calls.
"""

import pytest

from praisonaiagents.agent.attachments import (
    AttachmentError,
    build_attachment_parts,
)


# --- Fixtures --------------------------------------------------------------

def _write_pdf(path, text="Hello PDF world"):
    """A minimal but structurally valid PDF whose text pypdf can extract."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + body + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, xref,
    )
    with open(path, "wb") as fh:
        fh.write(bytes(out))


@pytest.fixture
def files(tmp_path):
    """One file of each interesting kind."""
    pdf = tmp_path / "doc.pdf"
    _write_pdf(str(pdf))
    (tmp_path / "clip.mp3").write_bytes(b"ID3\x03\x00\x00\x00" + b"\x00" * 64)
    (tmp_path / "notes.txt").write_text("meeting notes: ship it")
    (tmp_path / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    (tmp_path / "resume.docx").write_bytes(b"PK\x03\x04\x00\x01\x00\x00binary\x00blob")
    return tmp_path


@pytest.fixture
def caps(monkeypatch):
    """Stub the capability lookups so tests never depend on litellm's model map."""
    state = {"pdf": False, "audio": False}

    def fake(kind, model_name):
        return bool(state.get(kind))

    monkeypatch.setattr("praisonaiagents.agent.attachments._capability", fake)
    return state


# --- Non-image types now reach the model -----------------------------------

class TestPdfAttachments:
    def test_pdf_reaches_a_pdf_capable_model_as_a_file_part(self, files, caps):
        caps["pdf"] = True
        parts = build_attachment_parts(str(files / "doc.pdf"), "claude-sonnet-4")

        assert len(parts) == 1
        part = parts[0]
        assert part["type"] == "file"
        assert part["file"]["filename"] == "doc.pdf"
        assert part["file"]["file_data"].startswith("data:application/pdf;base64,")
        # Round-trips to the bytes on disk.
        import base64
        encoded = part["file"]["file_data"].split(",", 1)[1]
        assert base64.b64decode(encoded) == (files / "doc.pdf").read_bytes()

    def test_pdf_degrades_visibly_to_text_when_model_cannot_take_pdfs(
        self, files, caps, caplog
    ):
        caps["pdf"] = False
        with caplog.at_level("WARNING"):
            parts = build_attachment_parts(str(files / "doc.pdf"), "gpt-3.5-turbo")

        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        text = parts[0]["text"]
        # The degrade is announced to the model, names the file, and carries
        # the real content -- not a silent substitution.
        assert "doc.pdf" in text
        assert "extracted locally" in text
        assert "Hello PDF world" in text
        assert "gpt-3.5-turbo" in caplog.text

    def test_pdf_with_no_extractor_is_surfaced_not_swallowed(
        self, files, caps, caplog, monkeypatch
    ):
        caps["pdf"] = False
        monkeypatch.setattr(
            "praisonaiagents.agent.attachments._extract_pdf_text", lambda p: None
        )
        with caplog.at_level("WARNING"):
            parts = build_attachment_parts(str(files / "doc.pdf"), "gpt-3.5-turbo")

        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert "doc.pdf" in parts[0]["text"]
        assert "omitted" in parts[0]["text"].lower()
        assert "doc.pdf" in caplog.text
        assert "pypdf" in caplog.text


class TestAudioAttachments:
    def test_audio_reaches_an_audio_capable_model_as_input_audio(self, files, caps):
        caps["audio"] = True
        parts = build_attachment_parts(str(files / "clip.mp3"), "gpt-4o-audio-preview")

        assert len(parts) == 1
        part = parts[0]
        assert part["type"] == "input_audio"
        assert part["input_audio"]["format"] == "mp3"
        import base64
        assert base64.b64decode(part["input_audio"]["data"]) == (
            files / "clip.mp3"
        ).read_bytes()
        # Raw base64, not a data URI -- that is the OpenAI input_audio shape.
        assert not part["input_audio"]["data"].startswith("data:")

    def test_audio_on_a_text_only_model_warns_and_marks_the_prompt(
        self, files, caps, caplog
    ):
        caps["audio"] = False
        with caplog.at_level("WARNING"):
            parts = build_attachment_parts(str(files / "clip.mp3"), "gpt-4o")

        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert "clip.mp3" in parts[0]["text"]
        assert "clip.mp3" in caplog.text
        assert "cannot accept audio input" in caplog.text


class TestTextAttachments:
    def test_plain_text_file_is_inlined_and_labelled(self, files, caps):
        parts = build_attachment_parts(str(files / "notes.txt"), "gpt-4o")

        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert "notes.txt" in parts[0]["text"]
        assert "meeting notes: ship it" in parts[0]["text"]

    def test_long_text_truncation_is_announced(self, tmp_path, caps):
        from praisonaiagents.agent import attachments as att

        big = tmp_path / "big.txt"
        big.write_text("x" * (att.MAX_INLINE_TEXT_CHARS + 500))
        parts = build_attachment_parts(str(big), "gpt-4o")

        assert "truncated" in parts[0]["text"]
        assert "500 more characters" in parts[0]["text"]


# --- Failures are loud -----------------------------------------------------

class TestFailuresAreLoud:
    def test_nonexistent_path_raises_naming_the_path(self, caps):
        with pytest.raises(AttachmentError) as exc:
            build_attachment_parts("/no/such/typoed-report.pdf", "gpt-4o")
        assert "/no/such/typoed-report.pdf" in str(exc.value)

    def test_directory_raises_naming_the_path(self, files, caps):
        with pytest.raises(AttachmentError) as exc:
            build_attachment_parts(str(files), "gpt-4o")
        assert str(files) in str(exc.value)
        assert "directory" in str(exc.value)

    def test_missing_path_can_be_downgraded_to_a_visible_warning(
        self, caps, caplog, monkeypatch
    ):
        monkeypatch.setenv("PRAISONAI_ATTACHMENTS_ON_MISSING", "warn")
        with caplog.at_level("WARNING"):
            parts = build_attachment_parts("/no/such/typoed-report.pdf", "gpt-4o")
        assert len(parts) == 1
        assert "/no/such/typoed-report.pdf" in parts[0]["text"]
        assert "/no/such/typoed-report.pdf" in caplog.text

    def test_unsupported_binary_type_is_surfaced(self, files, caps, caplog):
        with caplog.at_level("WARNING"):
            parts = build_attachment_parts(str(files / "resume.docx"), "gpt-4o")

        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert "resume.docx" in parts[0]["text"]
        assert "unsupported" in parts[0]["text"].lower()
        assert "resume.docx" in caplog.text

    def test_strict_mode_escalates_an_unsupported_type_to_a_raise(
        self, files, caps, monkeypatch
    ):
        monkeypatch.setenv("PRAISONAI_ATTACHMENTS_STRICT", "1")
        with pytest.raises(AttachmentError) as exc:
            build_attachment_parts(str(files / "resume.docx"), "gpt-4o")
        assert "resume.docx" in str(exc.value)

    def test_video_is_surfaced_not_dropped(self, tmp_path, caps, caplog):
        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
        with caplog.at_level("WARNING"):
            parts = build_attachment_parts(str(clip), "gpt-4o")
        assert len(parts) == 1
        assert "clip.mp4" in parts[0]["text"]
        assert "clip.mp4" in caplog.text

    def test_wrong_python_type_raises(self, caps):
        with pytest.raises(AttachmentError) as exc:
            build_attachment_parts(42, "gpt-4o")
        assert "42" in str(exc.value)

    def test_pathlib_path_is_accepted(self, files, caps):
        parts = build_attachment_parts(files / "p.png", "gpt-4o")
        assert parts[0]["type"] == "image_url"

    def test_remote_pdf_url_is_surfaced_not_passed_off_as_an_image(self, caps, caplog):
        with caplog.at_level("WARNING"):
            parts = build_attachment_parts("https://example.com/report.pdf", "gpt-4o")
        assert parts[0]["type"] == "text"
        assert "report.pdf" in parts[0]["text"]
        assert "report.pdf" in caplog.text


# --- Controls: images and no-attachments are unchanged ---------------------

class TestImagesUnchanged:
    def test_local_image_still_produces_the_same_image_url_part(self, files, caps):
        import base64

        parts = build_attachment_parts(str(files / "p.png"), "gpt-4o")
        expected = base64.b64encode((files / "p.png").read_bytes()).decode()

        assert parts == [{
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{expected}"},
        }]

    @pytest.mark.parametrize(
        "name,mime",
        [("a.jpg", "image/jpeg"), ("a.jpeg", "image/jpeg"), ("a.gif", "image/gif"),
         ("a.webp", "image/webp")],
    )
    def test_every_supported_image_extension_keeps_its_media_type(
        self, tmp_path, caps, name, mime
    ):
        path = tmp_path / name
        path.write_bytes(b"\x00\x01\x02")
        parts = build_attachment_parts(str(path), "gpt-3.5-turbo")
        assert parts[0]["image_url"]["url"].startswith(f"data:{mime};base64,")

    def test_image_url_passthrough_unchanged(self, caps):
        parts = build_attachment_parts("https://example.com/cat.jpg", "gpt-4o")
        assert parts == [{
            "type": "image_url",
            "image_url": {"url": "https://example.com/cat.jpg"},
        }]

    def test_extensionless_url_still_treated_as_an_image(self, caps):
        parts = build_attachment_parts("https://example.com/photo", "gpt-4o")
        assert parts[0]["type"] == "image_url"

    def test_image_data_uri_passthrough_unchanged(self, caps):
        uri = "data:image/png;base64,AAAA"
        assert build_attachment_parts(uri, "gpt-4o") == [
            {"type": "image_url", "image_url": {"url": uri}}
        ]

    def test_structured_dict_passthrough_unchanged(self, caps):
        part = {"type": "text", "text": "already a part"}
        assert build_attachment_parts(part, "gpt-4o") == [part]


# --- End-to-end through the agent helper, with a stubbed LLM ---------------

class _StubLLM:
    """Stands in for ``agent.llm_instance``; records the prompt it was given."""

    def __init__(self, model):
        self.model = model


@pytest.fixture
def agent():
    from praisonaiagents import Agent
    return Agent(instructions="Test agent", llm="gpt-4o")


class TestBuildMultimodalPromptEndToEnd:
    def test_no_attachments_returns_the_plain_string(self, agent):
        assert agent._build_multimodal_prompt("Hello", None) == "Hello"
        assert agent._build_multimodal_prompt("Hello", []) == "Hello"

    def test_mixed_attachments_all_produce_parts(self, agent, files, caps):
        caps["pdf"] = True
        content = agent._build_multimodal_prompt(
            "summarise these",
            [
                str(files / "doc.pdf"),
                str(files / "clip.mp3"),
                str(files / "notes.txt"),
                str(files / "p.png"),
            ],
        )

        assert isinstance(content, list)
        # text prompt + one part per attachment: nothing dropped.
        assert len(content) == 5
        assert content[0] == {"type": "text", "text": "summarise these"}
        assert [p["type"] for p in content[1:]] == [
            "file", "text", "text", "image_url",
        ]

    def test_pdf_no_longer_vanishes(self, agent, files, caps):
        """The original defect, stated directly."""
        caps["pdf"] = True
        content = agent._build_multimodal_prompt(
            "summarise this", [str(files / "doc.pdf")]
        )
        assert len(content) == 2, "PDF attachment was dropped"
        assert content[1]["type"] == "file"

    def test_typoed_path_raises_through_the_agent_helper(self, agent, caps):
        with pytest.raises(AttachmentError) as exc:
            agent._build_multimodal_prompt("summarise this", ["repot.pdf"])
        assert "repot.pdf" in str(exc.value)

    def test_model_name_is_taken_from_the_agent(self, agent, files, monkeypatch):
        seen = []

        def fake(kind, model_name):
            seen.append((kind, model_name))
            return False

        monkeypatch.setattr("praisonaiagents.agent.attachments._capability", fake)
        agent._build_multimodal_prompt("x", [str(files / "clip.mp3")])
        assert seen == [("audio", "gpt-4o")]

    def test_model_name_prefers_llm_instance(self, agent, files, monkeypatch):
        from praisonaiagents.agent.attachments import resolve_attachment_model_name

        agent.llm_instance = _StubLLM("claude-sonnet-4")
        assert resolve_attachment_model_name(agent) == "claude-sonnet-4"


def test_capability_probe_survives_a_broken_litellm(monkeypatch, files):
    """A capability lookup that explodes must not take the whole run down."""
    from praisonaiagents.agent import attachments as att

    def boom(model_name):
        raise RuntimeError("litellm exploded")

    monkeypatch.setattr(
        "praisonaiagents.llm.model_capabilities.supports_pdf_input", boom
    )
    parts = att.build_attachment_parts(str(files / "doc.pdf"), "gpt-4o")
    assert len(parts) == 1  # degraded, not crashed
    assert parts[0]["type"] == "text"


def test_no_attachment_type_is_silently_dropped(files, caps):
    """Belt and braces: every input shape yields at least one part or raises."""
    inputs = [
        str(files / "doc.pdf"), str(files / "clip.mp3"), str(files / "notes.txt"),
        str(files / "p.png"), str(files / "resume.docx"),
        "https://example.com/cat.jpg", "data:image/png;base64,AAAA",
    ]
    for item in inputs:
        parts = build_attachment_parts(item, "gpt-4o")
        assert parts, f"{item} produced no content part"


class TestResponsesApiTranslation:
    """A PDF part must survive the Chat Completions -> Responses API hop."""

    def test_file_part_becomes_input_file(self):
        from praisonaiagents.llm.openai_client import OpenAIClient

        out = OpenAIClient._build_responses_content([
            {"type": "text", "text": "summarise this"},
            {"type": "file", "file": {
                "filename": "doc.pdf",
                "file_data": "data:application/pdf;base64,AAAA",
            }},
        ])
        assert out == [
            {"type": "input_text", "text": "summarise this"},
            {"type": "input_file", "filename": "doc.pdf",
             "file_data": "data:application/pdf;base64,AAAA"},
        ]

    def test_image_part_translation_unchanged(self):
        from praisonaiagents.llm.openai_client import OpenAIClient

        out = OpenAIClient._build_responses_content([
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ])
        assert out == [
            {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
        ]
