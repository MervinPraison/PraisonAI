#!/usr/bin/env python3
"""
Example: Bot In-Flight Run Control

Demonstrates how to use SessionRunControl to provide better UX for bots
during long-running agent operations. Shows busy feedback, pending message
handling, and /stop command support.

This example shows the "before" and "after" behavior described in issue #1914.
"""

import asyncio
import time
from typing import Optional

# Mock agent for demonstration
class MockAgent:
    """Simple mock agent that simulates long-running tasks."""
    
    def __init__(self, name="assistant"):
        self.name = name
        self.chat_history = []
        self._interrupt_controller = None
    
    def chat(self, prompt: str) -> str:
        """Simulate a long-running chat response."""
        print(f"[Agent] Starting to process: '{prompt[:50]}...'")
        
        # Simulate long processing with interrupt checking
        for i in range(30):  # 3 second task (30 x 0.1s)
            time.sleep(0.1)
            
            # Check for interruption
            if (self._interrupt_controller and 
                hasattr(self._interrupt_controller, 'is_set') and
                self._interrupt_controller.is_set()):
                reason = getattr(self._interrupt_controller, 'reason', 'unknown')
                print(f"[Agent] ⚠️ Interrupted: {reason}")
                raise InterruptedError(f"Task cancelled: {reason}")
                
        response = f"Completed analysis of: {prompt}"
        print(f"[Agent] ✅ Finished: {response}")
        return response


async def demo_without_run_control():
    """Demonstrate the old behavior (silent blocking)."""
    print("\n" + "="*60)
    print("🔴 BEFORE: Without Run Control (Silent Blocking)")
    print("="*60)
    
    from praisonai.bots._session import BotSessionManager
    
    # Standard session manager (no run control)
    session_mgr = BotSessionManager()
    agent = MockAgent("research-agent")
    user_id = "user123"
    
    print("\n1. User sends long task:")
    print("   User: 'research quantum computing trends'")
    
    # Start first task (this will run for 3 seconds)
    task1 = asyncio.create_task(
        session_mgr.chat(agent, user_id, "research quantum computing trends")
    )
    
    # Simulate user sending follow-up messages during execution
    await asyncio.sleep(0.5)
    print("\n2. User sends follow-up (this will block silently):")
    print("   User: 'actually focus on business impact'")
    
    task2 = asyncio.create_task(
        session_mgr.chat(agent, user_id, "actually focus on business impact")  
    )
    
    await asyncio.sleep(0.5)
    print("\n3. User tries to send /stop (this will also block):")
    print("   User: '/stop'")
    
    task3 = asyncio.create_task(
        session_mgr.chat(agent, user_id, "/stop")
    )
    
    print("\n⏳ Waiting for all messages to complete...")
    results = await asyncio.gather(task1, task2, task3)
    
    print("\n📊 Results (all processed sequentially with no feedback):")
    for i, result in enumerate(results, 1):
        print(f"   {i}. {result}")
    
    print("\n❌ Problems with this approach:")
    print("   - No immediate feedback on follow-up messages")
    print("   - No way to cancel long-running tasks") 
    print("   - User doesn't know if bot is working or broken")


async def demo_with_run_control():
    """Demonstrate the new behavior with run control."""
    print("\n" + "="*60)
    print("🟢 AFTER: With Run Control (Better UX)")  
    print("="*60)
    
    from praisonai.bots._run_control import SessionRunControl
    from praisonai.bots._session import BotSessionManager
    from praisonai.bots._commands import handle_stop_command
    
    # Session manager with run control
    run_control = SessionRunControl(
        busy_mode="queue",
        busy_ack_template="⏳ {action} — will process after current task finishes"
    )
    session_mgr = BotSessionManager(run_control=run_control)
    agent = MockAgent("research-agent")
    user_id = "user123"
    
    print("\n1. User sends long task:")
    print("   User: 'research quantum computing trends'")
    
    # Start first task
    task1 = asyncio.create_task(
        session_mgr.chat_with_run_control(agent, user_id, "research quantum computing trends")
    )
    
    # Immediate follow-up messages get acknowledgments
    await asyncio.sleep(0.5)
    print("\n2. User sends follow-up (gets immediate feedback):")
    print("   User: 'actually focus on business impact'")
    
    result2 = await session_mgr.chat_with_run_control(
        agent, user_id, "actually focus on business impact"
    )
    print(f"   Bot: {result2['response']}")
    print(f"   Metadata: {result2['metadata']}")
    
    await asyncio.sleep(0.5)
    print("\n3. User decides to stop current task:")
    print("   User: '/stop'")
    
    stop_response = await handle_stop_command(user_id, run_control)
    print(f"   Bot: {stop_response}")
    
    # Wait for first task to complete (it should be cancelled)
    try:
        result1 = await task1
        print(f"\n📊 Task 1 result: {result1['response']}")
        print(f"   Metadata: {result1['metadata']}")
    except asyncio.CancelledError:
        print("\n📊 Task 1 was cancelled as expected")
    
    print("\n4. User sends fresh request after stopping:")
    print("   User: 'what's the weather like?'")
    
    result4 = await session_mgr.chat_with_run_control(
        agent, user_id, "what's the weather like?"
    )
    print(f"   Bot: {result4['response']}")
    
    print("\n✅ Benefits of this approach:")
    print("   - Immediate feedback on all messages")
    print("   - Can cancel long-running tasks with /stop")
    print("   - Pending messages are queued and processed in order")
    print("   - User always knows what's happening")


async def demo_interrupt_mode():
    """Demonstrate interrupt mode."""
    print("\n" + "="*60)
    print("⚡ BONUS: Interrupt Mode (Cancel and Restart)")
    print("="*60)
    
    from praisonai.bots._run_control import SessionRunControl
    from praisonai.bots._session import BotSessionManager
    
    # Use interrupt mode instead of queue mode
    run_control = SessionRunControl(busy_mode="interrupt")
    session_mgr = BotSessionManager(run_control=run_control)
    agent = MockAgent("research-agent")
    user_id = "user123"
    
    print("\n1. User starts long task:")
    print("   User: 'research renewable energy for 30 pages'")
    
    task1 = asyncio.create_task(
        session_mgr.chat_with_run_control(agent, user_id, "research renewable energy for 30 pages")
    )
    
    await asyncio.sleep(0.5)
    print("\n2. User changes mind (interrupts and restarts):")
    print("   User: 'actually just summarize solar panel efficiency'")
    
    result2 = await session_mgr.chat_with_run_control(
        agent, user_id, "actually just summarize solar panel efficiency"
    )
    print(f"   Bot: {result2['response']}")
    
    # Wait for original task (should be interrupted)
    try:
        result1 = await task1
        print(f"\n📊 Original task result: {result1['response']}")
        if result1['metadata'].get('interrupted'):
            print("   ✅ Original task was properly interrupted")
    except:
        print("\n📊 Original task was cancelled")
    
    print("\n✅ Interrupt mode is great for:")
    print("   - When users frequently change direction")
    print("   - Interactive sessions where latest intent matters most")
    print("   - Real-time collaboration scenarios")


async def main():
    """Run all demonstrations."""
    print("🚀 Bot In-Flight Run Control Demo")
    print("Solving the silent lock problem described in issue #1914")
    
    # Show the problem
    await demo_without_run_control()
    
    # Show the solution  
    await demo_with_run_control()
    
    # Show advanced feature
    await demo_interrupt_mode()
    
    print("\n" + "="*60)
    print("🎯 Summary")
    print("="*60)
    print("SessionRunControl solves the silent blocking problem by providing:")
    print("1. Immediate feedback for mid-run messages")
    print("2. /stop command support via InterruptController")
    print("3. Configurable policies (queue/interrupt/steer)")
    print("4. Run generation tracking to prevent race conditions")
    print("5. Pending message merging and ordering")
    print("\nThis makes bot interactions feel responsive and predictable!")


if __name__ == "__main__":
    asyncio.run(main())