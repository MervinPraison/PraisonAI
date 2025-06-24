"""Pandas tools for data manipulation and analysis.

Usage:
from praisonaiagents.tools import pandas_tools
df = pandas_tools.read_csv("data.csv")
df = pandas_tools.filter_data(df, "column > 5")
summary = pandas_tools.get_summary(df)

or
from praisonaiagents.tools import read_csv, filter_data, get_summary
df = read_csv("data.csv")
"""

import logging
from typing import List, Dict, Union, Optional, Any
from importlib import util
import json
import os

# Import pandas for type hints, but don't use it until we check it's installed
if util.find_spec("pandas") is not None:
    import pandas as pd
    import numpy as np
else:
    # Create a placeholder for type hints
    class pd:
        DataFrame = None

def _convert_to_serializable(obj: Any) -> Any:
    """Convert numpy/pandas types to JSON serializable Python types."""
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Series):
        return obj.to_list()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    return obj

class PandasTools:
    """Tools for data manipulation and analysis using pandas."""
    
    def __init__(self):
        """Initialize PandasTools and check for pandas installation."""
        self._check_pandas()
        
    def _check_pandas(self):
        """Check if pandas is installed."""
        if util.find_spec("pandas") is None:
            raise ImportError("pandas is not available. Please install it using: pip install pandas")
        global pd, np
        import pandas as pd
        import numpy as np

    def read_csv(self, filepath: str, **kwargs) -> Union[pd.DataFrame, Dict[str, str]]:
        """
        Read a CSV file into a pandas DataFrame.
        
        Args:
            filepath: Path to the CSV file
            **kwargs: Additional arguments to pass to pd.read_csv()
            
        Returns:
            pd.DataFrame or Dict: DataFrame if successful, error dict if failed
        """
        try:
            return pd.read_csv(filepath, **kwargs)
        except Exception as e:
            error_msg = f"Error reading CSV file {filepath}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def read_excel(self, filepath: str, **kwargs) -> Union[pd.DataFrame, Dict[str, str]]:
        """
        Read an Excel file into a pandas DataFrame.
        
        Args:
            filepath: Path to the Excel file
            **kwargs: Additional arguments to pass to pd.read_excel()
            
        Returns:
            pd.DataFrame or Dict: DataFrame if successful, error dict if failed
        """
        try:
            return pd.read_excel(filepath, **kwargs)
        except Exception as e:
            error_msg = f"Error reading Excel file {filepath}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def write_csv(self, df: pd.DataFrame, filepath: str, **kwargs) -> bool:
        """
        Write DataFrame to a CSV file.
        
        Args:
            df: DataFrame to write
            filepath: Output file path
            **kwargs: Additional arguments to pass to df.to_csv()
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            df.to_csv(filepath, **kwargs)
            return True
        except Exception as e:
            error_msg = f"Error writing CSV file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def write_excel(self, df: pd.DataFrame, filepath: str, **kwargs) -> bool:
        """
        Write DataFrame to an Excel file.
        
        Args:
            df: DataFrame to write
            filepath: Output file path
            **kwargs: Additional arguments to pass to df.to_excel()
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            df.to_excel(filepath, **kwargs)
            return True
        except Exception as e:
            error_msg = f"Error writing Excel file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def filter_data(self, df: pd.DataFrame, query: str) -> Union[pd.DataFrame, Dict[str, str]]:
        """
        Filter DataFrame using a query string.
        
        Args:
            df: Input DataFrame
            query: Query string (e.g., "column > 5 and other_column == 'value'")
            
        Returns:
            pd.DataFrame or Dict: Filtered DataFrame if successful, error dict if failed
        """
        try:
            return df.query(query)
        except Exception as e:
            error_msg = f"Error filtering data with query '{query}': {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get a summary of the DataFrame including basic statistics and info.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Dict: Summary statistics and information
        """
        try:
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")
                
            numeric_summary = df.describe().to_dict()
            # Convert numpy types to native Python types
            for col in numeric_summary:
                numeric_summary[col] = {k: _convert_to_serializable(v) 
                                     for k, v in numeric_summary[col].items()}
            
            summary = {
                "shape": list(df.shape),
                "columns": list(df.columns),
                "dtypes": df.dtypes.astype(str).to_dict(),
                "null_counts": df.isnull().sum().to_dict(),
                "numeric_summary": numeric_summary,
                "memory_usage": int(df.memory_usage(deep=True).sum()),
            }
            return summary
        except Exception as e:
            error_msg = f"Error getting data summary: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def group_by(
        self, 
        df: pd.DataFrame, 
        columns: Union[str, List[str]], 
        agg_dict: Dict[str, Union[str, List[str]]]
    ) -> Union[pd.DataFrame, Dict[str, str]]:
        """
        Group DataFrame by columns and apply aggregation functions.
        
        Args:
            df: Input DataFrame
            columns: Column(s) to group by
            agg_dict: Dictionary of column:function pairs for aggregation
            
        Returns:
            pd.DataFrame or Dict: Grouped DataFrame if successful, error dict if failed
        """
        try:
            return df.groupby(columns).agg(agg_dict).reset_index()
        except Exception as e:
            error_msg = f"Error grouping data: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def pivot_table(
        self, 
        df: pd.DataFrame, 
        index: Union[str, List[str]], 
        columns: Optional[Union[str, List[str]]] = None,
        values: Optional[Union[str, List[str]]] = None,
        aggfunc: str = "mean"
    ) -> Union[pd.DataFrame, Dict[str, str]]:
        """
        Create a pivot table from DataFrame.
        
        Args:
            df: Input DataFrame
            index: Column(s) to use as index
            columns: Column(s) to use as columns
            values: Column(s) to aggregate
            aggfunc: Aggregation function to use
            
        Returns:
            pd.DataFrame or Dict: Pivot table if successful, error dict if failed
        """
        try:
            return pd.pivot_table(
                df,
                index=index,
                columns=columns,
                values=values,
                aggfunc=aggfunc
            ).reset_index()
        except Exception as e:
            error_msg = f"Error creating pivot table: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

# Create instance for direct function access
_pandas_tools = PandasTools()
read_csv = _pandas_tools.read_csv
read_excel = _pandas_tools.read_excel
write_csv = _pandas_tools.write_csv
write_excel = _pandas_tools.write_excel
filter_data = _pandas_tools.filter_data
get_summary = _pandas_tools.get_summary
group_by = _pandas_tools.group_by
pivot_table = _pandas_tools.pivot_table

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("PandasTools Demonstration")
    print("==================================================\n")

    # Create a test directory
    test_dir = os.path.join(os.getcwd(), "test_files")
    os.makedirs(test_dir, exist_ok=True)
    
    # Create a sample DataFrame
    df = pd.DataFrame({
        'name': ['John', 'Jane', 'Bob', 'Alice', 'Charlie'],
        'age': [25, 30, 35, 28, 32],
        'city': ['New York', 'London', 'Paris', 'Tokyo', 'London'],
        'salary': [50000, 60000, 75000, 65000, 55000]
    })
    
    # 1. Write to CSV
    print("1. Writing to CSV")
    print("------------------------------")
    csv_file = os.path.join(test_dir, "sample.csv")
    success = write_csv(df, csv_file, index=False)
    print(f"Write successful: {success}\n")
    
    # 2. Read from CSV
    print("2. Reading from CSV")
    print("------------------------------")
    df_read = read_csv(csv_file)
    print("First few rows:")
    print(df_read.head())
    print()
    
    # 3. Filter Data
    print("3. Filtering Data")
    print("------------------------------")
    filtered_df = filter_data(df, "age > 30 and salary > 60000")
    print("People over 30 with salary > 60000:")
    print(filtered_df)
    print()
    
    # 4. Get Summary
    print("4. Data Summary")
    print("------------------------------")
    summary = get_summary(df)
    print(json.dumps(summary, indent=2))
    print()
    
    # 5. Group By
    print("5. Group By")
    print("------------------------------")
    grouped = group_by(df, "city", {"salary": ["mean", "count"], "age": "mean"})
    print("Statistics by city:")
    print(grouped)
    print()
    
    # 6. Pivot Table
    print("6. Pivot Table")
    print("------------------------------")
    pivoted = pivot_table(df, index="city", values=["salary", "age"])
    print("Pivot table by city:")
    print(pivoted)
    print()
    
    # Clean up test directory
    try:
        import shutil
        shutil.rmtree(test_dir)
        print("Test directory cleaned up successfully")
    except Exception as e:
        print(f"Error cleaning up test directory: {str(e)}")
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
