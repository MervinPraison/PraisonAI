import json
from e2b_code_interpreter import Sandbox

def code_interpret(code: str):
    print(f"\n{'='*50}\n> Running following AI-generated code:\n{code}\n{'='*50}")
    exec = Sandbox().run_code(code)

    if exec.error:
        print("[Code Interpreter error]", exec.error)
        return {"error": str(exec.error)}
    else:
        results = []
        for result in exec.results:
            # Ensure each result is a list or a simple Python type
            if hasattr(result, '__iter__'):
                result_list = list(result)  # Convert Result to list
                results.extend(result_list)
            else:
                results.append(str(result))  # Fall back to string

        logs = {"stdout": list(exec.logs.stdout), "stderr": list(exec.logs.stderr)}

        # Now everything is JSON-serialisable
        return json.dumps({"results": results, "logs": logs})
