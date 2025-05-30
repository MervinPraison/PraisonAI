import os
import sqlite3
import asyncio
import shutil
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sql_alchemy import SQLAlchemyDataLayer
import chainlit.data as cl_data
from chainlit.types import ThreadDict
from database_config import get_database_url_with_sqlite_override

def ensure_directories():
    """Ensure required directories exist"""
    if "CHAINLIT_APP_ROOT" not in os.environ:
        chainlit_root = os.path.join(os.path.expanduser("~"), ".praison")
        os.environ["CHAINLIT_APP_ROOT"] = chainlit_root
    else:
        chainlit_root = os.environ["CHAINLIT_APP_ROOT"]

    os.makedirs(chainlit_root, exist_ok=True)
    os.makedirs(os.path.join(chainlit_root, ".files"), exist_ok=True)
    
    # Copy public folder and chainlit.md if they don't exist
    public_folder = os.path.join(os.path.dirname(__file__), "public")
    config_folder = os.path.join(os.path.dirname(__file__), "config")
    
    # Copy public folder
    if not os.path.exists(os.path.join(chainlit_root, "public")):
        if os.path.exists(public_folder):
            shutil.copytree(public_folder, os.path.join(chainlit_root, "public"), dirs_exist_ok=True)
            logging.info("Public folder copied successfully!")
        else:
            logging.info("Public folder not found in the package.")
    
    # Copy all files from config folder to root if translations doesn't exist
    if not os.path.exists(os.path.join(chainlit_root, "translations")):
        os.makedirs(os.path.join(chainlit_root, "translations"), exist_ok=True)
        
        if os.path.exists(config_folder):
            for item in os.listdir(config_folder):
                src_path = os.path.join(config_folder, item)
                dst_path = os.path.join(chainlit_root, item)
                if os.path.isfile(src_path):
                    shutil.copy2(src_path, dst_path)
                    logging.info(f"File {item} copied to root successfully!")
                elif os.path.isdir(src_path):
                    if os.path.exists(dst_path):
                        shutil.rmtree(dst_path)
                    shutil.copytree(src_path, dst_path)
                    logging.info(f"Directory {item} copied to root successfully!")
        else:
            logging.info("Config folder not found in the package.")

# Create directories at module import time
ensure_directories()

class DatabaseManager(SQLAlchemyDataLayer):
    def __init__(self):
        # Check FORCE_SQLITE flag to bypass external database detection
        self.database_url = get_database_url_with_sqlite_override()
        
        if self.database_url:
            self.conninfo = self.database_url
        else:
            chainlit_root = os.environ["CHAINLIT_APP_ROOT"]  # Now using CHAINLIT_APP_ROOT
            self.db_path = os.path.join(chainlit_root, "database.sqlite")
            self.conninfo = f"sqlite+aiosqlite:///{self.db_path}"
        
        # Initialize SQLAlchemyDataLayer with the connection info
        super().__init__(conninfo=self.conninfo)

    async def create_schema_async(self):
        """Create the database schema for PostgreSQL"""
        if not self.database_url:
            return
        engine = create_async_engine(self.database_url, echo=False)
        async with engine.begin() as conn:
            await conn.execute(text('''
                CREATE TABLE IF NOT EXISTS users (
                    "id" TEXT PRIMARY KEY,
                    "identifier" TEXT NOT NULL UNIQUE,
                    "meta" TEXT NOT NULL DEFAULT '{}',
                    "createdAt" TEXT
                );
            '''))
            await conn.execute(text('''
                CREATE TABLE IF NOT EXISTS threads (
                    "id" TEXT PRIMARY KEY,
                    "createdAt" TEXT,
                    "name" TEXT,
                    "userId" TEXT,
                    "userIdentifier" TEXT,
                    "tags" TEXT DEFAULT '[]',
                    "meta" TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
                );
            '''))
            await conn.execute(text('''
                CREATE TABLE IF NOT EXISTS steps (
                    "id" TEXT PRIMARY KEY,
                    "name" TEXT NOT NULL,
                    "type" TEXT NOT NULL,
                    "threadId" TEXT NOT NULL,
                    "parentId" TEXT,
                    "disableFeedback" BOOLEAN NOT NULL DEFAULT FALSE,
                    "streaming" BOOLEAN NOT NULL DEFAULT FALSE,
                    "waitForAnswer" BOOLEAN DEFAULT FALSE,
                    "isError" BOOLEAN NOT NULL DEFAULT FALSE,
                    "meta" TEXT DEFAULT '{}',
                    "tags" TEXT DEFAULT '[]',
                    "input" TEXT,
                    "output" TEXT,
                    "createdAt" TEXT,
                    "startTime" TEXT,
                    "endTime" TEXT,
                    "generation" TEXT,
                    "showInput" TEXT,
                    "language" TEXT,
                    "indent" INT,
                    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
                );
            '''))
            await conn.execute(text('''
                CREATE TABLE IF NOT EXISTS elements (
                    "id" TEXT PRIMARY KEY,
                    "threadId" TEXT,
                    "type" TEXT,
                    "url" TEXT,
                    "chainlitKey" TEXT,
                    "name" TEXT NOT NULL,
                    "display" TEXT,
                    "objectKey" TEXT,
                    "size" TEXT,
                    "page" INT,
                    "language" TEXT,
                    "forId" TEXT,
                    "mime" TEXT,
                    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
                );
            '''))
            await conn.execute(text('''
                CREATE TABLE IF NOT EXISTS feedbacks (
                    "id" TEXT PRIMARY KEY,
                    "forId" TEXT NOT NULL,
                    "value" INT NOT NULL,
                    "threadId" TEXT,
                    "comment" TEXT
                );
            '''))
            await conn.execute(text('''
                CREATE TABLE IF NOT EXISTS settings (
                    "id" SERIAL PRIMARY KEY,
                    "key" TEXT UNIQUE,
                    "value" TEXT
                );
            '''))
        await engine.dispose()

    def create_schema_sqlite(self):
        """Create the database schema for SQLite"""
        chainlit_root = os.environ["CHAINLIT_APP_ROOT"]  # Now using CHAINLIT_APP_ROOT
        self.db_path = os.path.join(chainlit_root, "database.sqlite")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                identifier TEXT NOT NULL UNIQUE,
                meta TEXT NOT NULL DEFAULT '{}',
                createdAt TEXT
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                createdAt TEXT,
                name TEXT,
                userId TEXT,
                userIdentifier TEXT,
                tags TEXT DEFAULT '[]',
                meta TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS steps (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                threadId TEXT NOT NULL,
                parentId TEXT,
                disableFeedback BOOLEAN NOT NULL DEFAULT 0,
                streaming BOOLEAN NOT NULL DEFAULT 0,
                waitForAnswer BOOLEAN DEFAULT 0,
                isError BOOLEAN NOT NULL DEFAULT 0,
                meta TEXT DEFAULT '{}',
                tags TEXT DEFAULT '[]',
                input TEXT,
                output TEXT,
                createdAt TEXT,
                startTime TEXT,
                endTime TEXT,
                generation TEXT,
                showInput TEXT,
                language TEXT,
                indent INT,
                FOREIGN KEY (threadId) REFERENCES threads(id) ON DELETE CASCADE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS elements (
                id TEXT PRIMARY KEY,
                threadId TEXT,
                type TEXT,
                url TEXT,
                chainlitKey TEXT,
                name TEXT NOT NULL,
                display TEXT,
                objectKey TEXT,
                size TEXT,
                page INT,
                language TEXT,
                forId TEXT,
                mime TEXT,
                FOREIGN KEY (threadId) REFERENCES threads(id) ON DELETE CASCADE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedbacks (
                id TEXT PRIMARY KEY,
                forId TEXT NOT NULL,
                value INT NOT NULL,
                threadId TEXT,
                comment TEXT
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT
            );
        ''')
        conn.commit()
        conn.close()

    def initialize(self):
        """Initialize the database with schema based on the configuration"""
        if self.database_url:
            asyncio.run(self.create_schema_async())
        else:
            self.create_schema_sqlite()

    async def save_setting(self, key: str, value: str):
        """Save a setting to the database"""
        if self.database_url:
            async with self.engine.begin() as conn:
                await conn.execute(text("""
                    INSERT INTO settings ("key", "value") VALUES (:key, :value)
                    ON CONFLICT ("key") DO UPDATE SET "value" = EXCLUDED."value"
                """), {"key": key, "value": value})
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO settings (id, key, value)
                VALUES ((SELECT id FROM settings WHERE key = ?), ?, ?)
                """,
                (key, key, value),
            )
            conn.commit()
            conn.close()

    async def load_setting(self, key: str) -> str:
        """Load a setting from the database"""
        if self.database_url:
            async with self.engine.connect() as conn:
                result = await conn.execute(text('SELECT "value" FROM settings WHERE "key" = :key'), {"key": key})
                row = result.fetchone()
                return row[0] if row else None
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
