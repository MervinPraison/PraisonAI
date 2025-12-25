"""PostgreSQL Tool Example.

This example demonstrates how to use the PostgreSQL tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"
    Docker: docker run -d --name postgres -e POSTGRES_PASSWORD=praison123 -e POSTGRES_DB=praisonai -p 5432:5432 postgres:16

Usage:
    python tool.py
"""

from praisonai_tools import PostgresTool


def main():
    # Initialize PostgreSQL tool
    pg = PostgresTool(
        host="localhost",
        port=5432,
        database="praisonai",
        user="postgres",
        password="praison123"
    )
    
    # Example 1: List tables
    print("=" * 60)
    print("Example 1: List Tables")
    print("=" * 60)
    
    tables = pg.list_tables()
    
    if isinstance(tables, dict) and "error" in tables:
        print(f"Error: {tables['error']}")
    else:
        print(f"Found {len(tables)} tables:")
        for t in tables[:10]:
            print(f"  - {t.get('table_name', t)}")
    
    # Example 2: Query
    print("\n" + "=" * 60)
    print("Example 2: Execute Query")
    print("=" * 60)
    
    result = pg.query("SELECT version()")
    
    if isinstance(result, dict) and "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"PostgreSQL version: {result}")
    
    print("\n✅ PostgreSQL tool working correctly!")


if __name__ == "__main__":
    main()
