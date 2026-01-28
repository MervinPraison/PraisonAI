"""
Tests for dynamic judge configuration.

TDD: These tests define the expected behavior for:
1. OptimizationRuleProtocol - pluggable optimization rules
2. JudgeCriteriaConfig - dynamic criteria configuration
3. Domain-agnostic judge usage (not just recipes)
"""

from typing import Dict, Any


class TestOptimizationRuleProtocol:
    """Tests for OptimizationRuleProtocol - pluggable optimization rules."""
    
    def test_protocol_exists(self):
        """OptimizationRuleProtocol should be importable from eval module."""
        from praisonaiagents.eval import OptimizationRuleProtocol
        assert OptimizationRuleProtocol is not None
    
    def test_protocol_is_runtime_checkable(self):
        """Protocol should be runtime checkable for isinstance checks."""
        from praisonaiagents.eval import OptimizationRuleProtocol
        
        class MyRule:
            name = "test_rule"
            pattern = r"test pattern"
            severity = "high"
            
            def get_fix(self, context: Dict[str, Any]) -> str:
                return "Fix suggestion"
        
        rule = MyRule()
        assert isinstance(rule, OptimizationRuleProtocol)
    
    def test_custom_rule_implementation(self):
        """Custom rules should work with the protocol."""
        from praisonaiagents.eval import OptimizationRuleProtocol
        
        class WaterLeakRule:
            """Example: Water flow optimization rule."""
            name = "water_leak"
            pattern = r"(leak|overflow|pressure.drop)"
            severity = "critical"
            
            def get_fix(self, context: Dict[str, Any]) -> str:
                location = context.get("location", "unknown")
                return f"Check valve at {location} for leaks"
        
        rule = WaterLeakRule()
        assert isinstance(rule, OptimizationRuleProtocol)
        assert rule.name == "water_leak"
        assert rule.get_fix({"location": "pipe-3"}) == "Check valve at pipe-3 for leaks"


class TestJudgeCriteriaConfig:
    """Tests for JudgeCriteriaConfig - dynamic criteria configuration."""
    
    def test_config_exists(self):
        """JudgeCriteriaConfig should be importable."""
        from praisonaiagents.eval import JudgeCriteriaConfig
        assert JudgeCriteriaConfig is not None
    
    def test_config_creation(self):
        """Should be able to create config with custom criteria."""
        from praisonaiagents.eval import JudgeCriteriaConfig
        
        config = JudgeCriteriaConfig(
            name="water_flow",
            description="Evaluate water flow optimization",
            prompt_template="Evaluate the water flow: {output}",
            scoring_dimensions=["efficiency", "safety", "cost"],
            threshold=7.0,
        )
        
        assert config.name == "water_flow"
        assert config.threshold == 7.0
        assert "efficiency" in config.scoring_dimensions
    
    def test_config_with_custom_prompt(self):
        """Config should support custom prompt templates."""
        from praisonaiagents.eval import JudgeCriteriaConfig
        
        config = JudgeCriteriaConfig(
            name="data_pipeline",
            description="Evaluate data pipeline efficiency",
            prompt_template="""
            Evaluate the data pipeline output:
            {output}
            
            Criteria:
            - No data loss
            - Correct transformations
            - Performance within SLA
            
            Score from 1-10.
            """,
            scoring_dimensions=["accuracy", "performance", "reliability"],
        )
        
        assert "data pipeline" in config.prompt_template.lower()


class TestDynamicJudge:
    """Tests for dynamic judge with custom criteria."""
    
    def test_judge_accepts_criteria_config(self):
        """Judge should accept JudgeCriteriaConfig."""
        from praisonaiagents.eval import Judge, JudgeCriteriaConfig
        
        config = JudgeCriteriaConfig(
            name="custom",
            description="Custom evaluation",
            prompt_template="Evaluate: {output}",
            scoring_dimensions=["quality"],
        )
        
        judge = Judge(criteria_config=config)
        assert judge.criteria_config == config
    
    def test_judge_uses_custom_prompt_template(self):
        """Judge should use custom prompt template from config."""
        from praisonaiagents.eval import Judge, JudgeCriteriaConfig
        
        config = JudgeCriteriaConfig(
            name="water",
            description="Water flow evaluation",
            prompt_template="Is the water flow optimal? Output: {output}",
            scoring_dimensions=["flow_rate", "pressure"],
        )
        
        judge = Judge(criteria_config=config)
        # The judge should use the custom prompt template
        prompt = judge._build_judge_prompt(output="Flow rate: 100L/min")
        assert "water flow" in prompt.lower() or "flow rate" in prompt.lower()


class TestOptimizationRuleRegistry:
    """Tests for optimization rule registry."""
    
    def test_add_rule(self):
        """Should be able to add custom rules to registry."""
        from praisonaiagents.eval import add_optimization_rule, get_optimization_rule
        
        class TestRule:
            name = "test_registry_rule"
            pattern = r"test"
            severity = "low"
            
            def get_fix(self, context):
                return "Test fix"
        
        add_optimization_rule("test_registry", TestRule)
        retrieved = get_optimization_rule("test_registry")
        assert retrieved is not None
    
    def test_list_rules(self):
        """Should be able to list all registered rules."""
        from praisonaiagents.eval import list_optimization_rules
        
        rules = list_optimization_rules()
        assert isinstance(rules, list)
    
    def test_remove_rule(self):
        """Should be able to remove rules from registry."""
        from praisonaiagents.eval import add_optimization_rule, remove_optimization_rule, get_optimization_rule
        
        class TempRule:
            name = "temp_rule"
            pattern = r"temp"
            severity = "low"
            
            def get_fix(self, context):
                return "Temp fix"
        
        add_optimization_rule("temp", TempRule)
        assert get_optimization_rule("temp") is not None
        
        remove_optimization_rule("temp")
        assert get_optimization_rule("temp") is None


class TestDomainAgnosticUsage:
    """Tests for domain-agnostic judge usage."""
    
    def test_water_flow_optimization(self):
        """Judge should work for water flow optimization domain."""
        from praisonaiagents.eval import Judge
        
        # Create judge for water flow domain
        judge = Judge(
            criteria="Water flow is optimal: no leaks, pressure within 50-100 PSI, efficient routing"
        )
        
        # Should be able to evaluate water flow output
        # Note: This is a mock test - actual LLM call would happen in integration tests
        assert judge.criteria is not None
        assert "water" in judge.criteria.lower()
    
    def test_data_pipeline_optimization(self):
        """Judge should work for data pipeline optimization domain."""
        from praisonaiagents.eval import Judge
        
        judge = Judge(
            criteria="Data pipeline is efficient: no bottlenecks, correct transformations, validated output"
        )
        
        assert "pipeline" in judge.criteria.lower()
    
    def test_manufacturing_quality(self):
        """Judge should work for manufacturing quality domain."""
        from praisonaiagents.eval import Judge
        
        judge = Judge(
            criteria="Manufacturing output meets quality standards: dimensions within tolerance, surface finish acceptable, no defects"
        )
        
        assert "manufacturing" in judge.criteria.lower()


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility."""
    
    def test_judge_without_criteria_config(self):
        """Judge should work without criteria_config (backward compatible)."""
        from praisonaiagents.eval import Judge
        
        # Original usage should still work
        judge = Judge()
        assert judge is not None
    
    def test_judge_with_simple_criteria(self):
        """Judge should work with simple string criteria (backward compatible)."""
        from praisonaiagents.eval import Judge
        
        judge = Judge(criteria="Response is helpful and accurate")
        assert judge.criteria == "Response is helpful and accurate"
    
    def test_existing_judge_types(self):
        """Existing judge types should still work."""
        from praisonaiagents.eval import AccuracyJudge, CriteriaJudge, RecipeJudge
        
        accuracy = AccuracyJudge()
        criteria = CriteriaJudge(criteria="Test")
        recipe = RecipeJudge()
        
        assert accuracy is not None
        assert criteria is not None
        assert recipe is not None
