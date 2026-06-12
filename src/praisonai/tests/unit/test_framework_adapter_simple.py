"""
Simplified unit tests for BaseFrameworkAdapter._resolve_llm() IndexError guard.

Focuses on the core regression test: IndexError prevention with empty llm_config.
"""

import unittest
from unittest.mock import Mock, patch


class TestBaseFrameworkAdapterIndexErrorFix(unittest.TestCase):
    """Test that BaseFrameworkAdapter._resolve_llm() prevents IndexError."""

    def setUp(self):
        """Set up test fixtures."""
        from praisonai.framework_adapters.base import BaseFrameworkAdapter
        self.adapter = BaseFrameworkAdapter()

    def test_resolve_llm_empty_llm_config_no_crash(self):
        """Test that empty llm_config lists don't cause IndexError."""
        # This is the core regression test for the IndexError bug
        with patch('praisonai.inc.PraisonAIModel') as mock_model_class:
            mock_instance = Mock()
            mock_model_class.return_value = mock_instance
            mock_instance.get_model.return_value = "test_model"
            
            # Before the fix: this would raise IndexError on llm_config[0]
            # After the fix: should handle empty list gracefully
            try:
                result = self.adapter._resolve_llm("gpt-4o-mini", [])
                indexerror_fixed = True
            except IndexError:
                indexerror_fixed = False
            
            self.assertTrue(indexerror_fixed, "Empty llm_config should not cause IndexError")
            
            # Verify the method completed and returned a result
            self.assertEqual(result, "test_model")

    def test_resolve_llm_none_llm_config_no_crash(self):
        """Test that None llm_config doesn't cause IndexError."""
        with patch('praisonai.inc.PraisonAIModel') as mock_model_class:
            mock_instance = Mock()
            mock_model_class.return_value = mock_instance
            mock_instance.get_model.return_value = "test_model"
            
            # Before the fix: this would raise IndexError on llm_config[0] 
            # After the fix: should handle None gracefully
            try:
                result = self.adapter._resolve_llm("gpt-4o-mini", None)
                indexerror_fixed = True
            except (IndexError, TypeError):
                indexerror_fixed = False
            
            self.assertTrue(indexerror_fixed, "None llm_config should not cause IndexError")
            
            # Verify method returns result
            self.assertEqual(result, "test_model")

    def test_resolve_llm_guards_check_length_before_access(self):
        """Test that _resolve_llm checks llm_config length before accessing [0]."""
        # This tests the specific fix: checking (llm_config and len(llm_config) > 0)
        with patch('praisonai.inc.PraisonAIModel') as mock_model_class:
            mock_instance = Mock()
            mock_model_class.return_value = mock_instance
            mock_instance.get_model.return_value = "test_model"
            
            # Test various edge cases that should not crash
            test_cases = [
                [],              # Empty list
                None,            # None value
                [{}],           # List with empty dict
                [{"other_key": "value"}]  # List with dict without expected keys
            ]
            
            for llm_config in test_cases:
                with self.subTest(llm_config=llm_config):
                    try:
                        result = self.adapter._resolve_llm("gpt-4o", llm_config)
                        # Should complete without IndexError
                        self.assertEqual(result, "test_model")
                        safe_access = True
                    except IndexError:
                        safe_access = False
                    
                    self.assertTrue(safe_access, f"llm_config {llm_config} should be handled safely")

    def test_resolve_llm_extracts_base_url_and_api_key_when_present(self):
        """Test that base_url and api_key are extracted when llm_config is valid."""
        with patch('praisonai.inc.PraisonAIModel') as mock_model_class:
            mock_instance = Mock()
            mock_model_class.return_value = mock_instance
            mock_instance.get_model.return_value = "test_model"
            
            # Test with valid llm_config
            llm_config = [{"base_url": "https://test.api", "api_key": "test-key"}]
            result = self.adapter._resolve_llm("gpt-4o", llm_config)
            
            # Verify PraisonAIModel was called with extracted values
            mock_model_class.assert_called_with(
                model="gpt-4o",
                base_url="https://test.api", 
                api_key="test-key"
            )

    def test_crewai_adapter_string_llm_compatibility(self):
        """Test that CrewAI adapter can handle string llm specs without crashing."""
        # This is a basic smoke test for string llm support in CrewAI adapter
        try:
            from praisonai.framework_adapters.crewai_adapter import CrewAIAdapter
            adapter = CrewAIAdapter()
            
            # Test that the adapter has the _resolve_llm method (indicating it uses the fix)
            has_resolve_llm = hasattr(adapter, '_resolve_llm')
            self.assertTrue(has_resolve_llm, "CrewAI adapter should inherit _resolve_llm method")
            
            # Basic smoke test - adapter should not crash on instantiation
            crewai_works = True
        except Exception:
            crewai_works = False
        
        self.assertTrue(crewai_works, "CrewAI adapter should be importable and instantiable")


if __name__ == '__main__':
    unittest.main()