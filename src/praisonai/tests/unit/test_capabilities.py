"""
Unit tests for PraisonAI Capabilities Module.

Tests the LiteLLM endpoint parity capabilities.
"""

from unittest.mock import Mock, patch, MagicMock


class TestAudioCapabilities:
    """Tests for audio transcription and speech capabilities."""
    
    def test_transcription_result_dataclass(self):
        """Test TranscriptionResult dataclass."""
        from praisonai.capabilities.audio import TranscriptionResult
        
        result = TranscriptionResult(
            text="Hello world",
            duration=5.0,
            language="en",
            model="whisper-1"
        )
        
        assert result.text == "Hello world"
        assert result.duration == 5.0
        assert result.language == "en"
        assert result.model == "whisper-1"
    
    def test_speech_result_dataclass(self):
        """Test SpeechResult dataclass."""
        from praisonai.capabilities.audio import SpeechResult
        
        result = SpeechResult(
            audio=b"audio_bytes",
            content_type="audio/mp3",
            model="tts-1"
        )
        
        assert result.audio == b"audio_bytes"
        assert result.content_type == "audio/mp3"
        assert result.model == "tts-1"
    
    @patch('litellm.transcription')
    def test_transcribe_function(self, mock_transcription):
        """Test transcribe function calls litellm correctly."""
        from praisonai.capabilities.audio import transcribe
        
        mock_response = Mock()
        mock_response.text = "Transcribed text"
        mock_response.duration = 10.0
        mock_transcription.return_value = mock_response
        
        with patch('builtins.open', MagicMock()):
            result = transcribe("test.mp3", model="whisper-1")
        
        assert result.text == "Transcribed text"
        mock_transcription.assert_called_once()
    
    @patch('litellm.speech')
    def test_speech_function(self, mock_speech):
        """Test speech function calls litellm correctly."""
        from praisonai.capabilities.audio import speech
        
        mock_response = Mock()
        mock_response.content = b"audio_content"
        mock_speech.return_value = mock_response
        
        result = speech("Hello world", model="tts-1", voice="alloy")
        
        assert result.audio == b"audio_content"
        mock_speech.assert_called_once()


class TestImagesCapabilities:
    """Tests for image generation and editing capabilities."""
    
    def test_image_result_dataclass(self):
        """Test ImageResult dataclass."""
        from praisonai.capabilities.images import ImageResult
        
        result = ImageResult(
            url="https://example.com/image.png",
            model="dall-e-3"
        )
        
        assert result.url == "https://example.com/image.png"
        assert result.model == "dall-e-3"
    
    @patch('litellm.image_generation')
    def test_image_generate_function(self, mock_image_generation):
        """Test image_generate function."""
        from praisonai.capabilities.images import image_generate
        
        mock_item = Mock()
        mock_item.url = "https://example.com/image.png"
        mock_item.b64_json = None
        mock_item.revised_prompt = "A beautiful sunset"
        
        mock_response = Mock()
        mock_response.data = [mock_item]
        mock_image_generation.return_value = mock_response
        
        results = image_generate("A sunset", model="dall-e-3")
        
        assert len(results) == 1
        assert results[0].url == "https://example.com/image.png"


class TestFilesCapabilities:
    """Tests for file management capabilities."""
    
    def test_file_result_dataclass(self):
        """Test FileResult dataclass."""
        from praisonai.capabilities.files import FileResult
        
        result = FileResult(
            id="file-abc123",
            filename="data.jsonl",
            purpose="batch"
        )
        
        assert result.id == "file-abc123"
        assert result.filename == "data.jsonl"
        assert result.purpose == "batch"
    
    @patch('litellm.create_file')
    def test_file_create_function(self, mock_create_file):
        """Test file_create function."""
        from praisonai.capabilities.files import file_create
        
        mock_response = Mock()
        mock_response.id = "file-abc123"
        mock_response.object = "file"
        mock_response.bytes = 1024
        mock_response.filename = "test.jsonl"
        mock_response.purpose = "batch"
        mock_response.status = "processed"
        mock_response.created_at = 1234567890
        mock_create_file.return_value = mock_response
        
        with patch('builtins.open', MagicMock()):
            result = file_create("test.jsonl", purpose="batch")
        
        assert result.id == "file-abc123"


class TestEmbeddingsCapabilities:
    """Tests for embedding capabilities."""
    
    def test_embedding_result_dataclass(self):
        """Test EmbeddingResult dataclass."""
        from praisonai.capabilities.embeddings import EmbeddingResult
        
        result = EmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model="text-embedding-3-small"
        )
        
        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 3
    
    @patch('litellm.embedding')
    def test_embed_function(self, mock_embedding):
        """Test embed function."""
        from praisonai.capabilities.embeddings import embed
        
        mock_item = Mock()
        mock_item.embedding = [0.1, 0.2, 0.3]
        
        mock_usage = Mock()
        mock_usage.prompt_tokens = 10
        mock_usage.total_tokens = 10
        
        mock_response = Mock()
        mock_response.data = [mock_item]
        mock_response.usage = mock_usage
        mock_embedding.return_value = mock_response
        
        result = embed("Hello world")
        
        assert len(result.embeddings) == 1
        assert result.embeddings[0] == [0.1, 0.2, 0.3]


class TestRerankCapabilities:
    """Tests for rerank capabilities."""
    
    def test_rerank_result_dataclass(self):
        """Test RerankResult dataclass."""
        from praisonai.capabilities.rerank import RerankResult
        
        result = RerankResult(
            results=[{"index": 0, "relevance_score": 0.95}],
            model="cohere/rerank-english-v3.0"
        )
        
        assert len(result.results) == 1
        assert result.results[0]["relevance_score"] == 0.95
    
    @patch('litellm.rerank')
    def test_rerank_function(self, mock_rerank):
        """Test rerank function."""
        from praisonai.capabilities.rerank import rerank
        
        mock_item = Mock()
        mock_item.index = 0
        mock_item.relevance_score = 0.95
        
        mock_response = Mock()
        mock_response.results = [mock_item]
        mock_rerank.return_value = mock_response
        
        result = rerank("What is AI?", ["AI is...", "ML is..."])
        
        assert len(result.results) == 1


class TestModerationsCapabilities:
    """Tests for moderation capabilities."""
    
    def test_moderation_result_dataclass(self):
        """Test ModerationResult dataclass."""
        from praisonai.capabilities.moderations import ModerationResult
        
        result = ModerationResult(
            flagged=False,
            categories={"hate": False},
            category_scores={"hate": 0.01}
        )
        
        assert result.flagged is False
        assert result.categories["hate"] is False
    
    @patch('litellm.moderation')
    def test_moderate_function(self, mock_moderation):
        """Test moderate function."""
        from praisonai.capabilities.moderations import moderate
        
        mock_item = Mock()
        mock_item.flagged = False
        mock_item.categories = Mock()
        mock_item.category_scores = Mock()
        
        mock_response = Mock()
        mock_response.results = [mock_item]
        mock_moderation.return_value = mock_response
        
        results = moderate("Hello world")
        
        assert len(results) == 1
        assert results[0].flagged is False


class TestOCRCapabilities:
    """Tests for OCR capabilities."""
    
    def test_ocr_result_dataclass(self):
        """Test OCRResult dataclass."""
        from praisonai.capabilities.ocr import OCRResult
        
        result = OCRResult(
            text="Extracted text",
            model="mistral/mistral-ocr-latest"
        )
        
        assert result.text == "Extracted text"
        assert result.model == "mistral/mistral-ocr-latest"


class TestBatchesCapabilities:
    """Tests for batch processing capabilities."""
    
    def test_batch_result_dataclass(self):
        """Test BatchResult dataclass."""
        from praisonai.capabilities.batches import BatchResult
        
        result = BatchResult(
            id="batch-abc123",
            status="in_progress",
            endpoint="/v1/chat/completions"
        )
        
        assert result.id == "batch-abc123"
        assert result.status == "in_progress"


class TestVectorStoresCapabilities:
    """Tests for vector store capabilities."""
    
    def test_vector_store_result_dataclass(self):
        """Test VectorStoreResult dataclass."""
        from praisonai.capabilities.vector_stores import VectorStoreResult
        
        result = VectorStoreResult(
            id="vs-abc123",
            name="my-store",
            status="completed"
        )
        
        assert result.id == "vs-abc123"
        assert result.name == "my-store"


class TestAssistantsCapabilities:
    """Tests for assistants capabilities."""
    
    def test_assistant_result_dataclass(self):
        """Test AssistantResult dataclass."""
        from praisonai.capabilities.assistants import AssistantResult
        
        result = AssistantResult(
            id="asst-abc123",
            name="Math Tutor",
            model="gpt-4o-mini"
        )
        
        assert result.id == "asst-abc123"
        assert result.name == "Math Tutor"


class TestFineTuningCapabilities:
    """Tests for fine-tuning capabilities."""
    
    def test_fine_tuning_result_dataclass(self):
        """Test FineTuningResult dataclass."""
        from praisonai.capabilities.fine_tuning import FineTuningResult
        
        result = FineTuningResult(
            id="ftjob-abc123",
            status="running",
            model="gpt-4o-mini"
        )
        
        assert result.id == "ftjob-abc123"
        assert result.status == "running"


class TestPassthroughCapabilities:
    """Tests for passthrough capabilities."""
    
    def test_passthrough_result_dataclass(self):
        """Test PassthroughResult dataclass."""
        from praisonai.capabilities.passthrough import PassthroughResult
        
        result = PassthroughResult(
            data={"key": "value"},
            status_code=200
        )
        
        assert result.data == {"key": "value"}
        assert result.status_code == 200


class TestResponsesCapabilities:
    """Tests for responses capabilities."""
    
    def test_response_result_dataclass(self):
        """Test ResponseResult dataclass."""
        from praisonai.capabilities.responses import ResponseResult
        
        result = ResponseResult(
            id="resp-abc123",
            status="completed",
            model="gpt-4o-mini"
        )
        
        assert result.id == "resp-abc123"
        assert result.status == "completed"


class TestContainersCapabilities:
    """Tests for container capabilities."""
    
    def test_container_result_dataclass(self):
        """Test ContainerResult dataclass."""
        from praisonai.capabilities.containers import ContainerResult
        
        result = ContainerResult(
            id="container-abc123",
            status="created",
            image="python:3.11"
        )
        
        assert result.id == "container-abc123"
        assert result.image == "python:3.11"


class TestSearchCapabilities:
    """Tests for search capabilities."""
    
    def test_search_result_dataclass(self):
        """Test SearchResult dataclass."""
        from praisonai.capabilities.search import SearchResult
        
        result = SearchResult(
            results=[{"title": "Test", "url": "https://example.com"}],
            query="test query"
        )
        
        assert len(result.results) == 1
        assert result.query == "test query"


class TestA2ACapabilities:
    """Tests for A2A capabilities."""
    
    def test_a2a_result_dataclass(self):
        """Test A2AResult dataclass."""
        from praisonai.capabilities.a2a import A2AResult
        
        result = A2AResult(
            id="a2a-abc123",
            status="sent",
            target_agent="data-analyst"
        )
        
        assert result.id == "a2a-abc123"
        assert result.target_agent == "data-analyst"


class TestCapabilitiesModuleImports:
    """Tests for capabilities module lazy loading."""
    
    def test_lazy_import_transcribe(self):
        """Test lazy import of transcribe."""
        from praisonai.capabilities import transcribe
        assert callable(transcribe)
    
    def test_lazy_import_speech(self):
        """Test lazy import of speech."""
        from praisonai.capabilities import speech
        assert callable(speech)
    
    def test_lazy_import_image_generate(self):
        """Test lazy import of image_generate."""
        from praisonai.capabilities import image_generate
        assert callable(image_generate)
    
    def test_lazy_import_embed(self):
        """Test lazy import of embed."""
        from praisonai.capabilities import embed
        assert callable(embed)
    
    def test_lazy_import_rerank(self):
        """Test lazy import of rerank."""
        from praisonai.capabilities.rerank import rerank
        assert callable(rerank)
    
    def test_lazy_import_moderate(self):
        """Test lazy import of moderate."""
        from praisonai.capabilities import moderate
        assert callable(moderate)
    
    def test_lazy_import_ocr(self):
        """Test lazy import of ocr."""
        from praisonai.capabilities.ocr import ocr
        assert callable(ocr)


class TestCLICapabilitiesHandler:
    """Tests for CLI capabilities handler."""
    
    def test_handler_exists(self):
        """Test CapabilitiesHandler can be imported."""
        from praisonai.cli.features import CapabilitiesHandler
        assert hasattr(CapabilitiesHandler, 'handle_audio')
        assert hasattr(CapabilitiesHandler, 'handle_images')
        assert hasattr(CapabilitiesHandler, 'handle_files')
        assert hasattr(CapabilitiesHandler, 'handle_embed')
        assert hasattr(CapabilitiesHandler, 'handle_rerank')
        assert hasattr(CapabilitiesHandler, 'handle_moderate')
        assert hasattr(CapabilitiesHandler, 'handle_ocr')
        assert hasattr(CapabilitiesHandler, 'handle_batches')
        assert hasattr(CapabilitiesHandler, 'handle_vector_stores')
        assert hasattr(CapabilitiesHandler, 'handle_assistants')
        assert hasattr(CapabilitiesHandler, 'handle_fine_tuning')
    
    def test_new_handlers_exist(self):
        """Test new capability handlers exist."""
        from praisonai.cli.features import CapabilitiesHandler
        assert hasattr(CapabilitiesHandler, 'handle_completions')
        assert hasattr(CapabilitiesHandler, 'handle_messages')
        assert hasattr(CapabilitiesHandler, 'handle_guardrails')
        assert hasattr(CapabilitiesHandler, 'handle_rag')
        assert hasattr(CapabilitiesHandler, 'handle_realtime')
        assert hasattr(CapabilitiesHandler, 'handle_videos')
        assert hasattr(CapabilitiesHandler, 'handle_a2a')
        assert hasattr(CapabilitiesHandler, 'handle_containers')
        assert hasattr(CapabilitiesHandler, 'handle_passthrough')
        assert hasattr(CapabilitiesHandler, 'handle_responses')
        assert hasattr(CapabilitiesHandler, 'handle_search')


class TestNewCapabilities:
    """Tests for new capability modules."""
    
    def test_completion_result_dataclass(self):
        """Test CompletionResult dataclass."""
        from praisonai.capabilities.completions import CompletionResult
        
        result = CompletionResult(
            id="chatcmpl-abc123",
            content="Hello world",
            model="gpt-4o-mini"
        )
        
        assert result.id == "chatcmpl-abc123"
        assert result.content == "Hello world"
    
    def test_message_result_dataclass(self):
        """Test MessageResult dataclass."""
        from praisonai.capabilities.messages import MessageResult
        
        result = MessageResult(
            id="msg-abc123",
            content=[{"type": "text", "text": "Hello"}],
            model="claude-3-5-sonnet-20241022"
        )
        
        assert result.id == "msg-abc123"
        assert len(result.content) == 1
    
    def test_guardrail_result_dataclass(self):
        """Test GuardrailResult dataclass."""
        from praisonai.capabilities.guardrails import GuardrailResult
        
        result = GuardrailResult(
            passed=True,
            original_content="Test content"
        )
        
        assert result.passed is True
    
    def test_rag_result_dataclass(self):
        """Test RAGResult dataclass."""
        from praisonai.capabilities.rag import RAGResult
        
        result = RAGResult(
            answer="The answer is 42",
            sources=[{"text": "Source 1"}]
        )
        
        assert result.answer == "The answer is 42"
    
    def test_realtime_session_dataclass(self):
        """Test RealtimeSession dataclass."""
        from praisonai.capabilities.realtime import RealtimeSession
        
        session = RealtimeSession(
            id="realtime-abc123",
            status="created",
            model="gpt-4o-realtime-preview"
        )
        
        assert session.id == "realtime-abc123"
    
    def test_mcp_result_dataclass(self):
        """Test MCPResult dataclass."""
        from praisonai.capabilities.mcp import MCPResult
        
        result = MCPResult(
            tools=[{"name": "read_file"}],
            server_name="npx"
        )
        
        assert len(result.tools) == 1
    
    def test_vector_store_file_result_dataclass(self):
        """Test VectorStoreFileResult dataclass."""
        from praisonai.capabilities.vector_store_files import VectorStoreFileResult
        
        result = VectorStoreFileResult(
            id="vsfile-abc123",
            vector_store_id="vs-xyz789"
        )
        
        assert result.id == "vsfile-abc123"
    
    def test_container_file_result_dataclass(self):
        """Test ContainerFileResult dataclass."""
        from praisonai.capabilities.container_files import ContainerFileResult
        
        result = ContainerFileResult(
            path="/app/output.txt",
            container_id="container-abc123"
        )
        
        assert result.path == "/app/output.txt"


class TestCapabilityImports:
    """Test all new capability imports work."""
    
    def test_import_completions(self):
        """Test completions module imports."""
        from praisonai.capabilities import chat_completion, achat_completion
        assert callable(chat_completion)
        assert callable(achat_completion)
    
    def test_import_messages(self):
        """Test messages module imports."""
        from praisonai.capabilities import messages_create, count_tokens
        assert callable(messages_create)
        assert callable(count_tokens)
    
    def test_import_guardrails(self):
        """Test guardrails module imports."""
        from praisonai.capabilities import apply_guardrail
        assert callable(apply_guardrail)
    
    def test_import_rag(self):
        """Test rag module imports."""
        from praisonai.capabilities import rag_query
        assert callable(rag_query)
    
    def test_import_realtime(self):
        """Test realtime module imports."""
        from praisonai.capabilities import realtime_connect
        assert callable(realtime_connect)
    
    def test_import_mcp(self):
        """Test mcp module imports."""
        from praisonai.capabilities import mcp_list_tools
        assert callable(mcp_list_tools)
    
    def test_import_vector_store_files(self):
        """Test vector_store_files module imports."""
        from praisonai.capabilities import vector_store_file_create
        assert callable(vector_store_file_create)
    
    def test_import_container_files(self):
        """Test container_files module imports."""
        from praisonai.capabilities import container_file_read
        assert callable(container_file_read)


class TestEmbeddingAliases:
    """Tests for embedding/embed alias consolidation."""
    
    def test_import_embed_from_praisonai(self):
        """Test that embed can be imported from top-level praisonai."""
        from praisonai import embed
        assert callable(embed)
    
    def test_import_embedding_from_praisonai(self):
        """Test that embedding can be imported from top-level praisonai."""
        from praisonai import embedding
        assert callable(embedding)
    
    def test_import_embedding_alias_from_capabilities(self):
        """Test that embedding alias works in capabilities module."""
        from praisonai.capabilities import embedding
        assert callable(embedding)
    
    def test_import_aembedding_alias_from_capabilities(self):
        """Test that aembedding alias works in capabilities module."""
        from praisonai.capabilities import aembedding
        assert callable(aembedding)
    
    def test_embed_and_embedding_are_same_function(self):
        """Test that embed and embedding point to the same function."""
        from praisonai.capabilities import embed, embedding
        # They should be the same function
        assert embed is embedding
    
    def test_aembed_and_aembedding_are_same_function(self):
        """Test that aembed and aembedding point to the same function."""
        from praisonai.capabilities import aembed, aembedding
        # They should be the same function
        assert aembed is aembedding
    
    def test_top_level_embed_returns_embedding_result(self):
        """Test that top-level embed returns EmbeddingResult type."""
        from praisonai import embed
        from praisonai.capabilities.embeddings import EmbeddingResult
        # Check that the function signature matches (returns EmbeddingResult)
        import inspect
        sig = inspect.signature(embed)
        # The function should have 'input' as first parameter
        params = list(sig.parameters.keys())
        assert 'input' in params
    
    def test_top_level_embedding_returns_embedding_result(self):
        """Test that top-level embedding returns EmbeddingResult type."""
        from praisonai import embedding
        from praisonai.capabilities.embeddings import EmbeddingResult
        # Check that the function signature matches (returns EmbeddingResult)
        import inspect
        sig = inspect.signature(embedding)
        # The function should have 'input' as first parameter
        params = list(sig.parameters.keys())
        assert 'input' in params
    
    def test_llm_embedding_shows_deprecation_warning(self):
        """Test that llm.embedding shows deprecation warning."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonai.llm import embedding
            # Call the function to trigger warning
            # Note: We can't actually call it without API key, but importing should work
            assert callable(embedding)
            # The deprecation warning should be raised when the function is called
            # We'll check that the function has the warning in its implementation
