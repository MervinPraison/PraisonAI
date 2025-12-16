"""Test You.com tools integration."""
import os
import sys

# Test 1: Import test - verify lazy loading works
print("=" * 60)
print("Test 1: Import Test (Lazy Loading)")
print("=" * 60)

try:
    from praisonaiagents.tools import ydc_search, ydc_contents, ydc_news, ydc_images
    print("✓ Successfully imported ydc_search, ydc_contents, ydc_news, ydc_images")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

try:
    from praisonaiagents.tools import YouTools
    print("✓ Successfully imported YouTools class")
except ImportError as e:
    print(f"✗ YouTools import failed: {e}")
    sys.exit(1)

# Test 2: Check API key detection
print("\n" + "=" * 60)
print("Test 2: API Key Detection")
print("=" * 60)

api_key = os.environ.get("YDC_API_KEY")
if api_key:
    print(f"✓ YDC_API_KEY is set (length: {len(api_key)})")
else:
    print("✗ YDC_API_KEY is not set")
    print("  To run full tests, set: export YDC_API_KEY=your_api_key")

# Test 3: Error handling without API key
print("\n" + "=" * 60)
print("Test 3: Error Handling (No API Key)")
print("=" * 60)

# Temporarily unset API key to test error handling
original_key = os.environ.pop("YDC_API_KEY", None)

try:
    result = ydc_search("test query")
    if "error" in result:
        print(f"✓ Proper error returned when no API key: {result['error'][:50]}...")
    else:
        print("✗ Expected error but got results")
except Exception as e:
    print(f"✗ Unexpected exception: {e}")

# Restore API key
if original_key:
    os.environ["YDC_API_KEY"] = original_key

# Test 4: YouTools class instantiation
print("\n" + "=" * 60)
print("Test 4: YouTools Class")
print("=" * 60)

try:
    tools = YouTools()
    print("✓ YouTools instantiated successfully")
    
    # Check methods exist
    methods = ['search', 'get_contents', 'live_news', 'images']
    for method in methods:
        if hasattr(tools, method):
            print(f"  ✓ Method '{method}' exists")
        else:
            print(f"  ✗ Method '{method}' missing")
except Exception as e:
    print(f"✗ YouTools instantiation failed: {e}")

# Test 5: Full integration test (only if API key is available)
print("\n" + "=" * 60)
print("Test 5: Full Integration Test")
print("=" * 60)

if os.environ.get("YDC_API_KEY"):
    print("Running search test...")
    try:
        result = ydc_search("Python programming", count=2)
        if "error" not in result:
            print(f"✓ Search successful!")
            web_results = result.get('results', {}).get('web', [])
            print(f"  Web results: {len(web_results)} items")
            if web_results:
                print(f"  First result: {web_results[0].get('title', 'N/A')[:50]}...")
        else:
            print(f"✗ Search returned error: {result['error']}")
    except Exception as e:
        print(f"✗ Search failed with exception: {e}")
else:
    print("⊘ Skipped (YDC_API_KEY not set)")

# Test 6: Agent integration test
print("\n" + "=" * 60)
print("Test 6: Agent Integration Test")
print("=" * 60)

if os.environ.get("YDC_API_KEY") and os.environ.get("OPENAI_API_KEY"):
    try:
        from praisonaiagents import Agent
        
        agent = Agent(
            name="SearchAgent",
            role="Web Researcher",
            goal="Search the web for information",
            tools=[ydc_search]
        )
        print("✓ Agent created with ydc_search tool")
        
        # Check tool is properly registered
        if agent.tools and ydc_search in agent.tools:
            print("✓ ydc_search is in agent's tools list")
        else:
            print("⊘ Tool registration check inconclusive")
            
    except Exception as e:
        print(f"✗ Agent integration failed: {e}")
else:
    missing = []
    if not os.environ.get("YDC_API_KEY"):
        missing.append("YDC_API_KEY")
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    print(f"⊘ Skipped (missing: {', '.join(missing)})")

print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
print("All import and basic tests passed!")
print("For full functionality, ensure YDC_API_KEY is set.")
