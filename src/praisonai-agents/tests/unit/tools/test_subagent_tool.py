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
            def __init__(self, name, tools=None, llm=None):
                self.name = name
                self.tools = tools
                self.llm = llm
            
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
    
    def test_subagent_with_llm_selection(self):
        """Test subagent with custom LLM model selection (Claude Code parity)."""
        class MockAgent:
            def __init__(self, name, tools=None, llm=None):
                self.name = name
                self.tools = tools
                self.llm = llm
            
            def chat(self, prompt):
                return f"Model: {self.llm}, Task: {prompt}"
        
        tool = create_subagent_tool(
            agent_factory=lambda **kwargs: MockAgent(**kwargs),
            default_llm="gpt-4o-mini"
        )
        func = tool["function"]
        
        # Test with default LLM
        result = func(task="Test task")
        assert result["success"] is True
        assert "gpt-4o-mini" in result["output"]
        
        # Test with custom LLM override
        result2 = func(task="Test task", llm="claude-3-sonnet")
        assert result2["success"] is True
        assert "claude-3-sonnet" in result2["output"]
    
    def test_subagent_with_permission_mode(self):
        """Test subagent with permission mode (Claude Code parity)."""
        tool = create_subagent_tool()
        func = tool["function"]
        
        # Test with permission_mode parameter
        result = func(
            task="Analyze code",
            permission_mode="plan"  # Read-only mode
        )
        
        assert result["success"] is True
        # Permission mode should be passed through
        assert result.get("permission_mode") == "plan"

    def test_subagent_synchronous_default_unchanged(self):
        """Background defaults to False; synchronous return shape is unchanged."""
        tool = create_subagent_tool()
        func = tool["function"]

        result = func(task="Analyze the code")

        # No job_id leaks into the synchronous path.
        assert "job_id" not in result
        assert result["success"] is True
        assert "output" in result

    def test_subagent_background_returns_job_id(self):
        """background=True returns immediately with a job handle."""
        tool = create_subagent_tool()
        func = tool["function"]

        result = func(task="run the full test suite", background=True)

        assert result["success"] is True
        assert result["status"] == "running"
        assert "job_id" in result
        assert result["job_id"]

    def test_subagent_result_tool_exposed(self):
        """The companion subagent_result tool is exposed on the tool dict."""
        tool = create_subagent_tool()

        assert "result_tool" in tool
        assert tool["result_tool"]["name"] == "subagent_result"
        assert callable(tool["result_tool"]["function"])

    def test_subagent_background_result_collected(self):
        """A backgrounded subagent's result is collectable via subagent_result(wait=True)."""
        class MockAgent:
            def __init__(self, name, tools=None, llm=None):
                self.name = name

            def chat(self, prompt):
                return f"Executed: {prompt}"

        tool = create_subagent_tool(
            agent_factory=lambda **kwargs: MockAgent(**kwargs)
        )
        spawn = tool["function"]
        collect = tool["result_tool"]["function"]

        handle = spawn(task="Background task", background=True)
        assert "job_id" in handle

        final = collect(handle["job_id"], wait=True)
        assert final["success"] is True
        assert final["status"] == "completed"
        assert final["result"]["success"] is True
        assert "Executed" in final["result"]["output"]

    def test_subagent_result_unknown_job(self):
        """Unknown job_id returns a clean error rather than raising."""
        tool = create_subagent_tool()
        collect = tool["result_tool"]["function"]

        result = collect("nonexistent-job-id")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_subagent_background_failed_job_wait(self):
        """A failed background job returns a clean failure via wait=True (not a raise)."""
        class ExplodingAgent:
            def __init__(self, name, tools=None, llm=None):
                pass

            def chat(self, prompt):
                raise RuntimeError("boom")

        tool = create_subagent_tool(
            agent_factory=lambda **kwargs: ExplodingAgent(**kwargs)
        )
        spawn = tool["function"]
        collect = tool["result_tool"]["function"]

        handle = spawn(task="will fail", background=True)
        # _run_subagent catches the chat error and returns success=False, so
        # the job itself completes; the inner result reflects the failure.
        final = collect(handle["job_id"], wait=True)

        assert final["success"] is True
        assert final["status"] == "completed"
        assert final["result"]["success"] is False
        assert "boom" in final["result"]["error"]

    def test_subagent_background_preserves_scoping(self):
        """Background subagents honour permission_mode/tools/llm scoping."""
        captured = {}

        class MockAgent:
            def __init__(self, name, tools=None, llm=None):
                captured["tools"] = tools
                captured["llm"] = llm

            def chat(self, prompt):
                return "ok"

        tool = create_subagent_tool(
            agent_factory=lambda **kwargs: MockAgent(**kwargs)
        )
        spawn = tool["function"]
        collect = tool["result_tool"]["function"]

        handle = spawn(
            task="restricted task",
            tools=["read_file"],
            llm="gpt-4o-mini",
            permission_mode="plan",
            background=True,
        )
        final = collect(handle["job_id"], wait=True)

        assert final["success"] is True
        assert final["result"]["permission_mode"] == "plan"
        assert final["result"]["llm"] == "gpt-4o-mini"
        assert captured["tools"] == ["read_file"]
        assert captured["llm"] == "gpt-4o-mini"


    def test_subagent_deliver_echoed_and_origin_captured(self):
        """deliver is echoed on the handle and origin is captured on the job."""
        from praisonaiagents.background.job_manager import get_job_manager

        class MockAgent:
            def __init__(self, name, tools=None, llm=None):
                self.name = name

            def chat(self, prompt):
                return f"Executed: {prompt}"

        tool = create_subagent_tool(
            agent_factory=lambda **kwargs: MockAgent(**kwargs)
        )
        spawn = tool["function"]
        collect = tool["result_tool"]["function"]

        handle = spawn(
            task="deep research",
            background=True,
            deliver="telegram:12345",
            platform="telegram",
            chat_id="12345",
        )
        assert handle["deliver"] == "telegram:12345"

        # Wait for completion so the origin is inspectable.
        collect(handle["job_id"], wait=True)
        info = get_job_manager().get_job_info(handle["job_id"])
        assert info.origin["deliver"] == "telegram:12345"
        assert info.origin["platform"] == "telegram"
        assert info.origin["chat_id"] == "12345"

    def test_subagent_on_job_complete_invoked_with_deliver(self):
        """on_job_complete fires when a delivering background job finishes."""
        seen = []

        class MockAgent:
            def __init__(self, name, tools=None, llm=None):
                self.name = name

            def chat(self, prompt):
                return f"Executed: {prompt}"

        tool = create_subagent_tool(
            agent_factory=lambda **kwargs: MockAgent(**kwargs),
            on_job_complete=lambda job_info: seen.append(job_info),
        )
        spawn = tool["function"]
        collect = tool["result_tool"]["function"]

        handle = spawn(task="research", background=True, deliver="origin")
        collect(handle["job_id"], wait=True)

        assert len(seen) == 1
        assert seen[0].origin["deliver"] == "origin"
        assert seen[0].result["success"] is True

    def test_subagent_on_job_complete_not_invoked_without_deliver(self):
        """No delivery target → callback never fires (pull-only unchanged)."""
        seen = []

        class MockAgent:
            def __init__(self, name, tools=None, llm=None):
                self.name = name

            def chat(self, prompt):
                return "ok"

        tool = create_subagent_tool(
            agent_factory=lambda **kwargs: MockAgent(**kwargs),
            on_job_complete=lambda job_info: seen.append(job_info),
        )
        spawn = tool["function"]
        collect = tool["result_tool"]["function"]

        handle = spawn(task="research", background=True)
        collect(handle["job_id"], wait=True)

        assert seen == []
        assert "deliver" not in handle


class TestJobManagerCompletion:
    """Tests for BackgroundJobManager on_complete + origin (core signal)."""

    def test_on_complete_fires_on_success(self):
        from praisonaiagents.background.job_manager import (
            BackgroundJobManager,
            JobStatus,
        )

        mgr = BackgroundJobManager()
        fired = []
        job_id = mgr.start_job(
            lambda: "result-value",
            on_complete=lambda info: fired.append(info),
            origin={"deliver": "origin", "platform": "telegram"},
        )
        mgr.get_result(job_id)
        # Callback runs inside the worker; give the future a moment isn't
        # needed because get_result blocks until the worker returns, but the
        # callback runs before return so it's already recorded.
        assert len(fired) == 1
        assert fired[0].status == JobStatus.COMPLETED
        assert fired[0].result == "result-value"
        assert fired[0].origin["deliver"] == "origin"

    def test_on_complete_fires_on_failure(self):
        from praisonaiagents.background.job_manager import (
            BackgroundJobManager,
            JobStatus,
        )

        mgr = BackgroundJobManager()
        fired = []

        def boom():
            raise RuntimeError("kaboom")

        job_id = mgr.start_job(boom, on_complete=lambda info: fired.append(info))
        try:
            mgr.get_result(job_id)
        except Exception:
            pass
        assert len(fired) == 1
        assert fired[0].status == JobStatus.FAILED
        assert "kaboom" in fired[0].error

    def test_on_complete_exception_swallowed(self):
        """A raising on_complete must not crash the worker/get_result."""
        from praisonaiagents.background.job_manager import BackgroundJobManager

        mgr = BackgroundJobManager()

        def bad_callback(info):
            raise ValueError("callback exploded")

        job_id = mgr.start_job(lambda: "ok", on_complete=bad_callback)
        # get_result should still return the job's real result.
        assert mgr.get_result(job_id) == "ok"

    def test_origin_defaults_empty(self):
        """No origin → empty dict, preserving prior behaviour."""
        from praisonaiagents.background.job_manager import BackgroundJobManager

        mgr = BackgroundJobManager()
        job_id = mgr.start_job(lambda: "ok")
        mgr.get_result(job_id)
        assert mgr.get_job_info(job_id).origin == {}


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
