"""
Integration tests for ConditionProtocol with AgentFlow and AgentTeam.

These tests verify that the shared condition evaluation works correctly
when used through the existing AgentFlow and AgentTeam APIs.
"""


class TestAgentFlowConditionIntegration:
    """Test that AgentFlow _evaluate_condition uses shared evaluator."""
    
    def test_agentflow_evaluate_condition_numeric(self):
        """Test AgentFlow._evaluate_condition with numeric comparison."""
        from praisonaiagents.workflows.workflows import AgentFlow
        
        flow = AgentFlow(steps=[])
        
        # Test numeric comparisons
        assert flow._evaluate_condition("{{score}} > 80", {"score": 90}) is True
        assert flow._evaluate_condition("{{score}} > 80", {"score": 70}) is False
        assert flow._evaluate_condition("{{score}} >= 80", {"score": 80}) is True
        assert flow._evaluate_condition("{{score}} < 50", {"score": 30}) is True
    
    def test_agentflow_evaluate_condition_string(self):
        """Test AgentFlow._evaluate_condition with string comparison."""
        from praisonaiagents.workflows.workflows import AgentFlow
        
        flow = AgentFlow(steps=[])
        
        # Test string equality
        assert flow._evaluate_condition("{{status}} == approved", {"status": "approved"}) is True
        assert flow._evaluate_condition("{{status}} == approved", {"status": "rejected"}) is False
        assert flow._evaluate_condition("{{status}} != rejected", {"status": "approved"}) is True
    
    def test_agentflow_evaluate_condition_contains(self):
        """Test AgentFlow._evaluate_condition with contains check."""
        from praisonaiagents.workflows.workflows import AgentFlow
        
        flow = AgentFlow(steps=[])
        
        # Test contains
        assert flow._evaluate_condition("error in {{message}}", {"message": "An error occurred"}) is True
        assert flow._evaluate_condition("error in {{message}}", {"message": "Success!"}) is False
        assert flow._evaluate_condition("{{message}} contains success", {"message": "Operation success"}) is True
    
    def test_agentflow_evaluate_condition_boolean(self):
        """Test AgentFlow._evaluate_condition with boolean evaluation."""
        from praisonaiagents.workflows.workflows import AgentFlow
        
        flow = AgentFlow(steps=[])
        
        # Test boolean
        assert flow._evaluate_condition("{{flag}}", {"flag": True}) is True
        assert flow._evaluate_condition("{{flag}}", {"flag": False}) is False
        assert flow._evaluate_condition("{{flag}}", {"flag": "yes"}) is True
    
    def test_agentflow_evaluate_condition_nested(self):
        """Test AgentFlow._evaluate_condition with nested property access."""
        from praisonaiagents.workflows.workflows import AgentFlow
        
        flow = AgentFlow(steps=[])
        
        # Test nested property
        assert flow._evaluate_condition("{{item.score}} >= 60", {"item": {"score": 75}}) is True
        assert flow._evaluate_condition("{{item.score}} >= 60", {"item": {"score": 50}}) is False
    
    def test_agentflow_evaluate_condition_previous_output(self):
        """Test AgentFlow._evaluate_condition with previous_output."""
        from praisonaiagents.workflows.workflows import AgentFlow
        
        flow = AgentFlow(steps=[])
        
        # Test previous_output substitution
        result = flow._evaluate_condition(
            "success in {{previous_output}}",
            {},
            previous_output="Operation success"
        )
        assert result is True


class TestSharedEvaluatorConsistency:
    """Test that shared evaluator produces consistent results."""
    
    def test_evaluator_and_agentflow_produce_same_results(self):
        """Verify shared evaluator and AgentFlow produce identical results."""
        from praisonaiagents.conditions.evaluator import evaluate_condition
        from praisonaiagents.workflows.workflows import AgentFlow
        
        flow = AgentFlow(steps=[])
        
        test_cases = [
            ("{{score}} > 80", {"score": 90}, None),
            ("{{score}} > 80", {"score": 70}, None),
            ("{{status}} == approved", {"status": "approved"}, None),
            ("error in {{message}}", {"message": "An error occurred"}, None),
            ("{{flag}}", {"flag": True}, None),
            ("{{item.score}} >= 60", {"item": {"score": 75}}, None),
            ("success in {{previous_output}}", {}, "Operation success"),
        ]
        
        for condition, variables, previous_output in test_cases:
            shared_result = evaluate_condition(condition, variables, previous_output)
            flow_result = flow._evaluate_condition(condition, variables, previous_output)
            assert shared_result == flow_result, f"Mismatch for {condition}"


class TestDictConditionForAgentTeam:
    """Test DictCondition for AgentTeam-style routing."""
    
    def test_dict_condition_routing(self):
        """Test dict condition for task routing."""
        from praisonaiagents.conditions.evaluator import DictCondition
        
        # Simulate AgentTeam task routing
        cond = DictCondition(
            {"approved": ["publish_task"], "rejected": ["revise_task"]},
            key="decision"
        )
        
        # Test routing
        assert cond.evaluate({"decision": "approved"}) is True
        assert cond.get_target({"decision": "approved"}) == ["publish_task"]
        
        assert cond.evaluate({"decision": "rejected"}) is True
        assert cond.get_target({"decision": "rejected"}) == ["revise_task"]
        
        assert cond.evaluate({"decision": "unknown"}) is False
        assert cond.get_target({"decision": "unknown"}) == []
    
    def test_dict_condition_case_insensitive(self):
        """Test dict condition is case-insensitive for decision values."""
        from praisonaiagents.conditions.evaluator import DictCondition
        
        cond = DictCondition(
            {"approved": ["publish"], "rejected": ["revise"]},
            key="decision"
        )
        
        # Test case insensitivity
        assert cond.evaluate({"decision": "APPROVED"}) is True
        assert cond.evaluate({"decision": "Approved"}) is True
        assert cond.get_target({"decision": "APPROVED"}) == ["publish"]


class TestExpressionConditionClass:
    """Test ExpressionCondition class wrapper."""
    
    def test_expression_condition_class(self):
        """Test ExpressionCondition class usage."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition
        
        cond = ExpressionCondition("{{score}} > 80")
        
        assert cond.evaluate({"score": 90}) is True
        assert cond.evaluate({"score": 70}) is False
    
    def test_expression_condition_with_previous_output(self):
        """Test ExpressionCondition with previous_output in context."""
        from praisonaiagents.conditions.evaluator import ExpressionCondition

        cond = ExpressionCondition("success in {{previous_output}}")

        # previous_output is passed via context
        assert cond.evaluate({"previous_output": "Operation success"}) is True
        assert cond.evaluate({"previous_output": "Operation failed"}) is False


class TestEvaluateConditionFailSafeFallback:
    """A comparison operator that never resolves must fail safe to False,
    per evaluate_condition's own documented contract, instead of falling
    through to the final truthy-string check."""

    def test_relational_with_undefined_right_operand(self):
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{score}} > {{threshold}}", {"score": 90}) is False

    def test_equality_with_undefined_right_operand(self):
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{status}} == {{expected}}", {"status": "approved"}) is False

    def test_relational_with_non_numeric_operands(self):
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{a}} > {{b}}", {"a": "apple", "b": "banana"}) is False

    def test_equality_with_undefined_left_operand(self):
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{error_flag}} == true", {}) is False

    def test_plain_flag_truthy_check_still_works(self):
        """Guard against over-broadly rejecting values with no comparison
        operator at all: the existing boolean/flag path is unaffected."""
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{flag}}", {"flag": "yes"}) is True
        assert evaluate_condition("{{flag}}", {"flag": ""}) is False

    def test_substituted_value_containing_operator_stays_truthy(self):
        """A placeholder with no comparison operator in the template must
        stay on the truthy-string path even if its substituted value
        happens to contain '>', '<', '==', etc."""
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{flag}}", {"flag": "ready > now"}) is True

    def test_substituted_value_parseable_as_numeric_comparison_stays_truthy(self):
        """A plain flag whose value parses as a numeric comparison
        (e.g. "5 < 3") must not be evaluated as a comparison: the template
        has no operator, so the non-empty value is truthy."""
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{flag}}", {"flag": "5 < 3"}) is True
        assert evaluate_condition("{{flag}}", {"flag": "5 > 3"}) is True

    def test_substituted_value_parseable_as_equality_stays_truthy(self):
        """A plain flag whose value parses as an equality comparison
        (e.g. "a == b") must stay on the truthy-string path because the
        template contains no comparison operator."""
        from praisonaiagents.conditions.evaluator import evaluate_condition

        assert evaluate_condition("{{flag}}", {"flag": "a == b"}) is True
        assert evaluate_condition("{{flag}}", {"flag": "a != b"}) is True
