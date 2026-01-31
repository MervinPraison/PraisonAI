"""Unit tests for BaseEvaluator class."""

import pytest
import tempfile
import json
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from praisonaiagents.eval.base import BaseEvaluator


class ConcreteEvaluator(BaseEvaluator):
    """Concrete implementation for testing."""
    
    def run(self, **kwargs):
        return {"test": "result"}


class TestBaseEvaluator:
    """Tests for BaseEvaluator abstract class."""
    
    def test_init_default_values(self):
        """Test default initialization values."""
        evaluator = ConcreteEvaluator()
        assert evaluator.name.startswith("eval_")
        assert evaluator.eval_id is not None
        assert len(evaluator.eval_id) == 8
        assert evaluator.save_results_path is None
        assert evaluator.verbose is False
    
    def test_init_custom_values(self):
        """Test initialization with custom values."""
        evaluator = ConcreteEvaluator(
            name="my_eval",
            save_results_path="/tmp/results.json",
            verbose=True
        )
        assert evaluator.name == "my_eval"
        assert evaluator.save_results_path == "/tmp/results.json"
        assert evaluator.verbose is True
    
    def test_eval_id_unique(self):
        """Test that each evaluator gets a unique ID."""
        eval1 = ConcreteEvaluator()
        eval2 = ConcreteEvaluator()
        assert eval1.eval_id != eval2.eval_id
    
    def test_before_run_verbose(self):
        """Test before_run hook with verbose logging."""
        # Reload module and create fresh class to get correct logger binding
        import praisonaiagents.eval.base as eval_base
        importlib.reload(eval_base)
        
        class FreshEvaluator(eval_base.BaseEvaluator):
            def run(self, **kwargs): return {}
        
        evaluator = FreshEvaluator(verbose=True)
        with patch.object(eval_base, 'logger') as mock_logger:
            evaluator.before_run()
            mock_logger.info.assert_called()
    
    def test_after_run_verbose(self):
        """Test after_run hook with verbose logging."""
        # Reload module and create fresh class to get correct logger binding
        import praisonaiagents.eval.base as eval_base
        importlib.reload(eval_base)
        
        class FreshEvaluator(eval_base.BaseEvaluator):
            def run(self, **kwargs): return {}
        
        evaluator = FreshEvaluator(verbose=True)
        with patch.object(eval_base, 'logger') as mock_logger:
            evaluator.after_run({"result": "test"})
            mock_logger.info.assert_called()
    
    def test_save_result_to_file(self):
        """Test saving results to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/results.json"
            evaluator = ConcreteEvaluator(
                name="test_save",
                save_results_path=path
            )
            
            result = MagicMock()
            result.to_dict.return_value = {"score": 8.0}
            
            evaluator._save_result(result)
            
            assert Path(path).exists()
            with open(path) as f:
                data = json.load(f)
            assert data["score"] == 8.0
    
    def test_save_result_with_placeholders(self):
        """Test saving results with path placeholders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/{{name}}_{{eval_id}}.json"
            evaluator = ConcreteEvaluator(
                name="test_eval",
                save_results_path=path
            )
            
            result = MagicMock()
            result.to_dict.return_value = {"score": 8.0}
            
            evaluator._save_result(result)
            
            expected_path = f"{tmpdir}/test_eval_{evaluator.eval_id}.json"
            assert Path(expected_path).exists()
    
    def test_save_result_creates_directories(self):
        """Test that save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/nested/dir/results.json"
            evaluator = ConcreteEvaluator(save_results_path=path)
            
            result = MagicMock()
            result.to_dict.return_value = {"score": 8.0}
            
            evaluator._save_result(result)
            
            assert Path(path).exists()
    
    def test_run_abstract_method(self):
        """Test that run method works in concrete implementation."""
        evaluator = ConcreteEvaluator()
        result = evaluator.run()
        assert result == {"test": "result"}
    
    @pytest.mark.asyncio
    async def test_run_async_default(self):
        """Test default async run calls sync run."""
        evaluator = ConcreteEvaluator()
        result = await evaluator.run_async()
        assert result == {"test": "result"}
    
    @pytest.mark.asyncio
    async def test_async_before_run(self):
        """Test async before_run hook."""
        # Reload module and create fresh class to get correct logger binding
        import praisonaiagents.eval.base as eval_base
        importlib.reload(eval_base)
        
        class FreshEvaluator(eval_base.BaseEvaluator):
            def run(self, **kwargs): return {}
        
        evaluator = FreshEvaluator(verbose=True)
        with patch.object(eval_base, 'logger') as mock_logger:
            await evaluator.async_before_run()
            mock_logger.info.assert_called()
    
    @pytest.mark.asyncio
    async def test_async_after_run(self):
        """Test async after_run hook."""
        # Reload module and create fresh class to get correct logger binding
        import praisonaiagents.eval.base as eval_base
        importlib.reload(eval_base)
        
        class FreshEvaluator(eval_base.BaseEvaluator):
            def run(self, **kwargs): return {}
        
        evaluator = FreshEvaluator(verbose=True)
        with patch.object(eval_base, 'logger') as mock_logger:
            await evaluator.async_after_run({"result": "test"})
            mock_logger.info.assert_called()
    
    def test_repr(self):
        """Test string representation."""
        evaluator = ConcreteEvaluator(name="test_eval")
        repr_str = repr(evaluator)
        assert "ConcreteEvaluator" in repr_str
        assert "test_eval" in repr_str
        assert evaluator.eval_id in repr_str
