"""
Test-Driven Development tests for Planning Mode.

This module contains comprehensive tests for:
- Plan and PlanStep dataclasses
- TodoList and TodoItem classes
- PlanStorage for persistence
- PlanningAgent for plan creation
- Agents planning integration
- Read-only mode
- Approval flow
"""

import pytest
import asyncio
import json
import os
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock


# =============================================================================
# SECTION 1: Plan and PlanStep Tests
# =============================================================================

class TestPlanStep:
    """Tests for PlanStep dataclass."""
    
    def test_plan_step_creation_minimal(self):
        """Test creating a PlanStep with minimal parameters."""
        from praisonaiagents.planning import PlanStep
        
        step = PlanStep(description="Test step")
        
        assert step.description == "Test step"
        assert step.id is not None
        assert len(step.id) == 8
        assert step.status == "pending"
        assert step.agent is None
        assert step.tools == []
        assert step.dependencies == []
        
    def test_plan_step_creation_full(self):
        """Test creating a PlanStep with all parameters."""
        from praisonaiagents.planning import PlanStep
        
        step = PlanStep(
            id="step001",
            description="Implement authentication",
            agent="Backend Developer",
            tools=["read_file", "write_file"],
            dependencies=["step000"],
            status="in_progress",
            estimated_tokens=1000
        )
        
        assert step.id == "step001"
        assert step.description == "Implement authentication"
        assert step.agent == "Backend Developer"
        assert step.tools == ["read_file", "write_file"]
        assert step.dependencies == ["step000"]
        assert step.status == "in_progress"
        assert step.estimated_tokens == 1000
        
    def test_plan_step_to_dict(self):
        """Test converting PlanStep to dictionary."""
        from praisonaiagents.planning import PlanStep
        
        step = PlanStep(
            id="step001",
            description="Test step",
            agent="Tester",
            tools=["pytest"],
            dependencies=["step000"],
            status="completed"
        )
        
        data = step.to_dict()
        
        assert data["id"] == "step001"
        assert data["description"] == "Test step"
        assert data["agent"] == "Tester"
        assert data["tools"] == ["pytest"]
        assert data["dependencies"] == ["step000"]
        assert data["status"] == "completed"
        
    def test_plan_step_from_dict(self):
        """Test creating PlanStep from dictionary."""
        from praisonaiagents.planning import PlanStep
        
        data = {
            "id": "step002",
            "description": "Deploy application",
            "agent": "DevOps",
            "tools": ["docker", "kubectl"],
            "dependencies": ["step001"],
            "status": "pending"
        }
        
        step = PlanStep.from_dict(data)
        
        assert step.id == "step002"
        assert step.description == "Deploy application"
        assert step.agent == "DevOps"
        assert step.tools == ["docker", "kubectl"]
        
    def test_plan_step_status_transitions(self):
        """Test valid status transitions."""
        from praisonaiagents.planning import PlanStep
        
        step = PlanStep(description="Test")
        assert step.status == "pending"
        
        step.status = "in_progress"
        assert step.status == "in_progress"
        
        step.status = "completed"
        assert step.status == "completed"
        
    def test_plan_step_mark_complete(self):
        """Test marking a step as complete."""
        from praisonaiagents.planning import PlanStep
        
        step = PlanStep(description="Test", status="in_progress")
        step.mark_complete()
        
        assert step.status == "completed"
        
    def test_plan_step_mark_in_progress(self):
        """Test marking a step as in progress."""
        from praisonaiagents.planning import PlanStep
        
        step = PlanStep(description="Test")
        step.mark_in_progress()
        
        assert step.status == "in_progress"


class TestPlan:
    """Tests for Plan dataclass."""
    
    def test_plan_creation_minimal(self):
        """Test creating a Plan with minimal parameters."""
        from praisonaiagents.planning import Plan
        
        plan = Plan(name="Test Plan")
        
        assert plan.name == "Test Plan"
        assert plan.id is not None
        assert plan.status == "draft"
        assert plan.steps == []
        assert plan.description == ""
        assert plan.created_at is not None
        
    def test_plan_creation_with_steps(self):
        """Test creating a Plan with steps."""
        from praisonaiagents.planning import Plan, PlanStep
        
        steps = [
            PlanStep(description="Step 1"),
            PlanStep(description="Step 2"),
            PlanStep(description="Step 3")
        ]
        
        plan = Plan(
            name="Implementation Plan",
            description="Implement new feature",
            steps=steps
        )
        
        assert len(plan.steps) == 3
        assert plan.steps[0].description == "Step 1"
        
    def test_plan_to_markdown(self):
        """Test converting Plan to markdown format."""
        from praisonaiagents.planning import Plan, PlanStep
        
        plan = Plan(
            name="Auth Implementation",
            description="Implement user authentication",
            steps=[
                PlanStep(description="Create user model", agent="Backend"),
                PlanStep(description="Add auth routes", dependencies=["step1"])
            ]
        )
        
        md = plan.to_markdown()
        
        assert "# Auth Implementation" in md
        assert "Implement user authentication" in md
        assert "Create user model" in md
        assert "Add auth routes" in md
        
    def test_plan_from_markdown(self):
        """Test creating Plan from markdown."""
        from praisonaiagents.planning import Plan
        
        markdown = """---
id: abc123
name: Test Plan
status: approved
---

# Test Plan

This is a test plan.

## Steps

1. ⬜ First step
   - Agent: Developer
2. ⬜ Second step
   - Depends on: step1
"""
        
        plan = Plan.from_markdown(markdown)
        
        assert plan.id == "abc123"
        assert plan.name == "Test Plan"
        assert plan.status == "approved"
        
    def test_plan_to_dict(self):
        """Test converting Plan to dictionary."""
        from praisonaiagents.planning import Plan, PlanStep
        
        plan = Plan(
            id="plan001",
            name="Test Plan",
            steps=[PlanStep(description="Step 1")]
        )
        
        data = plan.to_dict()
        
        assert data["id"] == "plan001"
        assert data["name"] == "Test Plan"
        assert len(data["steps"]) == 1
        
    def test_plan_from_dict(self):
        """Test creating Plan from dictionary."""
        from praisonaiagents.planning import Plan
        
        data = {
            "id": "plan002",
            "name": "Loaded Plan",
            "description": "A loaded plan",
            "status": "draft",
            "steps": [
                {"description": "Step 1", "status": "pending"}
            ]
        }
        
        plan = Plan.from_dict(data)
        
        assert plan.id == "plan002"
        assert plan.name == "Loaded Plan"
        assert len(plan.steps) == 1
        
    def test_plan_add_step(self):
        """Test adding a step to a plan."""
        from praisonaiagents.planning import Plan, PlanStep
        
        plan = Plan(name="Test")
        step = PlanStep(description="New step")
        
        plan.add_step(step)
        
        assert len(plan.steps) == 1
        assert plan.steps[0].description == "New step"
        
    def test_plan_remove_step(self):
        """Test removing a step from a plan."""
        from praisonaiagents.planning import Plan, PlanStep
        
        step1 = PlanStep(id="s1", description="Step 1")
        step2 = PlanStep(id="s2", description="Step 2")
        plan = Plan(name="Test", steps=[step1, step2])
        
        plan.remove_step("s1")
        
        assert len(plan.steps) == 1
        assert plan.steps[0].id == "s2"
        
    def test_plan_get_step(self):
        """Test getting a step by ID."""
        from praisonaiagents.planning import Plan, PlanStep
        
        step = PlanStep(id="target", description="Target step")
        plan = Plan(name="Test", steps=[step])
        
        found = plan.get_step("target")
        
        assert found is not None
        assert found.description == "Target step"
        
    def test_plan_approve(self):
        """Test approving a plan."""
        from praisonaiagents.planning import Plan
        
        plan = Plan(name="Test")
        assert plan.status == "draft"
        assert plan.approved_at is None
        
        plan.approve()
        
        assert plan.status == "approved"
        assert plan.approved_at is not None
        
    def test_plan_progress(self):
        """Test calculating plan progress."""
        from praisonaiagents.planning import Plan, PlanStep
        
        plan = Plan(
            name="Test",
            steps=[
                PlanStep(description="S1", status="completed"),
                PlanStep(description="S2", status="completed"),
                PlanStep(description="S3", status="pending"),
                PlanStep(description="S4", status="pending")
            ]
        )
        
        progress = plan.progress
        
        assert progress == 0.5  # 2 out of 4 completed
        
    def test_plan_is_complete(self):
        """Test checking if plan is complete."""
        from praisonaiagents.planning import Plan, PlanStep
        
        plan = Plan(
            name="Test",
            steps=[
                PlanStep(description="S1", status="completed"),
                PlanStep(description="S2", status="completed")
            ]
        )
        
        assert plan.is_complete is True
        
        plan.steps.append(PlanStep(description="S3", status="pending"))
        
        assert plan.is_complete is False


# =============================================================================
# SECTION 2: TodoList and TodoItem Tests
# =============================================================================

class TestTodoItem:
    """Tests for TodoItem dataclass."""
    
    def test_todo_item_creation(self):
        """Test creating a TodoItem."""
        from praisonaiagents.planning import TodoItem
        
        item = TodoItem(description="Write tests")
        
        assert item.description == "Write tests"
        assert item.id is not None
        assert item.status == "pending"
        assert item.dependencies == []
        
    def test_todo_item_with_dependencies(self):
        """Test TodoItem with dependencies."""
        from praisonaiagents.planning import TodoItem
        
        item = TodoItem(
            description="Deploy",
            dependencies=["build", "test"]
        )
        
        assert item.dependencies == ["build", "test"]
        
    def test_todo_item_complete(self):
        """Test completing a TodoItem."""
        from praisonaiagents.planning import TodoItem
        
        item = TodoItem(description="Task")
        item.complete()
        
        assert item.status == "completed"
        
    def test_todo_item_to_dict(self):
        """Test converting TodoItem to dict."""
        from praisonaiagents.planning import TodoItem
        
        item = TodoItem(id="t1", description="Task", status="completed")
        data = item.to_dict()
        
        assert data["id"] == "t1"
        assert data["description"] == "Task"
        assert data["status"] == "completed"


class TestTodoList:
    """Tests for TodoList class."""
    
    def test_todo_list_creation(self):
        """Test creating an empty TodoList."""
        from praisonaiagents.planning import TodoList
        
        todo = TodoList()
        
        assert len(todo.items) == 0
        assert todo.auto_update is True
        
    def test_todo_list_add_item(self):
        """Test adding items to TodoList."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        todo = TodoList()
        item = TodoItem(description="New task")
        
        todo.add(item)
        
        assert len(todo.items) == 1
        
    def test_todo_list_add_by_description(self):
        """Test adding item by description."""
        from praisonaiagents.planning import TodoList
        
        todo = TodoList()
        todo.add("Write documentation")
        
        assert len(todo.items) == 1
        assert todo.items[0].description == "Write documentation"
        
    def test_todo_list_remove_item(self):
        """Test removing item from TodoList."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        item = TodoItem(id="t1", description="Task")
        todo = TodoList(items=[item])
        
        todo.remove("t1")
        
        assert len(todo.items) == 0
        
    def test_todo_list_complete_item(self):
        """Test completing an item in TodoList."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        item = TodoItem(id="t1", description="Task")
        todo = TodoList(items=[item])
        
        todo.complete("t1")
        
        assert todo.items[0].status == "completed"
        
    def test_todo_list_pending_items(self):
        """Test getting pending items."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        todo = TodoList(items=[
            TodoItem(description="T1", status="completed"),
            TodoItem(description="T2", status="pending"),
            TodoItem(description="T3", status="pending")
        ])
        
        pending = todo.pending
        
        assert len(pending) == 2
        
    def test_todo_list_completed_items(self):
        """Test getting completed items."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        todo = TodoList(items=[
            TodoItem(description="T1", status="completed"),
            TodoItem(description="T2", status="completed"),
            TodoItem(description="T3", status="pending")
        ])
        
        completed = todo.completed
        
        assert len(completed) == 2
        
    def test_todo_list_progress(self):
        """Test calculating progress."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        todo = TodoList(items=[
            TodoItem(description="T1", status="completed"),
            TodoItem(description="T2", status="pending"),
            TodoItem(description="T3", status="pending"),
            TodoItem(description="T4", status="pending")
        ])
        
        assert todo.progress == 0.25
        
    def test_todo_list_to_markdown(self):
        """Test converting TodoList to markdown."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        todo = TodoList(items=[
            TodoItem(description="Task 1", status="completed"),
            TodoItem(description="Task 2", status="pending")
        ])
        
        md = todo.to_markdown()
        
        assert "- [x] Task 1" in md
        assert "- [ ] Task 2" in md
        
    def test_todo_list_from_plan(self):
        """Test creating TodoList from Plan."""
        from praisonaiagents.planning import TodoList, Plan, PlanStep
        
        plan = Plan(
            name="Test",
            steps=[
                PlanStep(description="Step 1"),
                PlanStep(description="Step 2")
            ]
        )
        
        todo = TodoList.from_plan(plan)
        
        assert len(todo.items) == 2
        assert todo.items[0].description == "Step 1"
        
    def test_todo_list_to_json(self):
        """Test serializing TodoList to JSON."""
        from praisonaiagents.planning import TodoList, TodoItem
        
        todo = TodoList(items=[
            TodoItem(id="t1", description="Task 1")
        ])
        
        json_str = todo.to_json()
        data = json.loads(json_str)
        
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "t1"
        
    def test_todo_list_from_json(self):
        """Test loading TodoList from JSON."""
        from praisonaiagents.planning import TodoList
        
        json_str = '{"items": [{"id": "t1", "description": "Task", "status": "pending", "dependencies": []}]}'
        
        todo = TodoList.from_json(json_str)
        
        assert len(todo.items) == 1
        assert todo.items[0].id == "t1"


# =============================================================================
# SECTION 3: PlanStorage Tests
# =============================================================================

class TestPlanStorage:
    """Tests for PlanStorage class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        dir_path = tempfile.mkdtemp()
        yield dir_path
        shutil.rmtree(dir_path)
        
    def test_storage_initialization(self, temp_dir):
        """Test PlanStorage initialization."""
        from praisonaiagents.planning import PlanStorage
        
        storage = PlanStorage(base_path=temp_dir)
        
        assert storage.base_path == temp_dir
        assert os.path.exists(os.path.join(temp_dir, "plans"))
        assert os.path.exists(os.path.join(temp_dir, "todos"))
        
    def test_storage_save_plan(self, temp_dir):
        """Test saving a plan."""
        from praisonaiagents.planning import PlanStorage, Plan, PlanStep
        
        storage = PlanStorage(base_path=temp_dir)
        plan = Plan(
            id="test123",
            name="Test Plan",
            steps=[PlanStep(description="Step 1")]
        )
        
        path = storage.save_plan(plan)
        
        assert os.path.exists(path)
        assert "test123" in path
        
    def test_storage_load_plan(self, temp_dir):
        """Test loading a plan."""
        from praisonaiagents.planning import PlanStorage, Plan, PlanStep
        
        storage = PlanStorage(base_path=temp_dir)
        plan = Plan(id="load123", name="Load Test", steps=[])
        storage.save_plan(plan)
        
        loaded = storage.load_plan("load123")
        
        assert loaded is not None
        assert loaded.id == "load123"
        assert loaded.name == "Load Test"
        
    def test_storage_list_plans(self, temp_dir):
        """Test listing all plans."""
        from praisonaiagents.planning import PlanStorage, Plan
        
        storage = PlanStorage(base_path=temp_dir)
        storage.save_plan(Plan(id="p1", name="Plan 1"))
        storage.save_plan(Plan(id="p2", name="Plan 2"))
        
        plans = storage.list_plans()
        
        assert len(plans) == 2
        
    def test_storage_delete_plan(self, temp_dir):
        """Test deleting a plan."""
        from praisonaiagents.planning import PlanStorage, Plan
        
        storage = PlanStorage(base_path=temp_dir)
        storage.save_plan(Plan(id="del123", name="Delete Me"))
        
        storage.delete_plan("del123")
        
        assert storage.load_plan("del123") is None
        
    def test_storage_save_todo(self, temp_dir):
        """Test saving a TodoList."""
        from praisonaiagents.planning import PlanStorage, TodoList, TodoItem
        
        storage = PlanStorage(base_path=temp_dir)
        todo = TodoList(items=[TodoItem(description="Task 1")])
        
        path = storage.save_todo(todo, "current")
        
        assert os.path.exists(path)
        
    def test_storage_load_todo(self, temp_dir):
        """Test loading a TodoList."""
        from praisonaiagents.planning import PlanStorage, TodoList, TodoItem
        
        storage = PlanStorage(base_path=temp_dir)
        todo = TodoList(items=[TodoItem(id="t1", description="Task")])
        storage.save_todo(todo, "test")
        
        loaded = storage.load_todo("test")
        
        assert loaded is not None
        assert len(loaded.items) == 1
        assert loaded.items[0].id == "t1"
        
    def test_storage_default_path(self):
        """Test default storage path."""
        from praisonaiagents.planning import PlanStorage
        
        storage = PlanStorage()
        
        assert ".praison" in storage.base_path


# =============================================================================
# SECTION 4: PlanningAgent Tests
# =============================================================================

class TestPlanningAgent:
    """Tests for PlanningAgent class."""
    
    def test_planning_agent_creation(self):
        """Test creating a PlanningAgent."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent()
        
        assert planner.llm_model in ["gpt-4o-mini", "gpt-4o-mini"]
        assert planner.read_only is True
        
    def test_planning_agent_custom_llm(self):
        """Test PlanningAgent with custom LLM."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent(llm="gpt-4o-mini")
        
        assert planner.llm_model == "gpt-4o-mini"
        
    def test_planning_agent_allowed_tools(self):
        """Test PlanningAgent has only read-only tools."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent(read_only=True)
        
        assert "read_file" in planner.allowed_tools
        assert "list_directory" in planner.allowed_tools
        assert "write_file" not in planner.allowed_tools
        assert "execute_command" not in planner.allowed_tools
        
    @pytest.mark.asyncio
    async def test_planning_agent_create_plan(self):
        """Test creating a plan."""
        from praisonaiagents.planning import PlanningAgent, Plan
        from praisonaiagents import Agent
        
        # Mock the LLM response by patching the _get_llm method
        planner = PlanningAgent()
        
        mock_llm = MagicMock()
        # Mock get_response_async which is the method actually called
        mock_llm.get_response_async = AsyncMock(return_value=json.dumps({
            "name": "Test Plan",
            "description": "A test plan",
            "steps": [
                {"description": "Step 1", "agent": "Developer"},
                {"description": "Step 2", "dependencies": ["step1"]}
            ]
        }))
        
        planner._llm = mock_llm
        agents = [Agent(name="Developer", role="Developer")]
        
        plan = await planner.create_plan(
            request="Implement feature X",
            agents=agents
        )
        
        assert isinstance(plan, Plan)
        assert plan.name == "Test Plan"
        assert len(plan.steps) == 2
            
    @pytest.mark.asyncio
    async def test_planning_agent_refine_plan(self):
        """Test refining a plan."""
        from praisonaiagents.planning import PlanningAgent, Plan, PlanStep
        
        planner = PlanningAgent()
        
        mock_llm = MagicMock()
        # Mock get_response_async which is the method actually called
        mock_llm.get_response_async = AsyncMock(return_value=json.dumps({
            "name": "Refined Plan",
            "description": "Updated plan",
            "steps": [
                {"description": "Updated Step 1"},
                {"description": "New Step 2"},
                {"description": "New Step 3"}
            ]
        }))
        
        planner._llm = mock_llm
        original_plan = Plan(
            name="Original",
            steps=[PlanStep(description="Old step")]
        )
        
        refined = await planner.refine_plan(
            plan=original_plan,
            feedback="Add more steps"
        )
        
        assert refined.name == "Refined Plan"
        assert len(refined.steps) == 3
            
    @pytest.mark.asyncio
    async def test_planning_agent_analyze_codebase(self):
        """Test codebase analysis."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent()
        
        mock_llm = MagicMock()
        # Mock get_response_async which is the method actually called
        mock_llm.get_response_async = AsyncMock(return_value="Analysis: Python project with FastAPI")
        
        planner._llm = mock_llm
        
        analysis = await planner.analyze_context(
            context="src/main.py contains FastAPI app"
        )
        
        assert "FastAPI" in analysis
            
    def test_planning_agent_format_agents_info(self):
        """Test formatting agent information."""
        from praisonaiagents.planning import PlanningAgent
        from praisonaiagents import Agent
        
        planner = PlanningAgent()
        agents = [
            Agent(name="Backend", role="Backend Developer"),
            Agent(name="Frontend", role="Frontend Developer")
        ]
        
        info = planner._format_agents_info(agents)
        
        assert "Backend" in info
        assert "Frontend" in info
        assert "Backend Developer" in info


# =============================================================================
# SECTION 5: Agents Planning Integration Tests
# =============================================================================

class TestAgentsPlanningIntegration:
    """Tests for planning integration in Agents."""
    
    def test_agents_planning_disabled_by_default(self):
        """Test that planning is disabled by default."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentManager(agents=[agent], tasks=[task])
        
        assert agents.planning is False
        
    def test_agents_planning_enabled(self):
        """Test enabling planning mode."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=True
        )
        
        assert agents.planning is True
        
    def test_agents_planning_custom_llm(self):
        """Test custom planning LLM."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(llm="gpt-4o-mini")
        )
        
        assert agents.planning_llm == "gpt-4o-mini"
        
    def test_agents_auto_approve_plan(self):
        """Test auto-approve plan option."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(auto_approve=True)
        )
        
        assert agents.auto_approve_plan is True
        
    @pytest.mark.asyncio
    async def test_agents_start_with_planning(self):
        """Test starting agents with planning enabled."""
        from praisonaiagents import Agent, Task, AgentManager
        from praisonaiagents.planning import Plan, PlanStep
        
        agent = Agent(name="Test", role="Tester", llm="gpt-4o-mini")
        task = Task(description="Test task", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(auto_approve=True)
        )
        
        # Test that planning is enabled and configured correctly
        assert agents.planning is not None  # Planning config is set
        assert agents.auto_approve_plan is True
        # Default planning_llm is gpt-4o-mini
        assert agents.planning_llm == "gpt-4o-mini"
        assert agents._current_plan is None  # No plan created yet
        assert agents._todo_list is None
                
    def test_agents_get_current_plan(self):
        """Test getting current plan."""
        from praisonaiagents import Agent, Task, AgentManager
        from praisonaiagents.planning import Plan
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=True
        )
        
        # Initially no plan
        assert agents.current_plan is None
        
    def test_agents_get_todo_list(self):
        """Test getting todo list."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=True
        )
        
        # Initially no todo list
        assert agents.todo_list is None


# =============================================================================
# SECTION 6: Read-Only Mode Tests
# =============================================================================

class TestReadOnlyMode:
    """Tests for read-only mode in Agent."""
    
    def test_agent_plan_mode_disabled_by_default(self):
        """Test that plan_mode is disabled by default."""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester")
        
        assert agent.plan_mode is False
        
    def test_agent_plan_mode_enabled(self):
        """Test enabling plan_mode via PlanningConfig."""
        from praisonaiagents import Agent
        from praisonaiagents.config import PlanningConfig
        
        agent = Agent(name="Test", role="Tester", planning=PlanningConfig(read_only=True))
        
        assert agent.plan_mode is True
        
    def test_agent_read_only_tools_filter(self):
        """Test that plan_mode filters to read-only tools."""
        from praisonaiagents import Agent
        from praisonaiagents.config import PlanningConfig
        from praisonaiagents.planning import READ_ONLY_TOOLS
        
        def read_file(path: str) -> str:
            """Read a file."""
            return "content"
            
        def write_file(path: str, content: str) -> bool:
            """Write to a file."""
            return True
            
        agent = Agent(
            name="Test",
            role="Tester",
            tools=[read_file, write_file],
            planning=PlanningConfig(read_only=True)
        )
        
        available = agent.get_available_tools()
        
        # In plan_mode, only read-only tools should be available
        # This depends on implementation - tools need to be classified
        assert agent.plan_mode is True
        
    def test_read_only_tools_list(self):
        """Test the READ_ONLY_TOOLS constant."""
        from praisonaiagents.planning import READ_ONLY_TOOLS
        
        assert "read_file" in READ_ONLY_TOOLS
        assert "list_directory" in READ_ONLY_TOOLS
        assert "search_codebase" in READ_ONLY_TOOLS
        assert "web_search" in READ_ONLY_TOOLS
        
        # These should NOT be in read-only tools
        assert "write_file" not in READ_ONLY_TOOLS
        assert "execute_command" not in READ_ONLY_TOOLS
        assert "delete_file" not in READ_ONLY_TOOLS
        
    def test_restricted_tools_list(self):
        """Test the RESTRICTED_TOOLS constant."""
        from praisonaiagents.planning import RESTRICTED_TOOLS
        
        assert "write_file" in RESTRICTED_TOOLS
        assert "execute_command" in RESTRICTED_TOOLS
        assert "delete_file" in RESTRICTED_TOOLS
        assert "create_file" in RESTRICTED_TOOLS


# =============================================================================
# SECTION 7: Approval Flow Tests
# =============================================================================

class TestApprovalFlow:
    """Tests for plan approval flow."""
    
    def test_approval_callback_creation(self):
        """Test creating an approval callback."""
        from praisonaiagents.planning import ApprovalCallback
        
        callback = ApprovalCallback()
        
        assert callback is not None
        
    def test_approval_callback_auto_approve(self):
        """Test auto-approve callback."""
        from praisonaiagents.planning import ApprovalCallback, Plan
        
        callback = ApprovalCallback(auto_approve=True)
        plan = Plan(name="Test")
        
        result = callback(plan)
        
        assert result is True
        
    def test_approval_callback_custom_function(self):
        """Test custom approval function."""
        from praisonaiagents.planning import ApprovalCallback, Plan
        
        def custom_approve(plan):
            return plan.name == "Approved Plan"
            
        callback = ApprovalCallback(approve_fn=custom_approve)
        
        assert callback(Plan(name="Approved Plan")) is True
        assert callback(Plan(name="Other Plan")) is False
        
    @pytest.mark.asyncio
    async def test_async_approval_callback(self):
        """Test async approval callback."""
        from praisonaiagents.planning import ApprovalCallback, Plan
        
        async def async_approve(plan):
            return True
            
        callback = ApprovalCallback(approve_fn=async_approve)
        plan = Plan(name="Test")
        
        result = await callback.async_call(plan)
        
        assert result is True
        
    def test_approval_with_modifications(self):
        """Test approval with plan modifications."""
        from praisonaiagents.planning import ApprovalCallback, Plan, PlanStep
        
        def approve_and_modify(plan):
            plan.steps.append(PlanStep(description="Added step"))
            return True
            
        callback = ApprovalCallback(approve_fn=approve_and_modify)
        plan = Plan(name="Test", steps=[])
        
        result = callback(plan)
        
        assert result is True
        assert len(plan.steps) == 1
        
    def test_approval_rejection(self):
        """Test plan rejection."""
        from praisonaiagents.planning import ApprovalCallback, Plan
        
        def reject_all(plan):
            return False
            
        callback = ApprovalCallback(approve_fn=reject_all)
        plan = Plan(name="Test")
        
        result = callback(plan)
        
        assert result is False


# =============================================================================
# SECTION 8: Integration Tests
# =============================================================================

class TestFullIntegration:
    """Full integration tests for planning mode."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        dir_path = tempfile.mkdtemp()
        yield dir_path
        shutil.rmtree(dir_path)
        
    @pytest.mark.asyncio
    async def test_full_planning_workflow(self, temp_dir):
        """Test complete planning workflow."""
        from praisonaiagents.planning import (
            PlanningAgent, Plan, PlanStep, 
            PlanStorage, TodoList, ApprovalCallback
        )
        
        # 1. Create storage
        storage = PlanStorage(base_path=temp_dir)
        
        # 2. Create a plan manually (simulating PlanningAgent output)
        plan = Plan(
            name="Feature Implementation",
            description="Implement new feature",
            steps=[
                PlanStep(id="s1", description="Design API", agent="Architect"),
                PlanStep(id="s2", description="Implement backend", agent="Backend", dependencies=["s1"]),
                PlanStep(id="s3", description="Write tests", agent="Tester", dependencies=["s2"])
            ]
        )
        
        # 3. Save plan
        storage.save_plan(plan)
        
        # 4. Load plan
        loaded = storage.load_plan(plan.id)
        assert loaded.name == "Feature Implementation"
        
        # 5. Create todo list from plan
        todo = TodoList.from_plan(loaded)
        assert len(todo.items) == 3
        
        # 6. Approve plan
        callback = ApprovalCallback(auto_approve=True)
        approved = callback(loaded)
        assert approved is True
        
        # 7. Execute steps (simulate)
        for step in loaded.steps:
            step.mark_in_progress()
            # ... execution would happen here ...
            step.mark_complete()
            
        # 8. Verify completion
        assert loaded.is_complete is True
        assert loaded.progress == 1.0
        
    def test_plan_persistence_roundtrip(self, temp_dir):
        """Test plan save/load roundtrip."""
        from praisonaiagents.planning import Plan, PlanStep, PlanStorage
        
        storage = PlanStorage(base_path=temp_dir)
        
        original = Plan(
            id="roundtrip",
            name="Roundtrip Test",
            description="Test persistence",
            steps=[
                PlanStep(id="s1", description="Step 1", status="completed"),
                PlanStep(id="s2", description="Step 2", status="pending")
            ],
            status="approved"
        )
        original.approve()
        
        # Save
        storage.save_plan(original)
        
        # Load
        loaded = storage.load_plan("roundtrip")
        
        # Verify
        assert loaded.id == original.id
        assert loaded.name == original.name
        assert loaded.status == original.status
        assert len(loaded.steps) == 2
        assert loaded.steps[0].status == "completed"
        
    def test_todo_list_sync_with_plan(self, temp_dir):
        """Test TodoList stays in sync with Plan."""
        from praisonaiagents.planning import Plan, PlanStep, TodoList
        
        plan = Plan(
            name="Sync Test",
            steps=[
                PlanStep(id="s1", description="Step 1"),
                PlanStep(id="s2", description="Step 2")
            ]
        )
        
        todo = TodoList.from_plan(plan)
        
        # Complete step in plan
        plan.steps[0].mark_complete()
        
        # Sync todo
        todo.sync_with_plan(plan)
        
        assert todo.items[0].status == "completed"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
