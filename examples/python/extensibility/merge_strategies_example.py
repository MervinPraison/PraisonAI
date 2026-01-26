"""Example: Merge Strategies for Multi-Agent Workflows

This example demonstrates how to use and create custom merge strategies
for combining outputs from parallel agent executions.
"""
from praisonaiagents.agents import (
    MergeStrategyProtocol,
    FirstWinsMerge,
    ConcatMerge,
    DictMerge,
)


def example_first_wins_merge():
    """Demonstrate FirstWinsMerge strategy."""
    print("=" * 50)
    print("FirstWinsMerge Examples")
    print("=" * 50)
    
    merge = FirstWinsMerge()
    
    # 1. Basic usage - returns first non-None
    print("\n1. Basic Usage:")
    outputs = [None, "Agent 2 response", "Agent 3 response"]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")
    
    # 2. All None returns None
    print("\n2. All None:")
    outputs = [None, None, None]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")
    
    # 3. First value wins
    print("\n3. First Value Wins:")
    outputs = ["Fast agent", "Slow agent", "Slowest agent"]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")
    
    # 4. Works with any type
    print("\n4. Various Types:")
    print(f"   Dict: {merge.merge([None, {'key': 'value'}])}")
    print(f"   List: {merge.merge([None, [1, 2, 3]])}")
    print(f"   Number: {merge.merge([None, 42])}")


def example_concat_merge():
    """Demonstrate ConcatMerge strategy."""
    print("\n" + "=" * 50)
    print("ConcatMerge Examples")
    print("=" * 50)
    
    # 1. Default separator (double newline)
    print("\n1. Default Separator:")
    merge = ConcatMerge()
    outputs = ["Part 1: Introduction", "Part 2: Analysis", "Part 3: Conclusion"]
    result = merge.merge(outputs)
    print(f"   Result:\n{result}")
    
    # 2. Custom separator
    print("\n2. Custom Separator:")
    merge = ConcatMerge(separator=" | ")
    outputs = ["Alice", "Bob", "Charlie"]
    result = merge.merge(outputs)
    print(f"   Result: {result}")
    
    # 3. Skips None values
    print("\n3. Skips None:")
    merge = ConcatMerge(separator=", ")
    outputs = ["A", None, "C", None, "E"]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")
    
    # 4. Converts non-strings
    print("\n4. Converts Non-Strings:")
    merge = ConcatMerge(separator=" + ")
    outputs = [1, 2, 3]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")


def example_dict_merge():
    """Demonstrate DictMerge strategy."""
    print("\n" + "=" * 50)
    print("DictMerge Examples")
    print("=" * 50)
    
    # 1. Basic shallow merge
    print("\n1. Shallow Merge (default):")
    merge = DictMerge()
    outputs = [
        {"name": "Alice", "score": 10},
        {"name": "Bob", "level": 5},
        {"score": 20, "rank": 1}
    ]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")
    
    # 2. Later values override
    print("\n2. Override Behavior:")
    merge = DictMerge()
    outputs = [
        {"status": "pending"},
        {"status": "processing"},
        {"status": "complete"}
    ]
    result = merge.merge(outputs)
    print(f"   Result: {result}")
    
    # 3. Deep merge for nested dicts
    print("\n3. Deep Merge:")
    merge = DictMerge(deep=True)
    outputs = [
        {"config": {"a": 1, "b": 2}},
        {"config": {"b": 3, "c": 4}},
        {"config": {"d": 5}}
    ]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")
    
    # 4. Skips non-dict values
    print("\n4. Skips Non-Dict Values:")
    merge = DictMerge()
    outputs = [{"a": 1}, "not a dict", None, {"b": 2}]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")


def example_custom_merge():
    """Demonstrate creating custom merge strategies."""
    print("\n" + "=" * 50)
    print("Custom Merge Strategy Examples")
    print("=" * 50)
    
    # 1. Longest output merge
    class LongestOutputMerge:
        """Returns the longest output."""
        def merge(self, outputs, context=None):
            valid = [o for o in outputs if o is not None]
            if not valid:
                return None
            return max(valid, key=lambda x: len(str(x)))
    
    print("\n1. LongestOutputMerge:")
    merge = LongestOutputMerge()
    outputs = ["short", "medium length", "this is the longest response"]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result}")
    
    # 2. Majority vote merge
    class MajorityVoteMerge:
        """Returns the most common output."""
        def merge(self, outputs, context=None):
            from collections import Counter
            valid = [o for o in outputs if o is not None]
            if not valid:
                return None
            counts = Counter(valid)
            return counts.most_common(1)[0][0]
    
    print("\n2. MajorityVoteMerge:")
    merge = MajorityVoteMerge()
    outputs = ["yes", "yes", "no", "yes", "no"]
    result = merge.merge(outputs)
    print(f"   Inputs: {outputs}")
    print(f"   Result: {result} (3 votes)")
    
    # 3. Weighted merge
    class WeightedMerge:
        """Merges with agent weights from context."""
        def merge(self, outputs, context=None):
            weights = context.get("weights", [1] * len(outputs)) if context else [1] * len(outputs)
            best_idx = 0
            best_weight = 0
            for i, (output, weight) in enumerate(zip(outputs, weights)):
                if output is not None and weight > best_weight:
                    best_idx = i
                    best_weight = weight
            return outputs[best_idx] if outputs else None
    
    print("\n3. WeightedMerge:")
    merge = WeightedMerge()
    outputs = ["junior answer", "senior answer", "expert answer"]
    context = {"weights": [1, 5, 10]}
    result = merge.merge(outputs, context=context)
    print(f"   Inputs: {outputs}")
    print(f"   Weights: {context['weights']}")
    print(f"   Result: {result}")
    
    # 4. Protocol compliance
    print("\n4. Protocol Compliance:")
    print(f"   LongestOutputMerge: {isinstance(LongestOutputMerge(), MergeStrategyProtocol)}")
    print(f"   MajorityVoteMerge: {isinstance(MajorityVoteMerge(), MergeStrategyProtocol)}")
    print(f"   WeightedMerge: {isinstance(WeightedMerge(), MergeStrategyProtocol)}")


if __name__ == "__main__":
    example_first_wins_merge()
    example_concat_merge()
    example_dict_merge()
    example_custom_merge()
    
    print("\n" + "=" * 50)
    print("All examples completed!")
    print("=" * 50)
