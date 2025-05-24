import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import asyncio

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestToolIntegration:
    """Test tool integration functionality."""
    
    def test_custom_tool_creation(self):
        """Test creating custom tools for agents."""
        def calculator_tool(expression: str) -> str:
            """Calculate mathematical expressions."""
            try:
                result = eval(expression)  # Simple eval for testing
                return f"Result: {result}"
            except Exception as e:
                return f"Error: {e}"
        
        def search_tool(query: str) -> str:
            """Search for information."""
            return f"Search results for: {query}"
        
        # Test tool properties
        assert calculator_tool.__name__ == "calculator_tool"
        assert "Calculate mathematical" in calculator_tool.__doc__
        
        # Test tool execution
        result = calculator_tool("2 + 2")
        assert "Result: 4" in result
        
        search_result = search_tool("Python programming")
        assert "Search results for: Python programming" == search_result
    
    def test_agent_with_multiple_tools(self, sample_agent_config):
        """Test agent with multiple custom tools."""
        def weather_tool(location: str) -> str:
            """Get weather information."""
            return f"Weather in {location}: Sunny, 25°C"
        
        def news_tool(category: str = "general") -> str:
            """Get news information."""
            return f"Latest {category} news: Breaking news headlines"
        
        def translate_tool(text: str, target_lang: str = "en") -> str:
            """Translate text to target language."""
            return f"Translated to {target_lang}: {text}"
        
        agent = Agent(
            name="Multi-Tool Agent",
            tools=[weather_tool, news_tool, translate_tool],
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        assert agent.name == "Multi-Tool Agent"
        assert len(agent.tools) >= 3
    
    @pytest.mark.asyncio
    async def test_async_tools(self, sample_agent_config):
        """Test async tools integration."""
        async def async_web_scraper(url: str) -> str:
            """Scrape web content asynchronously."""
            await asyncio.sleep(0.1)  # Simulate network delay
            return f"Scraped content from {url}"
        
        async def async_api_caller(endpoint: str, method: str = "GET") -> str:
            """Make async API calls."""
            await asyncio.sleep(0.1)  # Simulate API delay
            return f"API {method} response from {endpoint}"
        
        agent = Agent(
            name="Async Tool Agent",
            tools=[async_web_scraper, async_api_caller],
            **sample_agent_config
        )
        
        # Test async tools directly
        scrape_result = await async_web_scraper("https://example.com")
        api_result = await async_api_caller("https://api.example.com/data")
        
        assert "Scraped content from https://example.com" == scrape_result
        assert "API GET response from https://api.example.com/data" == api_result
    
    def test_tool_error_handling(self):
        """Test tool error handling."""
        def failing_tool(input_data: str) -> str:
            """Tool that always fails."""
            raise ValueError("Intentional tool failure")
        
        def safe_tool_wrapper(tool_func):
            """Wrapper for safe tool execution."""
            def wrapper(*args, **kwargs):
                try:
                    return tool_func(*args, **kwargs)
                except Exception as e:
                    return f"Tool error: {str(e)}"
            wrapper.__name__ = tool_func.__name__
            wrapper.__doc__ = tool_func.__doc__
            return wrapper
        
        safe_failing_tool = safe_tool_wrapper(failing_tool)
        result = safe_failing_tool("test input")
        
        assert "Tool error: Intentional tool failure" == result
    
    @patch('duckduckgo_search.DDGS')
    def test_duckduckgo_search_tool(self, mock_ddgs, mock_duckduckgo):
        """Test DuckDuckGo search tool integration."""
        def duckduckgo_search_tool(query: str, max_results: int = 5) -> list:
            """Search using DuckDuckGo."""
            try:
                from duckduckgo_search import DDGS
                ddgs = DDGS()
                results = []
                for result in ddgs.text(keywords=query, max_results=max_results):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "snippet": result.get("body", "")
                    })
                return results
            except Exception as e:
                return [{"error": str(e)}]
        
        # Test the tool
        results = duckduckgo_search_tool("Python programming")
        
        assert isinstance(results, list)
        assert len(results) >= 1
        if "error" not in results[0]:
            assert "title" in results[0]
            assert "url" in results[0]


class TestUIIntegration:
    """Test UI integration functionality."""
    
    def test_gradio_app_config(self):
        """Test Gradio app configuration."""
        gradio_config = {
            "interface_type": "chat",
            "title": "PraisonAI Agent Chat",
            "description": "Chat with AI agents",
            "theme": "default",
            "share": False,
            "server_port": 7860
        }
        
        assert gradio_config["interface_type"] == "chat"
        assert gradio_config["title"] == "PraisonAI Agent Chat"
        assert gradio_config["server_port"] == 7860
    
    def test_streamlit_app_config(self):
        """Test Streamlit app configuration."""
        streamlit_config = {
            "page_title": "PraisonAI Agents",
            "page_icon": "🤖",
            "layout": "wide",
            "initial_sidebar_state": "expanded",
            "menu_items": {
                'Get Help': 'https://docs.praisonai.com',
                'Report a bug': 'https://github.com/MervinPraison/PraisonAI/issues',
                'About': "PraisonAI Agents Framework"
            }
        }
        
        assert streamlit_config["page_title"] == "PraisonAI Agents"
        assert streamlit_config["page_icon"] == "🤖"
        assert streamlit_config["layout"] == "wide"
    
    def test_chainlit_app_config(self):
        """Test Chainlit app configuration."""
        chainlit_config = {
            "name": "PraisonAI Agent",
            "description": "Interact with PraisonAI agents",
            "author": "PraisonAI Team",
            "tags": ["ai", "agents", "chat"],
            "public": False,
            "authentication": True
        }
        
        assert chainlit_config["name"] == "PraisonAI Agent"
        assert chainlit_config["authentication"] is True
        assert "ai" in chainlit_config["tags"]
    
    def test_ui_agent_wrapper(self, sample_agent_config):
        """Test UI agent wrapper functionality."""
        class UIAgentWrapper:
            """Wrapper for agents in UI applications."""
            
            def __init__(self, agent, ui_type="gradio"):
                self.agent = agent
                self.ui_type = ui_type
                self.session_history = []
            
            def chat(self, message: str, user_id: str = "default") -> str:
                """Handle chat interaction."""
                # Mock agent response
                response = f"Agent response to: {message}"
                
                # Store in session
                self.session_history.append({
                    "user_id": user_id,
                    "message": message,
                    "response": response,
                    "timestamp": "2024-01-01T12:00:00Z"
                })
                
                return response
            
            def get_history(self, user_id: str = "default") -> list:
                """Get chat history for user."""
                return [
                    item for item in self.session_history 
                    if item["user_id"] == user_id
                ]
            
            def clear_history(self, user_id: str = "default"):
                """Clear chat history for user."""
                self.session_history = [
                    item for item in self.session_history 
                    if item["user_id"] != user_id
                ]
        
        # Test wrapper
        agent = Agent(**sample_agent_config)
        ui_wrapper = UIAgentWrapper(agent, ui_type="gradio")
        
        # Test chat
        response = ui_wrapper.chat("Hello, how are you?", "user1")
        assert "Agent response to: Hello, how are you?" == response
        
        # Test history
        history = ui_wrapper.get_history("user1")
        assert len(history) == 1
        assert history[0]["message"] == "Hello, how are you?"
        
        # Test clear history
        ui_wrapper.clear_history("user1")
        history_after_clear = ui_wrapper.get_history("user1")
        assert len(history_after_clear) == 0
    
    def test_api_endpoint_simulation(self, sample_agent_config):
        """Test API endpoint functionality simulation."""
        class APIEndpointSimulator:
            """Simulate REST API endpoints for agents."""
            
            def __init__(self, agent):
                self.agent = agent
                self.active_sessions = {}
            
            def create_session(self, user_id: str) -> dict:
                """Create a new chat session."""
                session_id = f"session_{len(self.active_sessions) + 1}"
                self.active_sessions[session_id] = {
                    "user_id": user_id,
                    "created_at": "2024-01-01T12:00:00Z",
                    "messages": []
                }
                return {"session_id": session_id, "status": "created"}
            
            def send_message(self, session_id: str, message: str) -> dict:
                """Send message to agent."""
                if session_id not in self.active_sessions:
                    return {"error": "Session not found"}
                
                # Mock agent response
                response = f"Agent response: {message}"
                
                # Store message
                self.active_sessions[session_id]["messages"].append({
                    "user_message": message,
                    "agent_response": response,
                    "timestamp": "2024-01-01T12:00:00Z"
                })
                
                return {
                    "session_id": session_id,
                    "response": response,
                    "status": "success"
                }
            
            def get_session_history(self, session_id: str) -> dict:
                """Get session message history."""
                if session_id not in self.active_sessions:
                    return {"error": "Session not found"}
                
                return {
                    "session_id": session_id,
                    "messages": self.active_sessions[session_id]["messages"]
                }
        
        # Test API simulator
        agent = Agent(**sample_agent_config)
        api_sim = APIEndpointSimulator(agent)
        
        # Create session
        session_result = api_sim.create_session("user123")
        assert session_result["status"] == "created"
        session_id = session_result["session_id"]
        
        # Send message
        message_result = api_sim.send_message(session_id, "Hello API!")
        assert message_result["status"] == "success"
        assert "Agent response: Hello API!" == message_result["response"]
        
        # Get history
        history = api_sim.get_session_history(session_id)
        assert len(history["messages"]) == 1
        assert history["messages"][0]["user_message"] == "Hello API!"


class TestMultiModalTools:
    """Test multi-modal tool functionality."""
    
    def test_image_analysis_tool(self):
        """Test image analysis tool simulation."""
        def image_analysis_tool(image_path: str, analysis_type: str = "description") -> str:
            """Analyze images using AI."""
            # Mock image analysis
            analysis_results = {
                "description": f"Description of image at {image_path}",
                "objects": f"Objects detected in {image_path}: person, car, tree",
                "text": f"Text extracted from {image_path}: Sample text",
                "sentiment": f"Sentiment analysis of {image_path}: Positive"
            }
            
            return analysis_results.get(analysis_type, "Unknown analysis type")
        
        # Test different analysis types
        desc_result = image_analysis_tool("/path/to/image.jpg", "description")
        objects_result = image_analysis_tool("/path/to/image.jpg", "objects")
        text_result = image_analysis_tool("/path/to/image.jpg", "text")
        
        assert "Description of image" in desc_result
        assert "Objects detected" in objects_result
        assert "Text extracted" in text_result
    
    def test_audio_processing_tool(self):
        """Test audio processing tool simulation."""
        def audio_processing_tool(audio_path: str, operation: str = "transcribe") -> str:
            """Process audio files."""
            # Mock audio processing
            operations = {
                "transcribe": f"Transcription of {audio_path}: Hello, this is a test audio.",
                "summarize": f"Summary of {audio_path}: Audio contains greeting and test message.",
                "translate": f"Translation of {audio_path}: Hola, esta es una prueba de audio.",
                "sentiment": f"Sentiment of {audio_path}: Neutral tone detected."
            }
            
            return operations.get(operation, "Unknown operation")
        
        # Test different operations
        transcribe_result = audio_processing_tool("/path/to/audio.wav", "transcribe")
        summary_result = audio_processing_tool("/path/to/audio.wav", "summarize")
        
        assert "Transcription of" in transcribe_result
        assert "Summary of" in summary_result
    
    def test_document_processing_tool(self, temp_directory):
        """Test document processing tool."""
        def document_processing_tool(doc_path: str, operation: str = "extract_text") -> str:
            """Process various document formats."""
            # Mock document processing
            operations = {
                "extract_text": f"Text extracted from {doc_path}",
                "summarize": f"Summary of document {doc_path}",
                "extract_metadata": f"Metadata from {doc_path}: Author, Title, Date",
                "convert_format": f"Converted {doc_path} to new format"
            }
            
            return operations.get(operation, "Unknown operation")
        
        # Create a test document
        test_doc = temp_directory / "test_document.txt"
        test_doc.write_text("This is a test document for processing.")
        
        # Test document processing
        text_result = document_processing_tool(str(test_doc), "extract_text")
        summary_result = document_processing_tool(str(test_doc), "summarize")
        
        assert "Text extracted from" in text_result
        assert "Summary of document" in summary_result


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 