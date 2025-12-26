"""MLflow Local Observability Demo (no API key needed)"""
import mlflow
import time

mlflow.set_tracking_uri("file:///tmp/mlflow_demo")
mlflow.set_experiment("praisonai-demo")

with mlflow.start_run(run_name="agent-trace"):
    mlflow.log_param("agent_name", "Assistant")
    mlflow.log_param("model", "gpt-4o-mini")
    
    # Simulate agent work
    start = time.time()
    time.sleep(0.1)
    latency = time.time() - start
    
    mlflow.log_metric("latency_ms", latency * 1000)
    mlflow.log_metric("tokens_used", 150)
    
    print(f"Logged run to MLflow: latency={latency*1000:.1f}ms")

print("PASSED: MLflow local observability works")
