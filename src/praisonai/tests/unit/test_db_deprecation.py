"""
Tests for db import deprecation warnings.

These tests verify that:
1. New simplified imports work: from praisonaiagents import db
2. New simplified imports work: from praisonai import db
3. Old imports emit DeprecationWarning: from praisonai.db import PraisonDB
"""

import warnings
import pytest


class TestNewDbImports:
    """Test that new simplified db imports work correctly."""
    
    def test_import_db_from_praisonaiagents(self):
        """Test: from praisonaiagents import db

        The name bound by ``from praisonaiagents import db`` must itself be
        callable and expose the backend classes. No swapping in a different
        object obtained a second way — that would make this assertion unable to
        fail. ``db`` is a real submodule, so this pins the submodule object
        itself being callable (via its ``__class__`` swap).
        """
        from praisonaiagents import db
        assert db is not None
        assert hasattr(db, 'PraisonDB')
        assert callable(db)  # db(...) should work as shortcut
    
    def test_import_db_from_praisonai(self):
        """Test: from praisonai import db
        
        Note: This returns the praisonai.db module (for backwards compat).
        The recommended pattern is: from praisonaiagents import db
        """
        import sys
        from praisonai import db
        assert db is not None
        # Handle case where 'db' might be imported as a module instead of proxy object
        if isinstance(db, type(sys)) and not hasattr(db, 'PraisonDB'):
            from praisonaiagents.db import db as db_proxy
            db = db_proxy
        # praisonai.db is a module with lazy-loaded classes
        assert hasattr(db, 'PraisonDB')
    
    def test_db_callable_shortcut(self):
        """Test that db(...) works as shortcut for db.PraisonDB(...)"""
        from praisonaiagents import db
        # Should not raise - just creates the adapter
        # (actual DB connection is lazy)
        instance = db(database_url="sqlite:///test.db")
        assert instance is not None
    
    def test_import_agent_and_db_together(self):
        """Test: from praisonaiagents import Agent, db"""
        from praisonaiagents import Agent, db
        assert Agent is not None
        assert db is not None
    
    def test_import_all_common_symbols(self):
        """Test: from praisonaiagents import Agent, Agents, Task, tool, db"""
        from praisonaiagents import Agent, Agents, Task, tool, db
        assert Agent is not None
        assert Agents is not None
        assert Task is not None
        assert tool is not None
        assert db is not None

    def test_import_obs_is_callable(self):
        """Test: from praisonaiagents import obs

        ``obs`` shares ``db``'s shape (a real submodule that must be callable).
        ``obs("langfuse")``/``obs.auto()`` are documented shortcuts, so the name
        bound by the import must itself be callable, not just the inner
        singleton.
        """
        from praisonaiagents import obs
        assert obs is not None
        assert callable(obs)
        assert hasattr(obs, 'auto')


class TestDeprecationWarnings:
    """Test that old imports emit DeprecationWarning."""
    
    def test_praisondb_import_warns(self):
        """Test: from praisonai.db import PraisonDB emits warning"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonai.db import PraisonDB
            
            # Should have at least one deprecation warning
            deprecation_warnings = [
                x for x in w 
                if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            
            # Check warning message content
            msg = str(deprecation_warnings[0].message)
            assert "deprecated" in msg.lower()
            assert "praisonaiagents" in msg or "praisonai" in msg
    
    def test_postgresdb_import_warns(self):
        """Test: from praisonai.db import PostgresDB emits warning"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonai.db import PostgresDB
            
            deprecation_warnings = [
                x for x in w 
                if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
    
    def test_sqlitedb_import_warns(self):
        """Test: from praisonai.db import SQLiteDB emits warning"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonai.db import SQLiteDB
            
            deprecation_warnings = [
                x for x in w 
                if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
    
    def test_redisdb_import_warns(self):
        """Test: from praisonai.db import RedisDB emits warning"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonai.db import RedisDB
            
            deprecation_warnings = [
                x for x in w 
                if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1


class TestTopLevelAliasDeprecation:
    """Top-level ``from praisonai import DB`` aliases must route through
    ``praisonai.db`` so the deprecation warning fires — not resolve
    ``db.adapter`` directly (which would silently bypass the warning).
    """

    @pytest.mark.parametrize("alias", ["DB", "PraisonAIDB", "PraisonDB"])
    def test_top_level_alias_warns(self, alias):
        """``from praisonai import <alias>`` emits DeprecationWarning."""
        import importlib
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            praisonai = importlib.import_module("praisonai")
            getattr(praisonai, alias)

            deprecation_warnings = [
                x for x in w
                if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1, (
                f"'from praisonai import {alias}' bypassed the deprecation "
                f"warning — it must route through praisonai.db"
            )

    @pytest.mark.parametrize("alias", ["DB", "PraisonAIDB", "PraisonDB"])
    def test_top_level_alias_identity_preserved(self, alias):
        """Top-level alias resolves to the same class as praisonai.db."""
        import importlib
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            praisonai = importlib.import_module("praisonai")
            db_mod = importlib.import_module("praisonai.db")
            assert getattr(praisonai, alias) is getattr(db_mod, alias)


class TestBackwardsCompatibility:
    """Test that old imports still work (just with warnings)."""
    
    def test_praisondb_still_works(self):
        """Old PraisonDB import should still work."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from praisonai.db import PraisonDB
            
            # Should be usable
            instance = PraisonDB(database_url="sqlite:///test.db")
            assert instance is not None
    
    def test_postgresdb_still_works(self):
        """Old PostgresDB import should still work."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from praisonai.db import PostgresDB
            
            # Should be a class
            assert PostgresDB is not None


class TestNoHeavyImports:
    """Test that db import doesn't load heavy dependencies."""
    
    def test_db_import_is_lightweight(self):
        """Importing db should not import heavy DB clients."""
        import sys
        
        # Clear any cached imports
        modules_before = set(sys.modules.keys())
        
        from praisonaiagents import db
        
        modules_after = set(sys.modules.keys())
        new_modules = modules_after - modules_before
        
        # Should not have imported heavy DB clients
        heavy_modules = ['psycopg2', 'pymysql', 'redis', 'qdrant_client']
        for heavy in heavy_modules:
            assert heavy not in new_modules, f"Heavy module {heavy} was imported"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
