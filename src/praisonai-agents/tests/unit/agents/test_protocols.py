"""Unit tests for agents/protocols.py"""
from praisonaiagents.agents.protocols import (
    MergeStrategyProtocol,
    FirstWinsMerge,
    ConcatMerge,
    DictMerge,
)


class TestMergeStrategyProtocol:
    """Tests for MergeStrategyProtocol."""
    
    def test_protocol_is_runtime_checkable(self):
        """Test protocol is runtime checkable."""
        assert isinstance(FirstWinsMerge(), MergeStrategyProtocol)
        assert isinstance(ConcatMerge(), MergeStrategyProtocol)
        assert isinstance(DictMerge(), MergeStrategyProtocol)
    
    def test_custom_implementation(self):
        """Test custom implementation matches protocol."""
        class CustomMerge:
            def merge(self, outputs, context=None):
                return outputs[-1] if outputs else None
        
        assert isinstance(CustomMerge(), MergeStrategyProtocol)
    
    def test_incomplete_implementation(self):
        """Test incomplete implementation doesn't match."""
        class IncompleteMerge:
            def other_method(self):
                pass
        
        assert not isinstance(IncompleteMerge(), MergeStrategyProtocol)


class TestFirstWinsMerge:
    """Tests for FirstWinsMerge."""
    
    def test_returns_first_non_none(self):
        """Test returns first non-None value."""
        merge = FirstWinsMerge()
        result = merge.merge([None, "first", "second"])
        assert result == "first"
    
    def test_skips_leading_nones(self):
        """Test skips leading None values."""
        merge = FirstWinsMerge()
        result = merge.merge([None, None, "third"])
        assert result == "third"
    
    def test_all_none_returns_none(self):
        """Test returns None when all values are None."""
        merge = FirstWinsMerge()
        result = merge.merge([None, None, None])
        assert result is None
    
    def test_empty_list_returns_none(self):
        """Test returns None for empty list."""
        merge = FirstWinsMerge()
        result = merge.merge([])
        assert result is None
    
    def test_single_value(self):
        """Test with single value."""
        merge = FirstWinsMerge()
        result = merge.merge(["only"])
        assert result == "only"
    
    def test_with_context(self):
        """Test context parameter is accepted."""
        merge = FirstWinsMerge()
        result = merge.merge(["value"], context={"agent": "test"})
        assert result == "value"
    
    def test_various_types(self):
        """Test with various types."""
        merge = FirstWinsMerge()
        assert merge.merge([None, 42]) == 42
        assert merge.merge([None, {"key": "value"}]) == {"key": "value"}
        assert merge.merge([None, [1, 2, 3]]) == [1, 2, 3]


class TestConcatMerge:
    """Tests for ConcatMerge."""
    
    def test_default_separator(self):
        """Test default separator is double newline."""
        merge = ConcatMerge()
        result = merge.merge(["a", "b", "c"])
        assert result == "a\n\nb\n\nc"
    
    def test_custom_separator(self):
        """Test custom separator."""
        merge = ConcatMerge(separator=" | ")
        result = merge.merge(["x", "y", "z"])
        assert result == "x | y | z"
    
    def test_skips_none_values(self):
        """Test None values are skipped."""
        merge = ConcatMerge(separator=", ")
        result = merge.merge(["a", None, "c"])
        assert result == "a, c"
    
    def test_converts_to_string(self):
        """Test non-string values are converted."""
        merge = ConcatMerge(separator="-")
        result = merge.merge([1, 2, 3])
        assert result == "1-2-3"
    
    def test_empty_list(self):
        """Test empty list returns empty string."""
        merge = ConcatMerge()
        result = merge.merge([])
        assert result == ""
    
    def test_all_none(self):
        """Test all None values returns empty string."""
        merge = ConcatMerge()
        result = merge.merge([None, None])
        assert result == ""
    
    def test_single_value(self):
        """Test single value."""
        merge = ConcatMerge()
        result = merge.merge(["only"])
        assert result == "only"
    
    def test_with_context(self):
        """Test context parameter is accepted."""
        merge = ConcatMerge()
        result = merge.merge(["a", "b"], context={"session": "123"})
        assert result == "a\n\nb"


class TestDictMerge:
    """Tests for DictMerge."""
    
    def test_basic_merge(self):
        """Test basic dictionary merge."""
        merge = DictMerge()
        result = merge.merge([{"a": 1}, {"b": 2}])
        assert result == {"a": 1, "b": 2}
    
    def test_later_overrides_earlier(self):
        """Test later values override earlier for same key."""
        merge = DictMerge()
        result = merge.merge([{"a": 1}, {"a": 2}])
        assert result == {"a": 2}
    
    def test_skips_none_values(self):
        """Test None values are skipped."""
        merge = DictMerge()
        result = merge.merge([{"a": 1}, None, {"b": 2}])
        assert result == {"a": 1, "b": 2}
    
    def test_skips_non_dict_values(self):
        """Test non-dict values are skipped."""
        merge = DictMerge()
        result = merge.merge([{"a": 1}, "not a dict", {"b": 2}])
        assert result == {"a": 1, "b": 2}
    
    def test_empty_list(self):
        """Test empty list returns empty dict."""
        merge = DictMerge()
        result = merge.merge([])
        assert result == {}
    
    def test_all_none(self):
        """Test all None returns empty dict."""
        merge = DictMerge()
        result = merge.merge([None, None])
        assert result == {}
    
    def test_shallow_merge_default(self):
        """Test shallow merge is default."""
        merge = DictMerge()
        result = merge.merge([
            {"nested": {"a": 1}},
            {"nested": {"b": 2}}
        ])
        # Shallow merge replaces entire nested dict
        assert result == {"nested": {"b": 2}}
    
    def test_deep_merge(self):
        """Test deep merge combines nested dicts."""
        merge = DictMerge(deep=True)
        result = merge.merge([
            {"nested": {"a": 1, "b": 2}},
            {"nested": {"b": 3, "c": 4}}
        ])
        assert result == {"nested": {"a": 1, "b": 3, "c": 4}}
    
    def test_deep_merge_multiple_levels(self):
        """Test deep merge with multiple nesting levels."""
        merge = DictMerge(deep=True)
        result = merge.merge([
            {"l1": {"l2": {"a": 1}}},
            {"l1": {"l2": {"b": 2}}}
        ])
        assert result == {"l1": {"l2": {"a": 1, "b": 2}}}
    
    def test_deep_merge_non_dict_override(self):
        """Test deep merge replaces non-dict with dict."""
        merge = DictMerge(deep=True)
        result = merge.merge([
            {"key": "string"},
            {"key": {"nested": "value"}}
        ])
        assert result == {"key": {"nested": "value"}}
    
    def test_with_context(self):
        """Test context parameter is accepted."""
        merge = DictMerge()
        result = merge.merge([{"a": 1}], context={"agent": "test"})
        assert result == {"a": 1}
    
    def test_complex_merge(self):
        """Test complex merge scenario."""
        merge = DictMerge()
        result = merge.merge([
            {"name": "Alice", "score": 10, "tags": ["a"]},
            {"name": "Bob", "level": 5},
            {"score": 20, "tags": ["b", "c"]}
        ])
        assert result == {
            "name": "Bob",
            "score": 20,
            "level": 5,
            "tags": ["b", "c"]
        }
