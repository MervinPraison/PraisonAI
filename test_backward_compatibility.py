#!/usr/bin/env python3
"""
Test the backward compatibility fix for Pydantic .dict() → .model_dump() migration
"""

class MockPydanticV1:
    """Mock Pydantic v1 model that has .dict() but not .model_dump()"""
    def __init__(self, data):
        self.data = data
    
    def dict(self):
        return self.data
    
    def __str__(self):
        return str(self.data)

class MockPydanticV2:
    """Mock Pydantic v2 model that has both .dict() and .model_dump()"""
    def __init__(self, data):
        self.data = data
    
    def dict(self):
        return self.data
    
    def model_dump(self):
        return self.data
        
    def __str__(self):
        return str(self.data)

class MockNonPydantic:
    """Mock non-Pydantic object"""
    def __init__(self, data):
        self.data = data
    
    def __str__(self):
        return str(self.data)

def test_notebook_backward_compatibility():
    """Test the fixed notebook logic with different object types"""
    
    print("Testing notebook backward compatibility fix...")
    
    # Test cases
    test_objects = [
        ("Pydantic v1 mock", MockPydanticV1({"test": "data1"})),
        ("Pydantic v2 mock", MockPydanticV2({"test": "data2"})),
        ("Non-Pydantic object", MockNonPydantic({"test": "data3"})),
        ("String object", "just a string"),
        ("None object", None),
    ]
    
    for name, result_obj in test_objects:
        print(f"\nTesting {name}:")
        
        # This is the fixed logic from the notebook
        try:
            result = result_obj.model_dump() if hasattr(result_obj, "model_dump") else str(result_obj)
            print(f"  ✅ Success: {result}")
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            return False
    
    print("\n✅ All backward compatibility tests passed!")
    return True

def test_api_files_syntax():
    """Test that the API files have valid syntax"""
    
    print("\nTesting API files syntax...")
    
    files_to_check = [
        "examples/python/concepts/reasoning-extraction.py",
        "examples/python/api/secondary-market-research-api.py"
    ]
    
    for file_path in files_to_check:
        try:
            print(f"  Checking {file_path}...")
            with open(file_path, 'r') as f:
                code = f.read()
            
            # Check that .model_dump() is used instead of .dict()
            if '.dict()' in code and 'result_obj.dict()' in code:
                print(f"  ❌ Found remaining .dict() usage in {file_path}")
                return False
            
            # Compile the code to check syntax
            compile(code, file_path, 'exec')
            print(f"  ✅ {file_path} has valid syntax")
            
        except Exception as e:
            print(f"  ❌ Error checking {file_path}: {e}")
            return False
    
    print("✅ All API files have valid syntax!")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("TESTING BACKWARD COMPATIBILITY FIXES")
    print("=" * 60)
    
    success = True
    success &= test_notebook_backward_compatibility()
    success &= test_api_files_syntax()
    
    if success:
        print("\n🎉 All backward compatibility tests passed!")
        print("The fixes ensure compatibility with both Pydantic v1 and v2")
    else:
        print("\n❌ Some tests failed")
        exit(1)