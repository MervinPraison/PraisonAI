"""
Example 6: Context Injection for Agents

This example demonstrates how Fast Context results can be formatted
and injected into agent prompts for better code understanding.

Features:
- Multiple format styles (markdown, xml, plain)
- Token budget management
- Precision over recall (avoid context pollution)
"""

from praisonaiagents.context.fast import FastContext
from praisonaiagents.context.fast.context_injector import (
    ContextInjector,
    InjectionConfig,
    inject_fast_context
)

WORKSPACE = "/Users/praison/praisonai-package/src/praisonai-agents"


def main():
    print("=" * 70)
    print("Context Injection for Agents")
    print("=" * 70)
    
    # Search for code
    fc = FastContext(workspace_path=WORKSPACE)
    result = fc.search("class Agent")
    
    print(f"\nSearch results: {result.total_files} files found")
    
    # Markdown format (default)
    print("\n1. Markdown Format")
    print("-" * 40)
    
    config_md = InjectionConfig(
        max_tokens=2000,
        max_files=3,
        max_lines_per_file=20,
        format_style="markdown",
        include_line_numbers=True,
        include_file_content=True,
        prioritize_precision=True
    )
    
    injector_md = ContextInjector(config_md)
    md_context = injector_md.format_context(result)
    
    print(f"   Format: Markdown")
    print(f"   Length: {len(md_context)} chars (~{len(md_context)//4} tokens)")
    print(f"   Preview:")
    for line in md_context.split('\n')[:10]:
        print(f"   {line[:70]}")
    print("   ...")
    
    # XML format
    print("\n2. XML Format")
    print("-" * 40)
    
    config_xml = InjectionConfig(
        max_tokens=2000,
        max_files=3,
        format_style="xml",
        prioritize_precision=True
    )
    
    injector_xml = ContextInjector(config_xml)
    xml_context = injector_xml.format_context(result)
    
    print(f"   Format: XML")
    print(f"   Length: {len(xml_context)} chars")
    print(f"   Preview:")
    for line in xml_context.split('\n')[:10]:
        print(f"   {line[:70]}")
    print("   ...")
    
    # Plain text format
    print("\n3. Plain Text Format")
    print("-" * 40)
    
    config_plain = InjectionConfig(
        max_tokens=2000,
        max_files=3,
        format_style="plain"
    )
    
    injector_plain = ContextInjector(config_plain)
    plain_context = injector_plain.format_context(result)
    
    print(f"   Format: Plain")
    print(f"   Length: {len(plain_context)} chars")
    print(f"   Preview:")
    for line in plain_context.split('\n')[:8]:
        print(f"   {line[:70]}")
    print("   ...")
    
    # Inject into prompts
    print("\n4. Injecting into Prompts")
    print("-" * 40)
    
    system_prompt = "You are a helpful code assistant."
    user_message = "Explain how the Agent class works."
    
    injected = inject_fast_context(
        result=result,
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=1500,
        format_style="markdown"
    )
    
    print(f"   Original system prompt: {len(system_prompt)} chars")
    print(f"   Injected system prompt: {len(injected['system_prompt'])} chars")
    print(f"   User message unchanged: {injected['user_message'] == user_message}")
    
    # Token budget management
    print("\n5. Token Budget Management")
    print("-" * 40)
    
    budgets = [500, 1000, 2000, 4000]
    
    for budget in budgets:
        config = InjectionConfig(max_tokens=budget, max_files=10)
        injector = ContextInjector(config)
        context = injector.format_context(result)
        estimated_tokens = len(context) // 4
        print(f"   Budget: {budget} tokens -> {len(context)} chars (~{estimated_tokens} tokens)")
    
    # Precision mode
    print("\n6. Precision vs Recall")
    print("-" * 40)
    
    # High precision (fewer, more relevant results)
    config_precision = InjectionConfig(
        max_tokens=2000,
        max_files=5,
        prioritize_precision=True
    )
    injector_precision = ContextInjector(config_precision)
    precision_context = injector_precision.format_context(result)
    
    # Lower precision (more results)
    config_recall = InjectionConfig(
        max_tokens=2000,
        max_files=10,
        prioritize_precision=False
    )
    injector_recall = ContextInjector(config_recall)
    recall_context = injector_recall.format_context(result)
    
    print(f"   High precision mode: {len(precision_context)} chars")
    print(f"   High recall mode: {len(recall_context)} chars")
    print(f"   Precision mode is more focused for better agent understanding")
    
    print("\n" + "=" * 70)
    print("Context injection formats search results for optimal agent use!")
    print("=" * 70)


if __name__ == "__main__":
    main()
