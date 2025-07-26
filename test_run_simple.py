#!/usr/bin/env python3

# Let me see if we can inspect the source directly without import issues
import ast
import inspect

# Read the agents.py file as text
with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents/agents/agents.py', 'r') as f:
    source = f.read()

# Parse the AST to look for class definition
tree = ast.parse(source)

# Find the PraisonAIAgents class
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == 'PraisonAIAgents':
        print(f"Found class {node.name}")
        print("Methods in the class:")
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                print(f"  def {item.name}")
        
        # Look for any assignment to run
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == 'run':
                        print(f"Found assignment: run = ...")
                        print(f"Value: {ast.dump(item.value)}")

# Also check if there are any assignments after the class
in_class = False
class_ended = False
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == 'PraisonAIAgents':
        in_class = True
    elif in_class and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(node, ast.ClassDef):
        class_ended = True
    elif class_ended and isinstance(node, ast.Assign):
        # Check if any assignment involves PraisonAIAgents.run
        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'PraisonAIAgents' and target.attr == 'run':
                print(f"Found post-class assignment: PraisonAIAgents.run = ...")
                print(f"Value: {ast.dump(node.value)}")

print("\nNow checking if run method exists at module level...")

# Look for any assignment at module level 
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'PraisonAIAgents' and target.attr == 'run':
                print(f"Found module-level assignment: PraisonAIAgents.run = ...")
                if isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name) and node.value.value.id == 'PraisonAIAgents' and node.value.attr == 'start':
                    print("Assignment is: PraisonAIAgents.run = PraisonAIAgents.start")