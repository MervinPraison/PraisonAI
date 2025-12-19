"""
Unit tests for PraisonAI Profiler module.
"""

import time


class TestProfiler:
    """Test Profiler class."""
    
    def test_profiler_singleton(self):
        """Should return same instance."""
        from praisonai.profiler import Profiler
        
        p1 = Profiler()
        p2 = Profiler()
        assert p1 is p2
    
    def test_enable_disable(self):
        """Should enable and disable profiling."""
        from praisonai.profiler import Profiler
        
        Profiler.disable()
        assert not Profiler.is_enabled()
        
        Profiler.enable()
        assert Profiler.is_enabled()
        
        Profiler.disable()
    
    def test_record_timing(self):
        """Should record timing."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("test_op", 100.5, "test")
        
        timings = Profiler.get_timings()
        assert len(timings) >= 1
        assert timings[-1].name == "test_op"
        assert timings[-1].duration_ms == 100.5
        
        Profiler.disable()
        Profiler.clear()
    
    def test_record_import(self):
        """Should record import timing."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_import("test_module", 50.0)
        
        imports = Profiler.get_imports()
        assert len(imports) >= 1
        assert imports[-1].module == "test_module"
        
        Profiler.disable()
        Profiler.clear()
    
    def test_block_context_manager(self):
        """Should profile a block of code."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        with Profiler.block("test_block"):
            time.sleep(0.01)
        
        timings = Profiler.get_timings(category="block")
        assert len(timings) >= 1
        assert timings[-1].name == "test_block"
        assert timings[-1].duration_ms >= 10
        
        Profiler.disable()
        Profiler.clear()
    
    def test_get_summary(self):
        """Should return summary."""
        from praisonai.profiler import Profiler
        
        Profiler.enable()
        Profiler.clear()
        
        Profiler.record_timing("op1", 100, "function")
        Profiler.record_timing("op2", 200, "function")
        Profiler.record_import("mod1", 50)
        
        summary = Profiler.get_summary()
        
        assert summary['total_time_ms'] == 300
        assert summary['import_time_ms'] == 50
        assert summary['timing_count'] == 2
        assert summary['import_count'] == 1
        
        Profiler.disable()
        Profiler.clear()


class TestProfileDecorator:
    """Test @profile decorator."""
    
    def test_profile_function(self):
        """Should profile a function."""
        from praisonai.profiler import Profiler, profile
        
        Profiler.enable()
        Profiler.clear()
        
        @profile
        def test_func():
            time.sleep(0.01)
            return "result"
        
        result = test_func()
        
        assert result == "result"
        
        timings = Profiler.get_timings(category="function")
        assert len(timings) >= 1
        assert timings[-1].name == "test_func"
        assert timings[-1].duration_ms >= 10
        
        Profiler.disable()
        Profiler.clear()
    
    def test_profile_with_category(self):
        """Should profile with custom category."""
        from praisonai.profiler import Profiler, profile
        
        Profiler.enable()
        Profiler.clear()
        
        @profile(category="api")
        def api_call():
            return "response"
        
        api_call()
        
        timings = Profiler.get_timings(category="api")
        assert len(timings) >= 1
        assert timings[-1].name == "api_call"
        
        Profiler.disable()
        Profiler.clear()
    
    def test_profile_disabled(self):
        """Should not record when disabled."""
        from praisonai.profiler import Profiler, profile
        
        Profiler.disable()
        Profiler.clear()
        
        @profile
        def test_func():
            return "result"
        
        test_func()
        
        timings = Profiler.get_timings()
        assert len(timings) == 0


class TestImportProfiler:
    """Test ImportProfiler."""
    
    def test_profile_imports(self):
        """Should profile imports."""
        from praisonai.profiler import profile_imports
        
        with profile_imports() as profiler:
            import json
            import re
        
        imports = profiler.get_imports()
        # May or may not have imports depending on cache
        assert isinstance(imports, list)
    
    def test_get_slowest(self):
        """Should get slowest imports."""
        from praisonai.profiler import profile_imports
        
        with profile_imports() as profiler:
            import collections
        
        slowest = profiler.get_slowest(5)
        assert isinstance(slowest, list)
        assert len(slowest) <= 5


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_check_module_available(self):
        """Should check module availability."""
        from praisonai.profiler import check_module_available
        
        assert check_module_available("os") is True
        assert check_module_available("nonexistent_module_xyz") is False
    
    def test_time_import(self):
        """Should time import."""
        from praisonai.profiler import time_import
        
        duration = time_import("json")
        assert isinstance(duration, float)
        assert duration >= 0


class TestDataClasses:
    """Test data classes."""
    
    def test_timing_record(self):
        """Should create TimingRecord."""
        from praisonai.profiler import TimingRecord
        
        record = TimingRecord(
            name="test",
            duration_ms=100.0,
            category="function",
            file="test.py",
            line=10
        )
        
        assert record.name == "test"
        assert record.duration_ms == 100.0
        assert record.category == "function"
    
    def test_import_record(self):
        """Should create ImportRecord."""
        from praisonai.profiler import ImportRecord
        
        record = ImportRecord(
            module="test_module",
            duration_ms=50.0,
            parent="parent_module"
        )
        
        assert record.module == "test_module"
        assert record.duration_ms == 50.0
    
    def test_flow_record(self):
        """Should create FlowRecord."""
        from praisonai.profiler import FlowRecord
        
        record = FlowRecord(
            step=1,
            name="step1",
            file="test.py",
            line=20,
            duration_ms=30.0
        )
        
        assert record.step == 1
        assert record.name == "step1"
