"""
Production Telemetry Example

Demonstrates compatible telemetry setup with `enable_telemetry()` and
`TelemetryCollector` patterns.
"""

from contextlib import nullcontext
from praisonaiagents import Agent, Task, AgentTeam
from praisonaiagents.tools import duckduckgo
from praisonaiagents.telemetry import enable_telemetry, TelemetryCollector


def main() -> None:
    print("=" * 80)
    print("PRODUCTION TELEMETRY SETUP")
    print("=" * 80)

    # New API: no args
    enable_telemetry()
    collector = TelemetryCollector()

    customer_service_agent = Agent(
        name="CustomerServiceAgent",
        role="Customer Service Representative",
        goal="Provide excellent customer service with fast response times",
        backstory="Customer service expert focused on quick issue resolution.",
        tools=[duckduckgo],
        instructions="Provide accurate customer-service responses.",
    )

    requests = [
        "Customer asking about monthly bill charges",
        "Customer experiencing connectivity issues",
    ]

    for idx, description in enumerate(requests, start=1):
        trace_ctx = getattr(collector, "trace", None)
        trace_cm = trace_ctx(f"customer_request_{idx}") if callable(trace_ctx) else nullcontext()
        with trace_cm:
            task = Task(
                name=f"customer_request_{idx}",
                description=description,
                expected_output="Professional customer service response with solution",
                agent=customer_service_agent,
            )
            agents = AgentTeam(agents=[customer_service_agent], tasks=[task], output="minimal")
            result = agents.start()
            print(f"✅ Request {idx} completed, response length={len(str(result))}")

    print("\nTelemetry demonstration completed.")


if __name__ == "__main__":
    main()