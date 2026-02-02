"""
Integration tests comparing Task.condition vs AgentFlow when() syntax.

This test file validates both condition syntaxes work correctly and
documents the differences for analysis.
"""
import pytest


class TestAgentFlowConditionSyntax:
    """Test AgentFlow's when()/if_() string-based condition syntax."""
    
    def test_agentflow_numeric_condition(self):
        """AgentFlow uses string expressions: '{{score}} > 80'"""
        from praisonaiagents import AgentFlow
        from praisonaiagents.workflows import if_
        
        results = []
        
        def approve(ctx):
            results.append("approved")
            return {"output": "approved"}
        
        def reject(ctx):
            results.append("rejected")
            return {"output": "rejected"}
        
        # Test passing condition
        flow = AgentFlow(
            steps=[
                if_(
                    condition="{{score}} > 80",
                    then_steps=[approve],
                    else_steps=[reject]
                )
            ],
            variables={"score": 90}
        )
        flow.start("test")
        assert "approved" in results
        
        # Test failing condition
        results.clear()
        flow2 = AgentFlow(
            steps=[
                if_(
                    condition="{{score}} > 80",
                    then_steps=[approve],
                    else_steps=[reject]
                )
            ],
            variables={"score": 70}
        )
        flow2.start("test")
        assert "rejected" in results
    
    def test_agentflow_string_condition(self):
        """AgentFlow string equality: '{{status}} == approved'"""
        from praisonaiagents import AgentFlow
        from praisonaiagents.workflows import when
        
        results = []
        
        def process_approved(ctx):
            results.append("processed_approved")
            return {"output": "done"}
        
        def process_rejected(ctx):
            results.append("processed_rejected")
            return {"output": "done"}
        
        flow = AgentFlow(
            steps=[
                when(
                    condition="{{status}} == approved",
                    then_steps=[process_approved],
                    else_steps=[process_rejected]
                )
            ],
            variables={"status": "approved"}
        )
        flow.start("test")
        assert "processed_approved" in results


class TestTaskConditionSyntax:
    """Test Task's Dict-based condition syntax for routing."""
    
    def test_task_dict_condition_routing(self):
        """Task uses Dict[str, List[str]]: {'approved': ['next_task']}"""
        from praisonaiagents import Task
        
        # Task condition is a dict mapping decision values to next task names
        task = Task(
            name="review_task",
            description="Review and decide",
            task_type="decision",
            condition={
                "approved": ["publish_task"],
                "rejected": ["revise_task"]
            }
        )
        
        # Verify condition structure
        assert isinstance(task.condition, dict)
        assert "approved" in task.condition
        assert task.condition["approved"] == ["publish_task"]
        assert task.condition["rejected"] == ["revise_task"]
    
    def test_task_should_run_callable(self):
        """Task also supports should_run callable for conditional execution."""
        from praisonaiagents import Task
        
        def check_condition(ctx):
            return ctx.get("score", 0) > 80
        
        task = Task(
            name="conditional_task",
            description="Only run if score > 80",
            should_run=check_condition
        )
        
        assert task.should_run is not None
        assert callable(task.should_run)
        # Test the callable
        assert task.should_run({"score": 90}) is True
        assert task.should_run({"score": 70}) is False


class TestSyntaxComparison:
    """Compare the two syntaxes side-by-side."""
    
    def test_document_syntax_differences(self):
        """Document the syntax differences for analysis."""
        
        # ============================================================
        # AGENTFLOW SYNTAX (Deterministic Pipelines)
        # ============================================================
        # Uses: String expressions with {{variable}} placeholders
        # Location: workflows/workflows.py - when(), if_(), If class
        # Evaluation: evaluate_condition() in conditions/evaluator.py
        # 
        # Example:
        #   when(
        #       condition="{{score}} > 80",  # STRING expression
        #       then_steps=[approve],
        #       else_steps=[reject]
        #   )
        #
        # Supported formats:
        #   - Numeric: "{{var}} > 80", "{{var}} >= 50"
        #   - String: "{{var}} == approved"
        #   - Contains: "error in {{message}}"
        #   - Boolean: "{{flag}}"
        #   - Nested: "{{item.score}} >= 60"
        
        agentflow_condition = "{{score}} > 80"  # STRING
        
        # ============================================================
        # TASK/AGENTTEAM SYNTAX (Multi-Agent Task Graphs)
        # ============================================================
        # Uses: Dict[str, List[str]] mapping decision values to task names
        # Location: task/task.py - Task.condition parameter
        # Evaluation: process/process.py - matches decision_str to dict keys
        #
        # Example:
        #   Task(
        #       condition={
        #           "approved": ["publish_task"],  # DICT routing
        #           "rejected": ["revise_task"]
        #       }
        #   )
        #
        # How it works:
        #   1. Task with task_type="decision" returns a decision value
        #   2. Process looks up decision value in condition dict
        #   3. Routes to the corresponding next task(s)
        
        task_condition = {"approved": ["publish_task"], "rejected": ["revise_task"]}  # DICT
        
        # ============================================================
        # KEY DIFFERENCES (CONFUSING FOR USERS)
        # ============================================================
        #
        # | Aspect          | AgentFlow          | Task/AgentTeam       |
        # |-----------------|--------------------|-----------------------|
        # | Condition Type  | STRING expression  | DICT routing map      |
        # | Evaluation      | Expression parsing | Key lookup            |
        # | Purpose         | Branch on value    | Route to next task    |
        # | Variables       | {{var}} syntax     | decision_str from LLM |
        # | Flexibility     | Any comparison     | Exact key match       |
        #
        # CONFUSION POINTS:
        # 1. Same word "condition" means different things
        # 2. AgentFlow: condition="{{x}} > 5" (evaluates expression)
        # 3. Task: condition={"yes": ["task_a"]} (routes by key)
        # 4. No unified syntax for beginners
        
        assert isinstance(agentflow_condition, str)
        assert isinstance(task_condition, dict)
        
        # This test documents the confusion - both use "condition" but differently


class TestRealWorldScenarios:
    """Test real-world scenarios with both syntaxes."""
    
    def test_agentflow_score_based_routing(self):
        """Real scenario: Route based on numeric score."""
        from praisonaiagents import AgentFlow
        from praisonaiagents.workflows import when
        
        execution_log = []
        
        def high_score_handler(ctx):
            execution_log.append("high_score")
            return {"output": "Premium service"}
        
        def low_score_handler(ctx):
            execution_log.append("low_score")
            return {"output": "Standard service"}
        
        # AgentFlow: Uses string expression
        flow = AgentFlow(
            steps=[
                when(
                    condition="{{customer_score}} >= 80",
                    then_steps=[high_score_handler],
                    else_steps=[low_score_handler]
                )
            ],
            variables={"customer_score": 85}
        )
        
        result = flow.start("Assign service tier")
        assert "high_score" in execution_log
    
    def test_task_decision_routing(self):
        """Real scenario: Task decision routes to next task."""
        from praisonaiagents import Task
        
        # Task: Uses dict for routing
        review_task = Task(
            name="content_review",
            description="Review content and decide: approved or rejected",
            task_type="decision",
            condition={
                "approved": ["publish_content"],
                "rejected": ["request_revision"]
            }
        )
        
        # The condition dict maps LLM decision output to next task names
        assert review_task.task_type == "decision"
        assert "approved" in review_task.condition
        assert "rejected" in review_task.condition
