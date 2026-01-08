#!/usr/bin/env python3
"""
Example: Hierarchical Summaries Demo

This example demonstrates:
1. Building multi-level summaries (file → folder → project)
2. Query routing to appropriate summary level
3. Agent-centric knowledge retrieval with unique codes

Requirements:
- pip install praisonaiagents[knowledge]
- OPENAI_API_KEY environment variable

Usage:
    python hierarchical_summaries_demo.py
"""

import os
import tempfile
import shutil

from praisonaiagents import Agent


# Unique verification codes per department
DEPT_CODES = {
    "engineering": "ENG-7X2K9",
    "marketing": "MKT-3M5N8",
    "finance": "FIN-9P4Q1",
}


def create_hierarchical_corpus(temp_dir: str) -> dict:
    """Create a hierarchical corpus with departments and files."""
    structure = {}
    
    for dept, code in DEPT_CODES.items():
        dept_dir = os.path.join(temp_dir, dept)
        os.makedirs(dept_dir, exist_ok=True)
        structure[dept] = []
        
        # Create department overview
        overview_path = os.path.join(dept_dir, "overview.txt")
        with open(overview_path, 'w') as f:
            f.write(f"""
{dept.upper()} DEPARTMENT OVERVIEW
{'=' * 40}

Department: {dept.title()}
Department Code: {code}

Mission Statement:
The {dept.title()} department is responsible for driving excellence
in our organization through innovative solutions and dedicated teamwork.

Key Responsibilities:
- Strategic planning and execution
- Cross-functional collaboration
- Continuous improvement initiatives

Access Code: {code}
Use this code for all department-related system access.

Last Updated: 2024-12-01
""")
        structure[dept].append(overview_path)
        
        # Create team files
        for i, team in enumerate(["alpha", "beta", "gamma"]):
            team_path = os.path.join(dept_dir, f"team_{team}.txt")
            with open(team_path, 'w') as f:
                f.write(f"""
{dept.upper()} - TEAM {team.upper()}
{'=' * 40}

Team: {team.title()}
Department: {dept.title()}
Team Size: {5 + i * 2} members

Current Projects:
- Project {team.upper()}-001: In Progress
- Project {team.upper()}-002: Planning
- Project {team.upper()}-003: Completed

Team Lead: {team.title()} Lead
Contact: {team}@acme.com

Note: For department access, use code: {code}
""")
            structure[dept].append(team_path)
    
    return structure


def main():
    temp_dir = tempfile.mkdtemp(prefix='praison_hierarchy_')
    
    try:
        print("=" * 60)
        print("Example: Hierarchical Summaries Demo")
        print("=" * 60)
        
        # Create hierarchical corpus
        structure = create_hierarchical_corpus(temp_dir)
        total_files = sum(len(files) for files in structure.values())
        print(f"\nCreated hierarchical corpus:")
        print(f"  Departments: {len(structure)}")
        print(f"  Total files: {total_files}")
        print(f"  Location: {temp_dir}")
        
        for dept, files in structure.items():
            print(f"  - {dept}/: {len(files)} files (code: {DEPT_CODES[dept]})")
        
        # Demonstrate hierarchical summarizer
        print("\n" + "-" * 40)
        print("Hierarchical Summarizer Demo")
        print("-" * 40)
        
        try:
            from praisonaiagents.rag import HierarchicalSummarizer
            
            # Collect all files
            all_files = []
            for files in structure.values():
                all_files.extend(files)
            
            # Build hierarchy
            summarizer = HierarchicalSummarizer(max_levels=3)
            result = summarizer.build_hierarchy(all_files, base_path=temp_dir)
            
            print(f"\nHierarchy built:")
            print(f"  Levels: {summarizer.max_levels}")
            if hasattr(result, 'nodes'):
                print(f"  Summary nodes: {len(result.nodes)}")
            
            # Query at different levels
            print("\nQuery routing demonstration:")
            queries = [
                ("What is the engineering department code?", "engineering"),
                ("Tell me about marketing team alpha", "marketing"),
                ("What are the finance department responsibilities?", "finance"),
            ]
            
            for query, expected_dept in queries:
                print(f"\n  Query: {query}")
                # In a full implementation, this would route to the appropriate level
                print(f"  Expected department: {expected_dept}")
                print(f"  Expected code: {DEPT_CODES[expected_dept]}")
                
        except ImportError as e:
            print(f"Note: Hierarchical summarizer not available: {e}")
        except Exception as e:
            print(f"Note: Hierarchy building skipped: {e}")
        
        # Create agent with knowledge
        print("\n" + "-" * 40)
        print("Agent Knowledge Retrieval Test")
        print("-" * 40)
        
        agent = Agent(
            name="DepartmentExpert",
            instructions="""You are a department information expert.
Answer questions based ONLY on the provided knowledge context.
When asked about department codes, provide the EXACT code from the documents.
Be specific about which department you're referring to.""",
            knowledge=[temp_dir],
            user_id="hierarchy_demo_user",
            verbose=True,
        )
        
        # Test retrieval of department codes
        test_cases = [
            ("What is the engineering department access code?", "ENG-7X2K9"),
            ("What is the marketing department code?", "MKT-3M5N8"),
            ("What is the finance department code?", "FIN-9P4Q1"),
        ]
        
        print("\nTesting retrieval of department codes:\n")
        
        for question, expected_code in test_cases:
            print(f"Q: {question}")
            response = agent.chat(question)
            print(f"A: {response[:200]}...")
            
            if expected_code in response.upper():
                print(f"✅ VERIFIED: Found code {expected_code}\n")
            else:
                print(f"❌ WARNING: Expected code {expected_code} not found\n")
        
        print("=" * 60)
        print("Demo Complete")
        print("=" * 60)
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
