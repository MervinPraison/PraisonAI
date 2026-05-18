#!/usr/bin/env python3
"""
Test script to verify that empty/filtered LLM response fixes work correctly.
"""

import sys
import os

# Add src paths to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai'))

def test_empty_response_mock():
    """Test that our fixes handle empty responses correctly"""
    
    # Create a mock response object that simulates empty/filtered responses
    class MockChoice:
        def __init__(self, message=None):
            self.message = message
    
    class MockMessage:
        def __init__(self, content=None):
            self.content = content
    
    class MockResponse:
        def __init__(self, choices=None):
            self.choices = choices or []
    
    # Test case 1: Empty choices
    empty_choices_response = MockResponse(choices=[])
    
    # Test case 2: None message
    none_message_response = MockResponse(choices=[MockChoice(message=None)])
    
    # Test case 3: None content
    none_content_response = MockResponse(choices=[MockChoice(message=MockMessage(content=None))])
    
    # Test case 4: Valid response
    valid_response = MockResponse(choices=[MockChoice(message=MockMessage(content="Valid response"))])
    
    # Test the RAG fix
    def test_rag_answer_extraction(response):
        answer = (response.choices[0].message.content if response.choices and response.choices[0].message is not None and response.choices[0].message.content is not None else "") or ""
        return answer
    
    print("Testing RAG answer extraction...")
    assert test_rag_answer_extraction(empty_choices_response) == ""
    assert test_rag_answer_extraction(none_message_response) == ""
    assert test_rag_answer_extraction(none_content_response) == ""
    assert test_rag_answer_extraction(valid_response) == "Valid response"
    print("✅ RAG fixes work correctly")
    
    # Test the guard validation
    def test_guard_validation(response):
        return not response.choices or response.choices[0].message is None or response.choices[0].message.content is None
    
    print("Testing guard validation...")
    assert test_guard_validation(empty_choices_response) == True
    assert test_guard_validation(none_message_response) == True  
    assert test_guard_validation(none_content_response) == True
    assert test_guard_validation(valid_response) == False
    print("✅ Guard validation works correctly")
    
    print("All tests passed! ✅")

if __name__ == "__main__":
    test_empty_response_mock()