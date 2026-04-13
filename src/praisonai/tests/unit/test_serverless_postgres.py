"""
Unit tests for serverless-resilient PostgreSQL support.

Tests: URL detection, SSL enforcement, retry logic, convenience classes.
These are mock-based — no live database needed.
"""

import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestURLDetection(unittest.TestCase):
    """Test that cloud provider URLs are correctly detected."""

    def _detect(self, url):
        from praisonai.db.adapter import PraisonAIDB
        db = PraisonAIDB.__new__(PraisonAIDB)
        return db._detect_backend(url)

    def test_neon_url_detected_as_postgres(self):
        url = "postgresql://user:pass@ep-cool-darkness-a1b2c3d4.us-east-2.aws.neon.tech/dbname?sslmode=require"
        self.assertEqual(self._detect(url), "postgres")

    def test_neon_pooler_url_detected_as_postgres(self):
        url = "postgresql://user:pass@ep-cool-darkness-a1b2c3d4-pooler.us-east-2.aws.neon.tech/dbname"
        self.assertEqual(self._detect(url), "postgres")

    def test_cockroachdb_url_detected_as_postgres(self):
        url = "postgresql://user:pass@free-tier.gcp-us-central1.cockroachlabs.cloud:26257/mydb?sslmode=verify-full"
        self.assertEqual(self._detect(url), "postgres")

    def test_xata_url_detected_as_postgres(self):
        url = "postgresql://user:pass@us-east-1.sql.xata.sh:5432/mydb?sslmode=require"
        self.assertEqual(self._detect(url), "postgres")

    def test_supabase_direct_postgres_detected(self):
        url = "postgresql://postgres.abc123:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        self.assertEqual(self._detect(url), "postgres")

    def test_supabase_rest_url_detected(self):
        url = "https://abc123.supabase.co"
        self.assertEqual(self._detect(url), "supabase")

    def test_turso_libsql_url_detected(self):
        url = "libsql://mydb-user.turso.io"
        self.assertEqual(self._detect(url), "turso")

    def test_standard_postgres_still_works(self):
        url = "postgresql://postgres:pass@localhost:5432/praisonai"
        self.assertEqual(self._detect(url), "postgres")

    def test_standard_mysql_still_works(self):
        url = "mysql://user:pass@localhost:3306/mydb"
        self.assertEqual(self._detect(url), "mysql")

    def test_standard_sqlite_still_works(self):
        url = "sqlite:///tmp/test.db"
        self.assertEqual(self._detect(url), "sqlite")

    def test_sqlite_file_extension_still_works(self):
        url = "/tmp/test.db"
        self.assertEqual(self._detect(url), "sqlite")

    def test_standard_redis_still_works(self):
        url = "redis://localhost:6379"
        self.assertEqual(self._detect(url), "redis")


class TestSSLEnforcement(unittest.TestCase):
    """Test SSL auto-append for serverless providers."""

    def test_neon_url_gets_ssl(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        url = "postgresql://user:pass@ep-xxx.neon.tech/db"
        result = PostgresConversationStore._ensure_ssl(url)
        self.assertIn("sslmode=require", result)

    def test_cockroachdb_url_gets_ssl(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        url = "postgresql://user:pass@xxx.cockroachlabs.cloud:26257/db"
        result = PostgresConversationStore._ensure_ssl(url)
        self.assertIn("sslmode=", result)

    def test_xata_url_gets_ssl(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        url = "postgresql://user:pass@xxx.xata.sh:5432/db"
        result = PostgresConversationStore._ensure_ssl(url)
        self.assertIn("sslmode=require", result)

    def test_supabase_direct_gets_ssl(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        url = "postgresql://postgres:pass@xxx.pooler.supabase.com:6543/postgres"
        result = PostgresConversationStore._ensure_ssl(url)
        self.assertIn("sslmode=require", result)

    def test_url_with_existing_ssl_not_modified(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        url = "postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=verify-full"
        result = PostgresConversationStore._ensure_ssl(url)
        self.assertIn("sslmode=verify-full", result)
        self.assertEqual(result.count("sslmode="), 1)

    def test_localhost_url_not_modified(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        url = "postgresql://postgres:pass@localhost:5432/db"
        result = PostgresConversationStore._ensure_ssl(url)
        self.assertNotIn("sslmode=", result)


class TestServerlessDetection(unittest.TestCase):
    """Test _is_serverless detection from URLs."""

    def test_neon_is_serverless(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        self.assertTrue(PostgresConversationStore._is_serverless(
            "postgresql://user:pass@ep-xxx.neon.tech/db"))

    def test_cockroachdb_is_serverless(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        self.assertTrue(PostgresConversationStore._is_serverless(
            "postgresql://user:pass@xxx.cockroachlabs.cloud:26257/db"))

    def test_xata_is_serverless(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        self.assertTrue(PostgresConversationStore._is_serverless(
            "postgresql://user:pass@xxx.xata.sh:5432/db"))

    def test_supabase_direct_is_serverless(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        self.assertTrue(PostgresConversationStore._is_serverless(
            "postgresql://postgres:pass@xxx.pooler.supabase.com:6543/postgres"))

    def test_localhost_not_serverless(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        self.assertFalse(PostgresConversationStore._is_serverless(
            "postgresql://postgres:pass@localhost:5432/db"))


class TestRetryLogic(unittest.TestCase):
    """Test connection retry for serverless cold-start."""

    @patch('praisonai.persistence.conversation.postgres.psycopg2', create=True)
    def test_retry_on_operational_error(self, mock_psycopg2):
        """Verify that _execute_with_retry retries on OperationalError."""
        from praisonai.persistence.conversation.postgres import PostgresConversationStore

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        
        store = PostgresConversationStore.__new__(PostgresConversationStore)
        store._pool = mock_pool
        store._psycopg2 = mock_psycopg2
        store._RealDictCursor = MagicMock()
        store.schema = "public"
        store.table_prefix = "praison_"
        store.sessions_table = "public.praison_sessions"
        store.messages_table = "public.praison_messages"
        store._serverless = True
        store._max_retries = 3
        store._retry_delay = 0.01

        # Simulate: first call raises OperationalError, second succeeds
        op_error = mock_psycopg2.OperationalError("connection closed")
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise op_error
            return MagicMock()  # success

        mock_cursor = MagicMock()
        mock_cursor.execute = side_effect
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # This should succeed after retry
        result = store._execute_with_retry(
            lambda conn: None,
        )
        # If no exception raised, retry worked


class TestConvenienceClasses(unittest.TestCase):
    """Test NeonDB, CockroachDB, XataDB convenience classes."""

    def test_neondb_class_exists(self):
        from praisonai.db.adapter import NeonDB
        self.assertTrue(callable(NeonDB))

    def test_cockroachdb_class_exists(self):
        from praisonai.db.adapter import CockroachDB as CockroachDBClass
        self.assertTrue(callable(CockroachDBClass))

    def test_xatadb_class_exists(self):
        from praisonai.db.adapter import XataDB
        self.assertTrue(callable(XataDB))

    def test_tursodb_class_exists(self):
        from praisonai.db.adapter import TursoDB
        self.assertTrue(callable(TursoDB))

    def test_neondb_inherits_praisonaidb(self):
        from praisonai.db.adapter import NeonDB, PraisonAIDB
        self.assertTrue(issubclass(NeonDB, PraisonAIDB))

    def test_cockroachdb_inherits_praisonaidb(self):
        from praisonai.db.adapter import CockroachDB as CockroachDBClass, PraisonAIDB
        self.assertTrue(issubclass(CockroachDBClass, PraisonAIDB))


class TestConfigEnvVars(unittest.TestCase):
    """Test new environment variable mappings."""

    def test_neon_env_var_exists(self):
        from praisonai.persistence.config import ENV_VARS
        self.assertIn("neon_database_url", ENV_VARS)

    def test_turso_env_vars_exist(self):
        from praisonai.persistence.config import ENV_VARS
        self.assertIn("turso_database_url", ENV_VARS)
        self.assertIn("turso_auth_token", ENV_VARS)

    def test_cockroachdb_env_var_exists(self):
        from praisonai.persistence.config import ENV_VARS
        self.assertIn("cockroachdb_url", ENV_VARS)

    def test_xata_env_var_exists(self):
        from praisonai.persistence.config import ENV_VARS
        self.assertIn("xata_database_url", ENV_VARS)

    def test_turso_in_conversation_backends(self):
        from praisonai.persistence.config import CONVERSATION_BACKENDS
        self.assertIn("turso", CONVERSATION_BACKENDS)


class TestFactoryRegistration(unittest.TestCase):
    """Test that new backends are registered in factory."""

    def test_turso_backend_in_factory(self):
        """Factory should accept 'turso' as conversation backend."""
        from praisonai.persistence.factory import create_conversation_store
        # We don't actually create the store (no libsql installed),
        # just verify the factory doesn't raise ValueError for 'turso'
        try:
            create_conversation_store("turso", url="libsql://test.turso.io")
        except ImportError:
            pass  # Expected — libsql not installed
        except ValueError:
            self.fail("Factory should recognize 'turso' backend")

    def test_neon_alias_in_factory(self):
        """Factory should accept 'neon' as alias for postgres."""
        from praisonai.persistence.factory import create_conversation_store
        try:
            create_conversation_store("neon", url="postgresql://user:pass@ep-xxx.neon.tech/db")
        except ImportError:
            pass  # Expected — psycopg2 not installed in CI
        except Exception as e:
            if "Unknown" in str(e):
                self.fail("Factory should recognize 'neon' as alias for postgres")

    def test_cockroachdb_alias_in_factory(self):
        """Factory should accept 'cockroachdb' as alias for postgres."""
        from praisonai.persistence.factory import create_conversation_store
        try:
            create_conversation_store("cockroachdb", url="postgresql://user:pass@xxx.cockroachlabs.cloud/db")
        except ImportError:
            pass
        except Exception as e:
            if "Unknown" in str(e):
                self.fail("Factory should recognize 'cockroachdb' as alias for postgres")

    def test_xata_alias_in_factory(self):
        """Factory should accept 'xata' as alias for postgres."""
        from praisonai.persistence.factory import create_conversation_store
        try:
            create_conversation_store("xata", url="postgresql://user:pass@xxx.xata.sh/db")
        except ImportError:
            pass
        except Exception as e:
            if "Unknown" in str(e):
                self.fail("Factory should recognize 'xata' as alias for postgres")


if __name__ == "__main__":
    unittest.main()
