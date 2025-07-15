"""
Advanced State Management Patterns Example

This example demonstrates sophisticated state management including cross-session persistence,
state-based conditional workflows, versioning, and distributed state coordination.
"""

import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Advanced State Management Patterns Example ===\n")

# Advanced State Management Classes
class StateManager:
    """Comprehensive state management with persistence and versioning"""
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.current_state = {}
        self.state_history = []
        self.checkpoints = {}
        self.metadata = {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "version": "1.0.0"
        }
    
    def set_state(self, key: str, value: Any, checkpoint_name: str = None):
        """Set state with optional checkpoint creation"""
        old_value = self.current_state.get(key)
        self.current_state[key] = value
        
        # Track state changes
        self.state_history.append({
            "timestamp": datetime.now().isoformat(),
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "action": "set"
        })
        
        # Create checkpoint if requested
        if checkpoint_name:
            self.create_checkpoint(checkpoint_name)
        
        self.metadata["last_updated"] = datetime.now().isoformat()
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """Get state value with optional default"""
        return self.current_state.get(key, default)
    
    def create_checkpoint(self, name: str):
        """Create a named checkpoint of current state"""
        self.checkpoints[name] = {
            "state": self.current_state.copy(),
            "timestamp": datetime.now().isoformat(),
            "history_length": len(self.state_history)
        }
    
    def restore_checkpoint(self, name: str) -> bool:
        """Restore state from a checkpoint"""
        if name not in self.checkpoints:
            return False
        
        checkpoint = self.checkpoints[name]
        self.current_state = checkpoint["state"].copy()
        
        # Log restoration
        self.state_history.append({
            "timestamp": datetime.now().isoformat(),
            "action": "restore_checkpoint",
            "checkpoint_name": name,
            "checkpoint_timestamp": checkpoint["timestamp"]
        })
        
        return True
    
    def get_state_diff(self, checkpoint_name: str) -> Dict[str, Any]:
        """Get differences between current state and checkpoint"""
        if checkpoint_name not in self.checkpoints:
            return {}
        
        checkpoint_state = self.checkpoints[checkpoint_name]["state"]
        diff = {}
        
        # Find added/modified keys
        for key, value in self.current_state.items():
            if key not in checkpoint_state:
                diff[key] = {"action": "added", "value": value}
            elif checkpoint_state[key] != value:
                diff[key] = {
                    "action": "modified", 
                    "old_value": checkpoint_state[key],
                    "new_value": value
                }
        
        # Find removed keys
        for key in checkpoint_state:
            if key not in self.current_state:
                diff[key] = {"action": "removed", "old_value": checkpoint_state[key]}
        
        return diff
    
    def save_to_file(self, filename: str):
        """Persist state to file"""
        state_data = {
            "session_id": self.session_id,
            "current_state": self.current_state,
            "state_history": self.state_history,
            "checkpoints": self.checkpoints,
            "metadata": self.metadata
        }
        
        with open(filename, 'w') as f:
            json.dump(state_data, f, indent=2)
    
    def load_from_file(self, filename: str):
        """Load state from file"""
        try:
            with open(filename, 'r') as f:
                state_data = json.load(f)
            
            self.session_id = state_data["session_id"]
            self.current_state = state_data["current_state"]
            self.state_history = state_data["state_history"]
            self.checkpoints = state_data["checkpoints"]
            self.metadata = state_data["metadata"]
            return True
        except (FileNotFoundError, json.JSONDecodeError):
            return False

class WorkflowStateController:
    """Advanced workflow state control with conditional logic"""
    
    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager
        self.workflow_rules = {}
        self.execution_log = []
    
    def add_rule(self, rule_name: str, condition: callable, action: callable):
        """Add conditional workflow rule"""
        self.workflow_rules[rule_name] = {
            "condition": condition,
            "action": action,
            "created_at": datetime.now().isoformat()
        }
    
    def evaluate_rules(self) -> List[str]:
        """Evaluate all rules and execute matching actions"""
        executed_rules = []
        
        for rule_name, rule in self.workflow_rules.items():
            try:
                if rule["condition"](self.state_manager.current_state):
                    result = rule["action"](self.state_manager)
                    executed_rules.append(rule_name)
                    
                    self.execution_log.append({
                        "timestamp": datetime.now().isoformat(),
                        "rule_name": rule_name,
                        "action_result": result,
                        "state_snapshot": self.state_manager.current_state.copy()
                    })
            except Exception as e:
                self.execution_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "rule_name": rule_name,
                    "error": str(e),
                    "state_snapshot": self.state_manager.current_state.copy()
                })
        
        return executed_rules
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of rule executions"""
        total_executions = len(self.execution_log)
        successful_executions = len([log for log in self.execution_log if "error" not in log])
        
        return {
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "success_rate": successful_executions / total_executions if total_executions > 0 else 0,
            "rules_count": len(self.workflow_rules),
            "last_execution": self.execution_log[-1] if self.execution_log else None
        }

# Example 1: Cross-Session State Persistence
print("Example 1: Cross-Session State Persistence")
print("-" * 40)

# Create state manager with persistence
session_state = StateManager("customer_support_session_001")

# Simulate first session - customer inquiry
session_state.set_state("customer_id", "CUST_12345")
session_state.set_state("inquiry_type", "technical_support")
session_state.set_state("priority", "high")
session_state.set_state("conversation_history", [
    {"timestamp": datetime.now().isoformat(), "message": "Customer reports login issues", "type": "customer"},
    {"timestamp": datetime.now().isoformat(), "message": "Investigating authentication system", "type": "agent"}
])
session_state.create_checkpoint("initial_inquiry")

print(f"Session ID: {session_state.session_id}")
print(f"Customer ID: {session_state.get_state('customer_id')}")
print(f"Inquiry Type: {session_state.get_state('inquiry_type')}")
print(f"Priority: {session_state.get_state('priority')}")

# Save session state
session_state.save_to_file(f"session_{session_state.session_id}.json")
print("Session state saved to file")

# Simulate session interruption and restoration
print("\n--- Session Restored ---")
restored_state = StateManager()
if restored_state.load_from_file(f"session_{session_state.session_id}.json"):
    print(f"Restored Session: {restored_state.session_id}")
    print(f"Customer ID: {restored_state.get_state('customer_id')}")
    print(f"Conversation History: {len(restored_state.get_state('conversation_history', []))} messages")
    
    # Continue session with new information
    restored_state.set_state("resolution_status", "in_progress")
    restored_state.set_state("assigned_agent", "senior_tech_support")
    print("Session continued with new state updates")

print()

# Example 2: State-Based Conditional Workflows
print("Example 2: State-Based Conditional Workflows")
print("-" * 40)

# Create workflow state controller
workflow_controller = WorkflowStateController(restored_state)

# Define workflow rules
def high_priority_condition(state: Dict[str, Any]) -> bool:
    return state.get("priority") == "high" and state.get("resolution_status") == "in_progress"

def escalation_action(state_manager: StateManager) -> str:
    state_manager.set_state("escalated", True)
    state_manager.set_state("escalation_timestamp", datetime.now().isoformat())
    state_manager.set_state("escalation_reason", "high_priority_unresolved")
    return "Escalated to senior support team"

def auto_close_condition(state: Dict[str, Any]) -> bool:
    return state.get("resolution_status") == "resolved" and not state.get("customer_feedback_pending", True)

def auto_close_action(state_manager: StateManager) -> str:
    state_manager.set_state("case_status", "closed")
    state_manager.set_state("closed_timestamp", datetime.now().isoformat())
    return "Case automatically closed"

# Add workflow rules
workflow_controller.add_rule("high_priority_escalation", high_priority_condition, escalation_action)
workflow_controller.add_rule("auto_close_resolved", auto_close_condition, auto_close_action)

# Evaluate workflow rules
executed_rules = workflow_controller.evaluate_rules()
print(f"Executed Rules: {executed_rules}")

if "high_priority_escalation" in executed_rules:
    print("✅ Case escalated due to high priority")
    print(f"Escalated: {restored_state.get_state('escalated')}")
    print(f"Escalation Time: {restored_state.get_state('escalation_timestamp')}")

print()

# Example 3: State Versioning and Rollback
print("Example 3: State Versioning and Rollback")
print("-" * 40)

# Create multiple checkpoints during workflow
restored_state.set_state("troubleshooting_steps", [
    "checked_authentication_logs",
    "verified_user_credentials", 
    "tested_password_reset"
])
restored_state.create_checkpoint("troubleshooting_phase")

# Further progress
restored_state.set_state("resolution_found", True)
restored_state.set_state("solution", "Password reset link was blocked by email filter")
restored_state.set_state("resolution_status", "resolved")
restored_state.create_checkpoint("resolution_phase")

# Show state differences
diff = restored_state.get_state_diff("troubleshooting_phase")
print("State changes since troubleshooting phase:")
for key, change in diff.items():
    if change["action"] == "added":
        print(f"  + {key}: {change['value']}")
    elif change["action"] == "modified":
        print(f"  ~ {key}: {change['old_value']} → {change['new_value']}")

# Simulate rollback scenario (e.g., incorrect resolution)
print("\n--- Rollback Scenario ---")
restored_state.set_state("customer_feedback", "Issue not actually resolved")
restored_state.set_state("resolution_status", "reopened")

print("Customer feedback indicates issue not resolved. Rolling back...")
if restored_state.restore_checkpoint("troubleshooting_phase"):
    print("✅ State rolled back to troubleshooting phase")
    print(f"Current Status: {restored_state.get_state('resolution_status', 'unknown')}")
    print(f"Resolution Found: {restored_state.get_state('resolution_found', False)}")

print()

# Example 4: Multi-Agent State Coordination
print("Example 4: Multi-Agent State Coordination")
print("-" * 40)

# Shared state for multi-agent coordination
shared_state = StateManager("multi_agent_research_project")

# Initialize project state
shared_state.set_state("project_id", "RESEARCH_2024_001")
shared_state.set_state("project_phase", "planning")
shared_state.set_state("assigned_agents", [])
shared_state.set_state("completed_tasks", [])
shared_state.set_state("pending_tasks", ["market_research", "competitive_analysis", "technical_review"])

# Create state-aware agents
class StatefulAgent(Agent):
    def __init__(self, state_manager: StateManager, **kwargs):
        super().__init__(**kwargs)
        self.state_manager = state_manager
    
    def update_shared_state(self, key: str, value: Any):
        """Update shared state and log the change"""
        self.state_manager.set_state(key, value)
        self.state_manager.set_state(f"last_updated_by", self.name)
        self.state_manager.set_state(f"last_update_time", datetime.now().isoformat())

# Research Agent with state awareness
research_agent = StatefulAgent(
    state_manager=shared_state,
    name="Market Research Agent",
    role="Market Researcher",
    goal="Conduct comprehensive market research",
    backstory="Expert market researcher with access to various data sources",
    tools=[internet_search]
)

# Analysis Agent with state awareness  
analysis_agent = StatefulAgent(
    state_manager=shared_state,
    name="Analysis Agent", 
    role="Data Analyst",
    goal="Analyze research data and generate insights",
    backstory="Data analysis specialist with expertise in market trends"
)

# Simulate state-coordinated workflow
print("Initializing multi-agent research project...")

# Research agent updates state
research_agent.update_shared_state("current_agent", "Market Research Agent")
research_agent.update_shared_state("project_phase", "research")

# Simulate task completion
completed_tasks = shared_state.get_state("completed_tasks", [])
completed_tasks.append({
    "task": "market_research",
    "completed_by": "Market Research Agent",
    "completed_at": datetime.now().isoformat(),
    "result_summary": "Market size estimated at $2.5B with 15% growth rate"
})
shared_state.set_state("completed_tasks", completed_tasks)

# Update pending tasks
pending_tasks = shared_state.get_state("pending_tasks", [])
if "market_research" in pending_tasks:
    pending_tasks.remove("market_research")
shared_state.set_state("pending_tasks", pending_tasks)

print(f"Project Phase: {shared_state.get_state('project_phase')}")
print(f"Completed Tasks: {len(shared_state.get_state('completed_tasks', []))}")
print(f"Pending Tasks: {shared_state.get_state('pending_tasks', [])}")
print(f"Last Updated By: {shared_state.get_state('last_updated_by')}")

# Analysis agent takes over
analysis_agent.update_shared_state("current_agent", "Analysis Agent")
analysis_agent.update_shared_state("project_phase", "analysis")

print(f"\nHandoff complete:")
print(f"Current Agent: {shared_state.get_state('current_agent')}")
print(f"Project Phase: {shared_state.get_state('project_phase')}")

print()

# Example 5: State Analytics and Monitoring
print("Example 5: State Analytics and Monitoring")
print("-" * 40)

# Analyze state history
state_changes = len(shared_state.state_history)
print(f"Total State Changes: {state_changes}")

# Analyze state by time periods
recent_changes = [
    change for change in shared_state.state_history 
    if datetime.fromisoformat(change["timestamp"]) > 
       datetime.fromisoformat((datetime.now().isoformat())[:-10] + "00:00:00")
]
print(f"Recent State Changes: {len(recent_changes)}")

# Analyze checkpoints
checkpoints = list(shared_state.checkpoints.keys())
print(f"Available Checkpoints: {checkpoints}")

# Workflow rule execution summary
workflow_summary = workflow_controller.get_execution_summary()
print(f"Workflow Rules Executed: {workflow_summary['total_executions']}")
print(f"Rule Success Rate: {workflow_summary['success_rate']:.1%}")

# State complexity metrics
unique_keys = len(set(change["key"] for change in shared_state.state_history if "key" in change))
print(f"State Complexity (Unique Keys): {unique_keys}")

# Memory usage estimation (simplified)
state_size = len(json.dumps(shared_state.current_state))
print(f"Current State Size: {state_size} bytes")

print(f"\n=== State Management Summary ===")
print(f"✅ Cross-session persistence: Active")
print(f"✅ State versioning and rollback: {len(checkpoints)} checkpoints")
print(f"✅ Conditional workflows: {len(workflow_controller.workflow_rules)} rules")
print(f"✅ Multi-agent coordination: Shared state enabled")
print(f"✅ State analytics: {state_changes} changes tracked")
print(f"📊 System health: {workflow_summary['success_rate']:.1%} success rate")

print("\nAdvanced state management patterns example complete!")