"""
Tests for the Subagent, Batch, and Todo tools.

TDD: Tests for task delegation and batch operations.
"""

from praisonaiagents.tools.subagent_tool import (
    create_subagent_tool,
    create_batch_tool,
    create_todo_tools,
)


class TestSubagentTool:
    """Tests for the subagent tool."""
    
    def test_create_subagent_tool(self):
        """Test creating subagent tool."""
        tool = create_subagent_tool()
        
        assert tool["name"] == "spawn_subagent"
        assert "function" in tool
        assert "parameters" in tool
    
    def test_subagent_without_factory(self):
        """Test subagent execution without factory (simulation mode)."""
        tool = create_subagent_tool()
        func = tool["function"]
        
        result = func(task="Analyze the code")
        
        assert result["success"] is True
        assert "simulation" in result.get("note", "").lower()
    
    def test_subagent_with_factory(self):
        """Test subagent execution with factory."""
        class MockAgent:
            def __init__(self, name, tools=None):
                self.name = name
                self.tools = tools
            
            def chat(self, prompt):
                return f"Executed: {prompt}"
        
        tool = create_subagent_tool(agent_factory=lambda **kwargs: MockAgent(**kwargs))
        func = tool["function"]
        
        result = func(task="Test task")
        
        assert result["success"] is True
        assert "Executed" in result["output"]
    
    def test_subagent_max_depth(self):
        """Test subagent depth limit."""
        tool = create_subagent_tool(max_depth=1)
        func = tool["function"]
        
        # First call should succeed
        result1 = func(task="Task 1")
        assert result1["success"] is True
        
        # Simulate nested call by calling again while first is "running"
        # (In real usage, this would be nested)
    
    def test_subagent_allowed_agents(self):
        """Test allowed agents filter."""
        tool = create_subagent_tool(allowed_agents=["coder", "reviewer"])
        func = tool["function"]
        
        # Allowed agent
        result1 = func(task="Task", agent_name="coder")
        assert result1["success"] is True
        
        # Disallowed agent
        result2 = func(task="Task", agent_name="hacker")
        assert result2["success"] is False
        assert "not in allowed" in result2["error"]
    
    def test_subagent_with_context(self):
        """Test subagent with context."""
        tool = create_subagent_tool()
        func = tool["function"]
        
        result = func(
            task="Analyze this",
            context="Previous analysis showed issues"
        )
        
        assert result["success"] is True


class TestBatchTool:
    """Tests for the batch tool."""
    
    def test_create_batch_tool(self):
        """Test creating batch tool."""
        tool = create_batch_tool()
        
        assert tool["name"] == "batch_execute"
        assert "function" in tool
    
    def test_batch_execute(self):
        """Test batch execution."""
        tool = create_batch_tool()
        func = tool["function"]
        
        result = func(operations=[
            {"type": "read", "args": {"file": "a.txt"}},
            {"type": "read", "args": {"file": "b.txt"}},
            {"type": "write", "args": {"file": "c.txt", "content": "test"}},
        ])
        
        assert result["total"] == 3
        assert result["successful"] == 3
        assert result["failed"] == 0
        assert len(result["results"]) == 3
    
    def test_batch_empty(self):
        """Test batch with empty operations."""
        tool = create_batch_tool()
        func = tool["function"]
        
        result = func(operations=[])
        
        assert result["total"] == 0
        assert result["successful"] == 0


class TestTodoTools:
    """Tests for the todo tools."""
    
    def test_create_todo_tools(self):
        """Test creating todo tools."""
        tools = create_todo_tools()
        
        assert len(tools) == 4
        names = [t["name"] for t in tools]
        assert "add_todo" in names
        assert "update_todo" in names
        assert "list_todos" in names
        assert "delete_todo" in names
    
    def test_add_todo(self):
        """Test adding a todo."""
        tools = create_todo_tools()
        add_func = next(t["function"] for t in tools if t["name"] == "add_todo")
        
        result = add_func(content="Test todo", priority="high")
        
        assert result["success"] is True
        assert result["todo"]["content"] == "Test todo"
        assert result["todo"]["priority"] == "high"
    
    def test_list_todos(self):
        """Test listing todos."""
        tools = create_todo_tools()
        add_func = next(t["function"] for t in tools if t["name"] == "add_todo")
        list_func = next(t["function"] for t in tools if t["name"] == "list_todos")
        
        add_func(content="Todo 1", priority="high")
        add_func(content="Todo 2", priority="low")
        add_func(content="Todo 3", priority="high")
        
        # List all
        result = list_func()
        assert result["count"] == 3
        
        # Filter by priority
        result = list_func(priority="high")
        assert result["count"] == 2
    
    def test_update_todo(self):
        """Test updating a todo."""
        tools = create_todo_tools()
        add_func = next(t["function"] for t in tools if t["name"] == "add_todo")
        update_func = next(t["function"] for t in tools if t["name"] == "update_todo")
        
        add_result = add_func(content="Original")
        todo_id = add_result["id"]
        
        update_result = update_func(
            todo_id=todo_id,
            content="Updated",
            status="completed"
        )
        
        assert update_result["success"] is True
        assert update_result["todo"]["content"] == "Updated"
        assert update_result["todo"]["status"] == "completed"
    
    def test_update_todo_not_found(self):
        """Test updating non-existent todo."""
        tools = create_todo_tools()
        update_func = next(t["function"] for t in tools if t["name"] == "update_todo")
        
        result = update_func(todo_id="nonexistent")
        
        assert result["success"] is False
        assert "not found" in result["error"]
    
    def test_delete_todo(self):
        """Test deleting a todo."""
        tools = create_todo_tools()
        add_func = next(t["function"] for t in tools if t["name"] == "add_todo")
        delete_func = next(t["function"] for t in tools if t["name"] == "delete_todo")
        list_func = next(t["function"] for t in tools if t["name"] == "list_todos")
        
        add_result = add_func(content="To delete")
        todo_id = add_result["id"]
        
        delete_result = delete_func(todo_id=todo_id)
        assert delete_result["success"] is True
        
        list_result = list_func()
        assert list_result["count"] == 0
    
    def test_delete_todo_not_found(self):
        """Test deleting non-existent todo."""
        tools = create_todo_tools()
        delete_func = next(t["function"] for t in tools if t["name"] == "delete_todo")
        
        result = delete_func(todo_id="nonexistent")
        
        assert result["success"] is False
