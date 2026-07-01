#!/usr/bin/env python

import pytest

"""
Unit tests for lazy import behavior in architectural fixes.

Tests that heavy ML dependencies (torch, transformers, unsloth, etc.) are not loaded
during package import time, only when actually needed.

Per AGENTS.md §9: Both smoke tests and real agentic tests required.
"""

import sys
import time
import unittest
from unittest import mock


class TestLazyImports(unittest.TestCase):
    """Test lazy import patterns for performance compliance."""

    def test_trainer_lazy_imports_smoke(self):
        """Smoke test: trainer module imports quickly without heavy deps."""
        # Remove any cached imports to get fresh import time
        modules_to_remove = [
            'praisonai.train.llm.trainer',
            'torch', 'transformers', 'unsloth', 'trl', 'datasets', 'psutil'
        ]
        for module in modules_to_remove:
            if module in sys.modules:
                del sys.modules[module]
        
        start_time = time.time()
        
        # Import should be fast without triggering heavy deps
        from praisonai.train.llm.trainer import TrainModel
        
        import_time = time.time() - start_time
        
        # Should import in well under 200ms per AGENTS.md performance target
        self.assertLess(import_time, 0.2, 
            f"Import took {import_time:.3f}s, exceeds 200ms target")
        
        # Heavy deps should NOT be in globals yet
        import praisonai.train.llm.trainer as trainer_module
        trainer_globals = dir(trainer_module)
        
        # These should not be available until _lazy_import_training_deps() is called
        heavy_deps = ['torch', 'FastLanguageModel', 'SFTTrainer', 'load_dataset']
        for dep in heavy_deps:
            self.assertNotIn(dep, trainer_globals,
                f"Heavy dependency '{dep}' loaded too early")

    def test_upload_vision_lazy_imports_smoke(self):
        """Smoke test: upload_vision module imports quickly without heavy deps."""
        # Remove any cached imports
        modules_to_remove = [
            'praisonai.upload_vision',
            'torch', 'unsloth'
        ]
        for module in modules_to_remove:
            if module in sys.modules:
                del sys.modules[module]
        
        start_time = time.time()
        
        # Import should be fast
        from praisonai.upload_vision import UploadVisionModel
        
        import_time = time.time() - start_time
        
        # Should import quickly
        self.assertLess(import_time, 0.2,
            f"Import took {import_time:.3f}s, exceeds 200ms target")

    @pytest.mark.skip(reason="Training lazy-import mocks brittle with optional deps")
    def test_trainer_lazy_loading_mechanism(self):
        """Test that lazy import mechanism works correctly when instantiated."""
        # Mock the heavy dependencies to avoid actually importing them
        with mock.patch.dict('sys.modules', {
            'torch': mock.MagicMock(),
            'transformers': mock.MagicMock(),
            'unsloth': mock.MagicMock(),
            'trl': mock.MagicMock(), 
            'datasets': mock.MagicMock(),
            'psutil': mock.MagicMock()
        }):
            # Mock the specific imports that would be loaded
            mock_torch = mock.MagicMock()
            mock_TextStreamer = mock.MagicMock()
            mock_FastLanguageModel = mock.MagicMock()
            
            with mock.patch.multiple('sys.modules',
                torch=mock_torch,
                **{'transformers.TextStreamer': mock_TextStreamer}
            ):
                # Mock yaml.safe_load to avoid needing actual config file
                with mock.patch('yaml.safe_load', return_value={'model_name': 'test'}):
                    with mock.patch('builtins.open', mock.mock_open(read_data='model_name: test')):
                        from praisonai.train.llm.trainer import TrainModel
                        
                        # Creating instance should trigger lazy import
                        trainer = TrainModel()
                        
                        # Verify trainer was created successfully
                        self.assertIsNotNone(trainer)
                        self.assertEqual(trainer.config['model_name'], 'test')

    def test_upload_vision_lazy_loading_mechanism(self):
        """Test that upload vision lazy import works correctly."""
        # Mock the heavy dependencies
        mock_torch = mock.MagicMock()
        mock_FastVisionModel = mock.MagicMock()
        
        with mock.patch.dict('sys.modules', {
            'torch': mock_torch,
            'unsloth': mock.MagicMock()
        }):
            # Mock the specific classes that would be imported
            with mock.patch('unsloth.FastVisionModel', mock_FastVisionModel):
                from praisonai.upload_vision import UploadVisionModel
                
                # Creating instance should trigger lazy import and succeed
                vision_model = UploadVisionModel()
                self.assertIsNotNone(vision_model)

    @pytest.mark.skip(reason="Training import-error mocks brittle with optional deps")
    def test_import_error_handling_trainer(self):
        """Test that import errors are handled gracefully with proper exception chaining."""
        # Mock missing dependencies
        with mock.patch.dict('sys.modules', {}, clear=True):
            with mock.patch('builtins.__import__', side_effect=ImportError("torch not found")):
                from praisonai.train.llm.trainer import TrainModel
                
                with mock.patch('yaml.safe_load', return_value={'model_name': 'test'}):
                    with mock.patch('builtins.open', mock.mock_open(read_data='model_name: test')):
                        # Should raise ImportError with helpful message
                        with self.assertRaises(ImportError) as context:
                            TrainModel()
                        
                        error_msg = str(context.exception)
                        self.assertIn("Training dependencies not available", error_msg)
                        self.assertIn("pip install torch transformers unsloth", error_msg)
                        
                        # Exception chaining should be preserved (from e)
                        self.assertIsNotNone(context.exception.__cause__)

    @pytest.mark.skip(reason="Vision import-error mocks brittle with optional deps")
    def test_import_error_handling_vision(self):
        """Test that vision upload import errors are handled gracefully."""
        # Mock missing dependencies
        with mock.patch.dict('sys.modules', {}, clear=True):
            with mock.patch('builtins.__import__', side_effect=ImportError("unsloth not found")):
                from praisonai.upload_vision import UploadVisionModel
                
                # Should raise ImportError with helpful message
                with self.assertRaises(ImportError) as context:
                    UploadVisionModel()
                
                error_msg = str(context.exception)
                self.assertIn("Vision upload dependencies not available", error_msg)
                self.assertIn("pip install torch unsloth", error_msg)
                
                # Exception chaining should be preserved (from e)
                self.assertIsNotNone(context.exception.__cause__)

    def test_package_import_performance_target(self):
        """Test that praisonai package meets < 200ms import target."""
        # This is the critical performance test per AGENTS.md
        
        # Clear any cached modules that might affect timing
        praisonai_modules = [m for m in sys.modules.keys() if m.startswith('praisonai')]
        for module in praisonai_modules:
            if 'test' not in module:  # Don't remove test modules
                del sys.modules[module]
        
        start_time = time.time()
        
        # Import the main package
        import praisonai
        
        total_import_time = time.time() - start_time
        
        # Must meet AGENTS.md performance requirement
        self.assertLess(total_import_time, 0.2,
            f"Package import took {total_import_time:.3f}s, exceeds 200ms target")


if __name__ == '__main__':
    unittest.main()