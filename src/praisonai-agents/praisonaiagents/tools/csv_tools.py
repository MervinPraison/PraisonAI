"""Tools for working with CSV files.

Usage:
from praisonaiagents.tools import csv_tools
df = csv_tools.read_csv("data.csv")

or
from praisonaiagents.tools import read_csv, write_csv, merge_csv
df = read_csv("data.csv")
"""

import logging
from typing import List, Dict, Union, Optional, Any, TYPE_CHECKING
from importlib import util
import json
import csv
from pathlib import Path

if TYPE_CHECKING:
    import pandas as pd

class CSVTools:
    """Tools for working with CSV files."""
    
    def __init__(self):
        """Initialize CSVTools."""
        pass

    def _get_pandas(self) -> Optional['pd']:
        """Get pandas module, installing if needed"""
        if util.find_spec('pandas') is None:
            error_msg = "pandas package is not available. Please install it using: pip install pandas"
            logging.error(error_msg)
            return None
        import pandas as pd
        return pd

    def read_csv(
        self,
        filepath: str,
        encoding: str = 'utf-8',
        delimiter: str = ',',
        header: Union[int, List[int], None] = 0,
        usecols: Optional[List[str]] = None,
        dtype: Optional[Dict[str, str]] = None,
        parse_dates: Optional[List[str]] = None,
        na_values: Optional[List[str]] = None,
        nrows: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Read a CSV file with advanced options.
        
        Args:
            filepath: Path to CSV file
            encoding: File encoding
            delimiter: Column delimiter
            header: Row number(s) to use as column names
            usecols: Columns to read
            dtype: Dict of column dtypes
            parse_dates: List of columns to parse as dates
            na_values: Additional strings to recognize as NA/NaN
            nrows: Number of rows to read
            
        Returns:
            List of row dicts
        """
        try:
            pd = self._get_pandas()
            if pd is None:
                return {"error": "pandas package not available"}

            df = pd.read_csv(
                filepath,
                encoding=encoding,
                delimiter=delimiter,
                header=header,
                usecols=usecols,
                dtype=dtype,
                parse_dates=parse_dates,
                na_values=na_values,
                nrows=nrows
            )
            return df.to_dict('records')
            
        except Exception as e:
            error_msg = f"Error reading CSV file {filepath}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def write_csv(
        self,
        filepath: str,
        data: Union[List[Dict[str, Any]], str],
        encoding: str = 'utf-8',
        delimiter: str = ',',
        index: bool = False,
        header: bool = True,
        float_format: Optional[str] = None,
        date_format: Optional[str] = None,
        mode: str = 'w'
    ) -> bool:
        """Write data to a CSV file.
        
        Args:
            filepath: Path to CSV file
            data: Either a list of dictionaries or a string containing CSV data
                  If string, each line should be comma-separated values
            encoding: File encoding (default: 'utf-8')
            delimiter: Column delimiter (default: ',')
            index: Whether to write row indices (default: False)
            header: Whether to write column headers (default: True)
            float_format: Format string for float values (default: None)
            date_format: Format string for date values (default: None)
            mode: Write mode - 'w' for write, 'a' for append (default: 'w')
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            pd = self._get_pandas()
            if pd is None:
                return False

            # Handle string input
            if isinstance(data, str):
                # Convert string to list of dicts
                rows = []
                if delimiter in data:
                    # Get existing columns if file exists and in append mode
                    existing_cols = []
                    if mode == 'a' and Path(filepath).exists():
                        try:
                            existing_df = pd.read_csv(filepath, nrows=1)
                            existing_cols = existing_df.columns.tolist()
                        except:
                            pass

                    values = [v.strip() for v in data.split(delimiter)]
                    
                    if existing_cols:
                        # Use existing column names
                        row_dict = dict(zip(existing_cols, values))
                    else:
                        # Create generic column names
                        row_dict = {f'col{i}': val for i, val in enumerate(values)}
                    
                    rows.append(row_dict)
                    data = rows

                df = pd.DataFrame(data)
                
                # Handle append mode properly
                write_header = header if mode == 'w' else (header and not Path(filepath).exists())
                
                df.to_csv(
                    filepath,
                    encoding=encoding,
                    sep=delimiter,
                    index=index,
                    header=write_header,
                    float_format=float_format,
                    date_format=date_format,
                    mode=mode
                )
                return True
            
        except Exception as e:
            error_msg = f"Error writing CSV file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def merge_csv(
        self,
        files: List[str],
        output_file: str,
        how: str = 'inner',
        on: Optional[Union[str, List[str]]] = None,
        suffixes: Optional[tuple] = None
    ) -> bool:
        """Merge multiple CSV files.
        
        Args:
            files: List of CSV files to merge
            output_file: Output file path
            how: Merge method ('inner', 'outer', 'left', 'right')
            on: Column(s) to merge on
            suffixes: Suffixes for overlapping columns
            
        Returns:
            bool: Success status
        """
        try:
            if len(files) < 2:
                error_msg = "At least two files are required for merging"
                logging.error(error_msg)
                return False
            
            pd = self._get_pandas()
            if pd is None:
                return False

            # Read first file
            result = pd.read_csv(files[0])
            
            # Merge with remaining files
            for file in files[1:]:
                df = pd.read_csv(file)
                result = pd.merge(
                    result,
                    df,
                    how=how,
                    on=on,
                    suffixes=suffixes or ('_1', '_2')
                )
            
            # Write merged result
            result.to_csv(output_file, index=False)
            return True
            
        except Exception as e:
            error_msg = f"Error merging CSV files: {str(e)}"
            logging.error(error_msg)
            return False

# Create instance for direct function access
_csv_tools = CSVTools()
read_csv = _csv_tools.read_csv
write_csv = _csv_tools.write_csv
merge_csv = _csv_tools.merge_csv

if __name__ == "__main__":
    print("\n==================================================")
    print("CSVTools Demonstration")
    print("==================================================\n")
    
    # Create a temporary file for testing
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp:
        temp_file = temp.name
        
        print("1. Writing CSV File")
        print("------------------------------")
        data = [
            {"name": "Alice", "age": 25, "city": "New York"},
            {"name": "Bob", "age": 30, "city": "San Francisco"},
            {"name": "Charlie", "age": 35, "city": "Chicago"}
        ]
        result = write_csv(temp_file, data)
        print(f"Data written successfully: {result}")
        print()
        
        print("2. Reading CSV File")
        print("------------------------------")
        read_data = read_csv(temp_file)
        print("Contents of CSV file:")
        for row in read_data:
            print(row)
        print()
        
        print("3. Merging CSV Files")
        print("------------------------------")
        # Create a second file for merging
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp2:
            temp_file2 = temp2.name
            data2 = [
                {"name": "Alice", "salary": 75000},
                {"name": "Bob", "salary": 85000},
                {"name": "Charlie", "salary": 95000}
            ]
            write_csv(temp_file2, data2)
            
            # Merge files
            with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp3:
                temp_file3 = temp3.name
                result = merge_csv(
                    [temp_file, temp_file2],
                    temp_file3,
                    how='inner',
                    on='name'
                )
                print(f"Files merged successfully: {result}")
                if result:
                    merged_data = read_csv(temp_file3)
                    print("\nMerged contents:")
                    for row in merged_data:
                        print(row)
                print()
        
        # Clean up temporary files
        os.unlink(temp_file)
        os.unlink(temp_file2)
        os.unlink(temp_file3)
    
    print("==================================================")
    print("Demonstration Complete")
    print("==================================================\n")
