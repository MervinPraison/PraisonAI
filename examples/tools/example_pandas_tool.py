"""
Example: Using pandas as a custom tool with PraisonAI Agent

This example shows how to wrap pandas functions as tools
that can be used with Agent().
"""

import pandas as pd
from io import StringIO

# Define pandas wrapper tools
def analyze_csv_data(csv_data: str) -> str:
    """Analyze CSV data using pandas DataFrame.
    
    Args:
        csv_data: CSV-formatted string data
        
    Returns:
        Analysis summary including shape, columns, and statistics
    """
    df = pd.read_csv(StringIO(csv_data))
    summary = f"""DataFrame Analysis:
- Shape: {df.shape[0]} rows, {df.shape[1]} columns
- Columns: {list(df.columns)}
- Data Types: {dict(df.dtypes)}
- Summary Statistics:
{df.describe().to_string()}"""
    return summary


def filter_dataframe(csv_data: str, column: str, condition: str, value: str) -> str:
    """Filter a DataFrame based on a condition.
    
    Args:
        csv_data: CSV-formatted string data
        column: Column name to filter on
        condition: Condition type ('equals', 'greater', 'less', 'contains')
        value: Value to compare against
        
    Returns:
        Filtered data as CSV string
    """
    df = pd.read_csv(StringIO(csv_data))
    
    if condition == 'equals':
        filtered = df[df[column] == value]
    elif condition == 'greater':
        filtered = df[df[column] > float(value)]
    elif condition == 'less':
        filtered = df[df[column] < float(value)]
    elif condition == 'contains':
        filtered = df[df[column].str.contains(value, na=False)]
    else:
        return f"Unknown condition: {condition}"
    
    return filtered.to_csv(index=False)


def calculate_statistics(csv_data: str, column: str) -> str:
    """Calculate statistics for a specific column.
    
    Args:
        csv_data: CSV-formatted string data
        column: Column name to analyze
        
    Returns:
        Statistics summary for the column
    """
    df = pd.read_csv(StringIO(csv_data))
    
    if column not in df.columns:
        return f"Column '{column}' not found. Available: {list(df.columns)}"
    
    col = df[column]
    
    if pd.api.types.is_numeric_dtype(col):
        stats = f"""Statistics for '{column}':
- Count: {col.count()}
- Mean: {col.mean():.2f}
- Std: {col.std():.2f}
- Min: {col.min()}
- Max: {col.max()}
- Median: {col.median()}"""
    else:
        stats = f"""Statistics for '{column}':
- Count: {col.count()}
- Unique: {col.nunique()}
- Top: {col.mode().iloc[0] if len(col.mode()) > 0 else 'N/A'}
- Sample values: {list(col.head(3))}"""
    
    return stats


if __name__ == "__main__":
    # Test data
    test_csv = """name,age,salary,department
Alice,30,50000,Engineering
Bob,25,45000,Marketing
Charlie,35,60000,Engineering
Diana,28,52000,Sales
Eve,32,55000,Marketing"""

    print("=== Test: analyze_csv_data ===")
    print(analyze_csv_data(test_csv))
    print()
    
    print("=== Test: filter_dataframe ===")
    print(filter_dataframe(test_csv, "age", "greater", "28"))
    print()
    
    print("=== Test: calculate_statistics ===")
    print(calculate_statistics(test_csv, "salary"))
    print()
    
    # Example with Agent (requires praisonaiagents)
    print("=== Agent Usage Example ===")
    print("""
from praisonaiagents import Agent

agent = Agent(
    name="data_analyst",
    role="Data Analyst",
    goal="Analyze data using pandas tools",
    tools=[analyze_csv_data, filter_dataframe, calculate_statistics]
)

result = agent.start("Analyze this data and find the average salary")
""")
