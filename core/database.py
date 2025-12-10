import os
import logging
import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("core.database")

class Database:
    _pool = None

    @classmethod
    async def connect(cls):
        if cls._pool is None:
            try:
                cls._pool = await asyncpg.create_pool(
                    user=os.getenv("DB_USER"),
                    password=os.getenv("DB_PASSWORD"),
                    database=os.getenv("DB_NAME"),
                    host=os.getenv("DB_HOST"),
                    port=os.getenv("DB_PORT")
                )
                logger.info("Connected to PostgreSQL.")
                await cls.init_schema()
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
                raise

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()
            logger.info("Database connection closed.")

    @classmethod
    async def get_pool(cls):
        if cls._pool is None:
            await cls.connect()
        return cls._pool

    @classmethod
    async def init_schema(cls):
        """Initializes the database schema if it doesn't exist."""
        queries = [
            # Enable pgvector extension
            "CREATE EXTENSION IF NOT EXISTS vector;",
            
            # Config table
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """,
            
            # Pinya Docs (RAG knowledge base)
            """
            CREATE TABLE IF NOT EXISTS pinya_docs (
                id SERIAL PRIMARY KEY,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector(1536),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            
            # Aliases table
            """
            CREATE TABLE IF NOT EXISTS aliases (
                trigger TEXT PRIMARY KEY,
                replacement TEXT NOT NULL
            );
            """
        ]

        async with cls._pool.acquire() as conn:
            async with conn.transaction():
                for query in queries:
                    await conn.execute(query)
        logger.info("Database schema initialized.")

    @classmethod
    async def fetchval(cls, query, *args):
        pool = await cls.get_pool()
        return await pool.fetchval(query, *args)

    @classmethod
    async def fetchrow(cls, query, *args):
        pool = await cls.get_pool()
        return await pool.fetchrow(query, *args)

    @classmethod
    async def fetch(cls, query, *args):
        pool = await cls.get_pool()
        return await pool.fetch(query, *args)

    @classmethod
    async def execute(cls, query, *args):
        pool = await cls.get_pool()
        return await pool.execute(query, *args)
