"""
TDD Tests for ConditionProtocol.

These tests define the expected behavior BEFORE implementation.
All tests should FAIL initially, then PASS after implementation.
"""
from typing import Dict, Any


class TestConditionProtocolExists:
    """Test that ConditionProtocol can be imported."""
    
    def test_condition_protocol_importable(self):
        """ConditionProtocol should be importable from conditions module."""
        from praisonaiagents.conditions.protocols import ConditionProtocol
        assert ConditionProtocol is not None
    
    def test_condition_protocol_is_runtime_checkable(self):
        """ConditionProtocol should be runtime_checkable."""
        from praisonaiagents.conditions.protocols import ConditionProtocol
        
        # Create a mock that implements the protocol
        class MockCondition:
            def evaluate(self, context: Dict[str, Any]) -> bool:
                return True
        
        mock = MockCondition()
        assert isinstance(mock, ConditionProtocol)
    
    def test_condition_protocol_has_evaluate_method(self):
        """ConditionProtocol should define evaluate(context) -> bool."""
        from praisonaiagents.conditions.protocols import ConditionProtocol
        
        # Check that evaluate is defined
        assert hasattr(ConditionProtocol, 'evaluate')


class TestExpressionCondition:
    """Test ExpressionCondition class for string-based conditions."""
    
    def test_expression_condition_importable(self):
        """ExpressionCondition should be importable."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        assert ExpressionCondition is not None
    
    def test_expression_condition_implements_protocol(self):
        """ExpressionCondition should implement ConditionProtocol."""
        from praisonaiagents.conditions.protocols import ConditionProtocol
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} > 80")
        assert isinstance(cond, ConditionProtocol)
    
    def test_numeric_greater_than(self):
        """Test numeric > comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} > 80")
        assert cond.evaluate({"score": 90}) is True
        assert cond.evaluate({"score": 80}) is False
        assert cond.evaluate({"score": 70}) is False
    
    def test_numeric_greater_equal(self):
        """Test numeric >= comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} >= 80")
        assert cond.evaluate({"score": 90}) is True
        assert cond.evaluate({"score": 80}) is True
        assert cond.evaluate({"score": 70}) is False
    
    def test_numeric_less_than(self):
        """Test numeric < comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} < 50")
        assert cond.evaluate({"score": 40}) is True
        assert cond.evaluate({"score": 50}) is False
        assert cond.evaluate({"score": 60}) is False
    
    def test_numeric_less_equal(self):
        """Test numeric <= comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} <= 50")
        assert cond.evaluate({"score": 40}) is True
        assert cond.evaluate({"score": 50}) is True
        assert cond.evaluate({"score": 60}) is False
    
    def test_numeric_equal(self):
        """Test numeric == comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} == 100")
        assert cond.evaluate({"score": 100}) is True
        assert cond.evaluate({"score": 99}) is False
    
    def test_numeric_not_equal(self):
        """Test numeric != comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} != 0")
        assert cond.evaluate({"score": 1}) is True
        assert cond.evaluate({"score": 0}) is False
    
    def test_string_equality(self):
        """Test string == comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{status}} == approved")
        assert cond.evaluate({"status": "approved"}) is True
        assert cond.evaluate({"status": "rejected"}) is False
    
    def test_string_not_equal(self):
        """Test string != comparison."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{status}} != rejected")
        assert cond.evaluate({"status": "approved"}) is True
        assert cond.evaluate({"status": "rejected"}) is False
    
    def test_contains_check(self):
        """Test 'in' contains check."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("error in {{message}}")
        assert cond.evaluate({"message": "An error occurred"}) is True
        assert cond.evaluate({"message": "Success!"}) is False
    
    def test_contains_keyword(self):
        """Test 'contains' keyword."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{message}} contains success")
        assert cond.evaluate({"message": "Operation success"}) is True
        assert cond.evaluate({"message": "Operation failed"}) is False
    
    def test_boolean_truthy(self):
        """Test boolean truthy evaluation."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{flag}}")
        assert cond.evaluate({"flag": True}) is True
        assert cond.evaluate({"flag": "yes"}) is True
        assert cond.evaluate({"flag": False}) is False
        assert cond.evaluate({"flag": ""}) is False
    
    def test_nested_property_access(self):
        """Test nested property access like {{item.score}}."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{item.score}} >= 60")
        assert cond.evaluate({"item": {"score": 75}}) is True
        assert cond.evaluate({"item": {"score": 50}}) is False
    
    def test_missing_variable_returns_false(self):
        """Test that missing variables don't crash, return False."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{missing}} > 0")
        assert cond.evaluate({}) is False


class TestDictCondition:
    """Test DictCondition class for dict-based routing conditions."""
    
    def test_dict_condition_importable(self):
        """DictCondition should be importable."""
        from praisonaiagents.conditions.evaluator import DictCondition
        assert DictCondition is not None
    
    def test_dict_condition_implements_protocol(self):
        """DictCondition should implement ConditionProtocol."""
        from praisonaiagents.conditions.protocols import ConditionProtocol
        from praisonaiagents.conditions.evaluator import DictCondition
        
        cond = DictCondition({"approved": ["task_a"]}, key="decision")
        assert isinstance(cond, ConditionProtocol)
    
    def test_dict_condition_matches_key(self):
        """Test dict condition matches decision key."""
        from praisonaiagents.conditions.evaluator import DictCondition
        
        cond = DictCondition(
            {"approved": ["publish"], "rejected": ["revise"]},
            key="decision"
        )
        assert cond.evaluate({"decision": "approved"}) is True
        assert cond.evaluate({"decision": "rejected"}) is True
        assert cond.evaluate({"decision": "unknown"}) is False
    
    def test_dict_condition_returns_target(self):
        """Test dict condition can return target tasks."""
        from praisonaiagents.conditions.evaluator import DictCondition
        
        cond = DictCondition(
            {"approved": ["publish"], "rejected": ["revise"]},
            key="decision"
        )
        assert cond.get_target({"decision": "approved"}) == ["publish"]
        assert cond.get_target({"decision": "rejected"}) == ["revise"]
        assert cond.get_target({"decision": "unknown"}) == []


class TestEvaluateConditionFunction:
    """Test the standalone evaluate_condition() function."""
    
    def test_evaluate_condition_importable(self):
        """evaluate_condition should be importable."""
        from praisonaiagents.conditions.evaluator import evaluate_condition
        assert evaluate_condition is not None
    
    def test_evaluate_condition_string(self):
        """Test evaluate_condition with string condition."""
        from praisonaiagents.conditions.evaluator import evaluate_condition
        
        result = evaluate_condition("{{score}} > 80", {"score": 90})
        assert result is True
    
    def test_evaluate_condition_with_previous_output(self):
        """Test evaluate_condition with previous_output substitution."""
        from praisonaiagents.conditions.evaluator import evaluate_condition
        
        result = evaluate_condition(
            "success in {{previous_output}}",
            {},
            previous_output="Operation success"
        )
        assert result is True


class TestConditionExports:
    """Test that conditions are properly exported."""
    
    def test_exports_from_conditions_module(self):
        """Test exports from conditions module."""
        from praisonaiagents.conditions import (
            ConditionProtocol,
            ExpressionCondition,
            DictCondition,
            evaluate_condition,
        )
        assert ConditionProtocol is not None
        assert ExpressionCondition is not None
        assert DictCondition is not None
        assert evaluate_condition is not None
    
    def test_exports_from_main_package(self):
        """Test exports from main praisonaiagents package."""
        from praisonaiagents import ConditionProtocol, evaluate_condition
        assert ConditionProtocol is not None
        assert evaluate_condition is not None
