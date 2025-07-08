"""Tools for working with DuckDB databases.

Usage:
from praisonaiagents.tools import duckdb_tools
df = duckdb_tools.query("SELECT * FROM my_table")

or
from praisonaiagents.tools import query_db, create_table, load_data
df = query_db("SELECT * FROM my_table")
"""

import logging
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
from importlib import util
import json
import re

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

class DuckDBTools:
    """Tools for working with DuckDB databases."""
    
    def __init__(self, database: str = ':memory:'):
        """Initialize DuckDBTools.
        
        Args:
            database: Path to database file or ':memory:' for in-memory database
        """
        self.database = database
        self._conn = None
    
    def _validate_identifier(self, identifier: str) -> str:
        """Validate and quote a SQL identifier to prevent injection.
        
        Args:
            identifier: Table or column name to validate
            
        Returns:
            Quoted identifier safe for SQL
            
        Raises:
            ValueError: If identifier contains invalid characters
        """
        # Only allow alphanumeric characters, underscores, and dots
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$', identifier):
            raise ValueError(f"Invalid identifier: {identifier}")
        
        # Quote the identifier to handle reserved words
        return f'"{identifier}"'

    def _get_duckdb(self) -> Optional['duckdb']:
        """Get duckdb module, installing if needed"""
        if util.find_spec('duckdb') is None:
            error_msg = "duckdb package is not available. Please install it using: pip install duckdb"
            logging.error(error_msg)
            return None
        import duckdb
        return duckdb

    def _get_pandas(self) -> Optional['pd']:
        """Get pandas module, installing if needed"""
        if util.find_spec('pandas') is None:
            error_msg = "pandas package is not available. Please install it using: pip install pandas"
            logging.error(error_msg)
            return None
        import pandas as pd
        return pd

    def _get_connection(self) -> Optional['duckdb.DuckDBPyConnection']:
        """Get or create database connection"""
        if self._conn is None:
            duckdb = self._get_duckdb()
            if duckdb is None:
                return None
            try:
                self._conn = duckdb.connect(self.database)
            except Exception as e:
                error_msg = f"Error connecting to database {self.database}: {str(e)}"
                logging.error(error_msg)
                return None
        return self._conn

    def execute_query(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        return_df: bool = True
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """Execute a SQL query.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            return_df: If True, return results as DataFrame records
            
        Returns:
            Query results as list of dicts, or error dict
        """
        try:
            conn = self._get_connection()
            if conn is None:
                return {"error": "Could not connect to database"}

            if params:
                result = conn.execute(query, params)
            else:
                result = conn.execute(query)

            if return_df:
                pd = self._get_pandas()
                if pd is None:
                    return {"error": "pandas package not available"}
                df = result.df()
                return df.to_dict('records')
            else:
                return [dict(row) for row in result.fetchall()]

        except Exception as e:
            error_msg = f"Error executing query: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def load_csv(
        self,
        table_name: str,
        filepath: str,
        schema: Optional[Dict[str, str]] = None,
        if_exists: str = 'replace'
    ) -> bool:
        """Load a CSV file into a table.
        
        Args:
            table_name: Name of table to create
            filepath: Path to CSV file
            schema: Optional column definitions
            if_exists: What to do if table exists ('fail', 'replace', 'append')
            
        Returns:
            bool: Success status
        """
        try:
            conn = self._get_connection()
            if conn is None:
                return False

            # Check if table exists using parameterized query
            exists = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, [table_name]).fetchone() is not None

            if exists:
                if if_exists == 'fail':
                    raise ValueError(f"Table {table_name} already exists")
                elif if_exists == 'replace':
                    # Validate and quote table name to prevent injection
                    safe_table = self._validate_identifier(table_name)
                    conn.execute(f"DROP TABLE IF EXISTS {safe_table}")
                elif if_exists != 'append':
                    raise ValueError("if_exists must be 'fail', 'replace', or 'append'")

            # Create table if needed
            if not exists or if_exists == 'replace':
                safe_table = self._validate_identifier(table_name)
                if schema:
                    # Create table with schema - validate column names
                    column_defs = []
                    for col_name, col_type in schema.items():
                        safe_col = self._validate_identifier(col_name)
                        # Validate column type to prevent injection
                        if not re.match(r'^[A-Z][A-Z0-9_]*(\([0-9,]+\))?$', col_type.upper()):
                            raise ValueError(f"Invalid column type: {col_type}")
                        column_defs.append(f"{safe_col} {col_type}")
                    columns = ', '.join(column_defs)
                    conn.execute(f"CREATE TABLE {safe_table} ({columns})")
                else:
                    # Infer schema from CSV - use parameterized query for filepath
                    conn.execute(f"""
                        CREATE TABLE {safe_table} AS 
                        SELECT * FROM read_csv_auto(?)
                        WHERE 1=0
                    """, [filepath])

            # Load data - use validated table name and parameterized filepath
            safe_table = self._validate_identifier(table_name)
            conn.execute(f"""
                INSERT INTO {safe_table}
                SELECT * FROM read_csv_auto(?)
            """, [filepath])

            return True

        except Exception as e:
            error_msg = f"Error loading CSV file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def export_csv(
        self,
        query: str,
        filepath: str,
        params: Optional[Union[tuple, dict]] = None
    ) -> bool:
        """Export query results to CSV.
        
        Args:
            query: SQL query to execute
            filepath: Output file path
            params: Optional query parameters
            
        Returns:
            bool: Success status
        """
        try:
            # Execute query and get results as DataFrame
            results = self.execute_query(query, params)
            if isinstance(results, dict) and 'error' in results:
                return False

            pd = self._get_pandas()
            if pd is None:
                return False

            # Convert to DataFrame and save
            df = pd.DataFrame(results)
            df.to_csv(filepath, index=False)
            return True

        except Exception as e:
            error_msg = f"Error exporting to CSV file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

# Create instance for direct function access
_duckdb_tools = DuckDBTools()
execute_query = _duckdb_tools.execute_query
load_csv = _duckdb_tools.load_csv
export_csv = _duckdb_tools.export_csv

if __name__ == "__main__":
    print("\n==================================================")
    print("DuckDBTools Demonstration")
    print("==================================================\n")
    
    # Create a temporary file for testing
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp:
        temp_file = temp.name
        
        # Create sample data
        with open(temp_file, 'w') as f:
            f.write("name,age,city\n")
            f.write("Alice,25,New York\n")
            f.write("Bob,30,San Francisco\n")
            f.write("Charlie,35,Chicago\n")
        
        print("1. Loading CSV File")
        print("------------------------------")
        result = load_csv('users', temp_file)
        print(f"CSV loaded successfully: {result}")
        print()
        
        print("2. Executing Query")
        print("------------------------------")
        query = "SELECT * FROM users WHERE age > 25"
        results = execute_query(query)
        print("Query results:")
        for row in results:
            print(row)
        print()
        
        print("3. Exporting Query Results")
        print("------------------------------")
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp2:
            temp_file2 = temp2.name
            result = export_csv(query, temp_file2)
            print(f"Results exported successfully: {result}")
            if result:
                print("\nExported file contents:")
                with open(temp_file2) as f:
                    print(f.read())
        
        # Clean up temporary files
        os.unlink(temp_file)
        os.unlink(temp_file2)
    
    print("==================================================")
    print("Demonstration Complete")
    print("==================================================\n")
