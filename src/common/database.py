"""
PostgreSQL database client for structured data storage.
"""
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from .config import get_config
from .logging import get_logger
from .metrics import metrics

logger = get_logger(__name__)


class Database:
    """PostgreSQL database client with connection pooling."""
    
    def __init__(self, min_conn: int = 1, max_conn: int = 10):
        """
        Initialize database connection pool.
        
        Args:
            min_conn: Minimum number of connections
            max_conn: Maximum number of connections
        """
        config = get_config()
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                min_conn,
                max_conn,
                host=config.postgres_host,
                port=config.postgres_port,
                user=config.postgres_user,
                password=config.postgres_password,
                database=config.postgres_db
            )
            logger.info(f"Database pool initialized: {config.postgres_host}:{config.postgres_port}/{config.postgres_db}")
        except psycopg2.Error as e:
            logger.error(f"Failed to initialize database pool: {e}")
            metrics.record_error("db_error", "init")
            raise
    
    @contextmanager
    def get_connection(self):
        """
        Get a database connection from the pool.
        
        Yields:
            Database connection
        """
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except psycopg2.Error as e:
            logger.error(f"Database connection error: {e}")
            metrics.record_error("db_error", "connection")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, commit: bool = True):
        """
        Get a database cursor with automatic commit/rollback.
        
        Args:
            commit: Whether to commit on success
        
        Yields:
            Database cursor
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                if commit:
                    conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Database cursor error: {e}")
                metrics.record_error("db_error", "cursor")
                raise
            finally:
                cursor.close()
    
    def execute(self, query: str, params: tuple = None, commit: bool = True) -> bool:
        """
        Execute a query without returning results.
        
        Args:
            query: SQL query
            params: Query parameters
            commit: Whether to commit
        
        Returns:
            True if successful
        """
        try:
            with self.get_cursor(commit=commit) as cursor:
                cursor.execute(query, params)
            return True
        except psycopg2.Error as e:
            logger.error(f"Failed to execute query: {e}")
            metrics.record_error("db_error", "execute")
            return False
    
    def fetch_one(self, query: str, params: tuple = None) -> Optional[tuple]:
        """
        Fetch a single row from query results.
        
        Args:
            query: SQL query
            params: Query parameters
        
        Returns:
            Single row or None
        """
        try:
            with self.get_cursor(commit=False) as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Failed to fetch one: {e}")
            metrics.record_error("db_error", "fetch_one")
            return None
    
    def fetch_all(self, query: str, params: tuple = None) -> List[tuple]:
        """
        Fetch all rows from query results.
        
        Args:
            query: SQL query
            params: Query parameters
        
        Returns:
            List of rows
        """
        try:
            with self.get_cursor(commit=False) as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Failed to fetch all: {e}")
            metrics.record_error("db_error", "fetch_all")
            return []
    
    def fetch_dict(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """
        Fetch all rows as dictionaries.
        
        Args:
            query: SQL query
            params: Query parameters
        
        Returns:
            List of row dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(query, params)
                results = cursor.fetchall()
                cursor.close()
                return [dict(row) for row in results]
        except psycopg2.Error as e:
            logger.error(f"Failed to fetch dict: {e}")
            metrics.record_error("db_error", "fetch_dict")
            return []
    
    def insert(self, table: str, data: Dict[str, Any]) -> Optional[int]:
        """
        Insert a row and return the ID.
        
        Args:
            table: Table name
            data: Column-value dictionary
        
        Returns:
            Inserted row ID or None
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, tuple(data.values()))
                result = cursor.fetchone()
                return result[0] if result else None
        except psycopg2.Error as e:
            logger.error(f"Failed to insert into {table}: {e}")
            metrics.record_error("db_error", "insert")
            return None
    
    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple = None) -> bool:
        """
        Update rows in a table.
        
        Args:
            table: Table name
            data: Column-value dictionary
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause
        
        Returns:
            True if successful
        """
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        params = tuple(data.values()) + (where_params or tuple())
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
            return True
        except psycopg2.Error as e:
            logger.error(f"Failed to update {table}: {e}")
            metrics.record_error("db_error", "update")
            return False
    
    def delete(self, table: str, where: str, where_params: tuple = None) -> bool:
        """
        Delete rows from a table.
        
        Args:
            table: Table name
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause
        
        Returns:
            True if successful
        """
        query = f"DELETE FROM {table} WHERE {where}"
        
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, where_params)
            return True
        except psycopg2.Error as e:
            logger.error(f"Failed to delete from {table}: {e}")
            metrics.record_error("db_error", "delete")
            return False
    
    def close(self):
        """Close all connections in the pool."""
        if self.pool:
            self.pool.closeall()
            logger.info("Database pool closed")


# Global database instance
_db: Optional[Database] = None


def get_db() -> Database:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
