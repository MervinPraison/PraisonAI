#!/usr/bin/env python3
"""Test script for Trafilatura integration"""

import sys
import json

# Test URL (a safe public article)
test_url = "https://www.python.org/about/"

print("Testing Trafilatura integration for PraisonAI\n")
print("=" * 50)

# First, test if we can import the tools
try:
    from praisonaiagents.tools import extract_content, extract_metadata, trafilatura_tools
    print("✓ Successfully imported trafilatura tools")
except ImportError as e:
    print(f"✗ Failed to import trafilatura tools: {e}")
    print("\nNote: trafilatura might not be installed. Install with:")
    print("pip install trafilatura")
    sys.exit(1)

# Test 1: Extract content
print(f"\n1. Testing extract_content() with {test_url}")
print("-" * 50)
try:
    content = extract_content(test_url)
    if isinstance(content, dict) and 'error' not in content:
        print("✓ Content extraction successful")
        print(f"  - Title: {content.get('title', 'N/A')}")
        print(f"  - Author: {content.get('author', 'N/A')}")
        print(f"  - Date: {content.get('date', 'N/A')}")
        print(f"  - Text length: {len(content.get('text', ''))} characters")
        print(f"  - Language: {content.get('language', 'N/A')}")
    else:
        print(f"✗ Content extraction failed: {content}")
except Exception as e:
    print(f"✗ Error during content extraction: {e}")

# Test 2: Extract metadata
print(f"\n2. Testing extract_metadata() with {test_url}")
print("-" * 50)
try:
    metadata = extract_metadata(test_url)
    if isinstance(metadata, dict) and 'error' not in metadata:
        print("✓ Metadata extraction successful")
        for key, value in metadata.items():
            if key != 'url':
                print(f"  - {key}: {value}")
    else:
        print(f"✗ Metadata extraction failed: {metadata}")
except Exception as e:
    print(f"✗ Error during metadata extraction: {e}")

# Test 3: Extract text only
print(f"\n3. Testing extract_text_only() with {test_url}")
print("-" * 50)
try:
    from praisonaiagents.tools import extract_text_only
    text = extract_text_only(test_url)
    if isinstance(text, str) and not text.startswith("Could not"):
        print("✓ Text-only extraction successful")
        print(f"  - Text length: {len(text)} characters")
        print(f"  - First 100 chars: {text[:100]}...")
    else:
        print(f"✗ Text extraction failed: {text}")
except Exception as e:
    print(f"✗ Error during text extraction: {e}")

# Test 4: Compare with other tools
print(f"\n4. Testing compare_extraction() with {test_url}")
print("-" * 50)
try:
    from praisonaiagents.tools import compare_extraction
    comparison = compare_extraction(test_url, include_newspaper=False, include_spider=False)
    if isinstance(comparison, dict):
        print("✓ Comparison successful")
        if comparison.get('trafilatura') and 'error' not in comparison['trafilatura']:
            print("  - Trafilatura extraction: SUCCESS")
        else:
            print("  - Trafilatura extraction: FAILED")
    else:
        print(f"✗ Comparison failed: {comparison}")
except Exception as e:
    print(f"✗ Error during comparison: {e}")

# Test 5: Test URL validation (should reject localhost)
print("\n5. Testing URL validation (security)")
print("-" * 50)
unsafe_urls = [
    "http://localhost/test",
    "http://127.0.0.1/test",
    "http://169.254.169.254/metadata"
]
for unsafe_url in unsafe_urls:
    try:
        result = extract_content(unsafe_url)
        if isinstance(result, dict) and 'error' in result and 'Invalid or unsafe URL' in result['error']:
            print(f"✓ Correctly rejected unsafe URL: {unsafe_url}")
        else:
            print(f"✗ Failed to reject unsafe URL: {unsafe_url}")
    except Exception as e:
        print(f"✗ Unexpected error for {unsafe_url}: {e}")

print("\n" + "=" * 50)
print("Testing complete!")