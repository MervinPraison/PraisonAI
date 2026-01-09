#!/usr/bin/env python3
"""
Example: Context Compression Demo

This example demonstrates:
1. Context compression for large retrieved content
2. Token budget management
3. Agent-centric knowledge retrieval with unique codes

Requirements:
- pip install praisonaiagents[knowledge]
- OPENAI_API_KEY environment variable

Usage:
    python compression_demo.py
"""

import os
import tempfile
import shutil

from praisonaiagents import Agent


# Unique verification code that CANNOT be guessed
SECRET_CODE = "COMPRESS-8K4M2"


def create_verbose_document(temp_dir: str) -> str:
    """Create a verbose document with a hidden unique code."""
    filepath = os.path.join(temp_dir, 'verbose_policy.txt')
    
    # Create a document with lots of filler text but one unique code
    with open(filepath, 'w') as f:
        f.write("""
ACME CORPORATION COMPREHENSIVE POLICY MANUAL
=============================================

CHAPTER 1: INTRODUCTION
-----------------------

This comprehensive policy manual outlines all procedures, guidelines, and 
requirements for employees of Acme Corporation. All employees are expected 
to read and understand this document in its entirety. This manual supersedes 
all previous versions and is effective immediately upon publication.

The purpose of this manual is to provide clear guidance on company policies,
procedures, and expectations. It covers a wide range of topics including but
not limited to workplace conduct, benefits, leave policies, and security
protocols.

CHAPTER 2: WORKPLACE CONDUCT
----------------------------

All employees are expected to maintain professional conduct at all times.
This includes treating colleagues with respect, maintaining a clean workspace,
and adhering to the company dress code. Violations of workplace conduct
policies may result in disciplinary action up to and including termination.

Professional behavior includes punctuality, meeting deadlines, and effective
communication with team members. Employees should report any concerns about
workplace conduct to their immediate supervisor or Human Resources.

CHAPTER 3: BENEFITS AND COMPENSATION
------------------------------------

Acme Corporation offers a comprehensive benefits package to all full-time
employees. This includes health insurance, dental coverage, vision care,
and a 401(k) retirement plan with company matching up to 6% of salary.

Employees are eligible for benefits after completing 90 days of employment.
Open enrollment occurs annually in November. Changes to benefits outside
of open enrollment require a qualifying life event.

CHAPTER 4: LEAVE POLICIES
-------------------------

Employees accrue paid time off (PTO) based on years of service:
- 0-2 years: 15 days per year
- 3-5 years: 20 days per year
- 6+ years: 25 days per year

Sick leave is provided separately at 10 days per year. Unused sick leave
may be carried over to the following year up to a maximum of 30 days.

CHAPTER 5: SECURITY PROTOCOLS
-----------------------------

All employees must follow strict security protocols to protect company
assets and confidential information. This includes using strong passwords,
locking workstations when away, and reporting any suspicious activity.

IMPORTANT: The master security verification code is: COMPRESS-8K4M2

This code is required for accessing secure areas and systems. Do not share
this code with unauthorized personnel. Misuse of security credentials is
grounds for immediate termination.

CHAPTER 6: EMERGENCY PROCEDURES
-------------------------------

In case of emergency, employees should follow the evacuation procedures
posted throughout the building. Assembly points are located in the parking
lot on the north side of the building.

Fire drills are conducted quarterly. All employees must participate in
fire drills and know the location of the nearest emergency exit.

CHAPTER 7: CONCLUSION
---------------------

This policy manual is a living document and may be updated periodically.
Employees will be notified of any changes via email and updated copies
will be made available on the company intranet.

Questions about any policy should be directed to Human Resources.

Document Version: 3.2.1
Last Updated: 2024-12-01
""")
    
    return filepath


def main():
    temp_dir = tempfile.mkdtemp(prefix='praison_compress_')
    
    try:
        print("=" * 60)
        print("Example: Context Compression Demo")
        print("=" * 60)
        
        # Create verbose document
        doc_path = create_verbose_document(temp_dir)
        print(f"\nCreated verbose document: {doc_path}")
        print(f"Secret code embedded: {SECRET_CODE}")
        
        # Demonstrate compression
        print("\n" + "-" * 40)
        print("Compression Demo")
        print("-" * 40)
        
        try:
            from praisonaiagents.rag import ContextCompressor
            
            # Read the document
            with open(doc_path, 'r') as f:
                content = f.read()
            
            print(f"\nOriginal document length: {len(content)} characters")
            
            # Compress with different ratios
            for ratio in [0.3, 0.5, 0.7]:
                compressor = ContextCompressor(
                    max_tokens=2000,
                    target_ratio=ratio,
                )
                result = compressor.compress([content], query="security verification code")
                
                print(f"\nCompression ratio {ratio}:")
                print(f"  Original tokens: {result.original_tokens}")
                print(f"  Compressed tokens: {result.compressed_tokens}")
                print(f"  Actual ratio: {result.compressed_tokens / max(result.original_tokens, 1):.2f}")
                
                # Check if secret code is preserved
                compressed_text = " ".join(result.chunks) if result.chunks else ""
                if SECRET_CODE in compressed_text:
                    print(f"  ✅ Secret code preserved in compressed output")
                else:
                    print(f"  ⚠️ Secret code may have been removed (query-focused compression)")
                    
        except ImportError as e:
            print(f"Note: Compression module not available: {e}")
        
        # Create agent with knowledge
        print("\n" + "-" * 40)
        print("Agent Knowledge Retrieval Test")
        print("-" * 40)
        
        agent = Agent(
            name="PolicyExpert",
            instructions="""You are a company policy expert.
Answer questions based ONLY on the provided knowledge context.
When asked about codes, provide the EXACT code from the documents.
Be concise but accurate.""",
            knowledge=[temp_dir],
            user_id="compression_demo_user",
            output="verbose",
        )
        
        # Test retrieval of the unique code
        print("\nQ: What is the master security verification code?")
        response = agent.chat("What is the master security verification code?")
        print(f"A: {response}")
        
        if SECRET_CODE in response.upper():
            print(f"\n✅ VERIFIED: Agent correctly retrieved the secret code!")
        else:
            print(f"\n❌ WARNING: Expected code {SECRET_CODE} not found in response")
        
        print("\n" + "=" * 60)
        print("Demo Complete")
        print("=" * 60)
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
