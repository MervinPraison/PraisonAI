"""Tools for working with Excel files.

Usage:
from praisonaiagents.tools import excel_tools
df = excel_tools.read_excel("data.xlsx")

or
from praisonaiagents.tools import read_excel, write_excel, merge_excel
df = read_excel("data.xlsx")
"""

import logging
from typing import List, Dict, Union, Optional, Any, TYPE_CHECKING, Tuple
from importlib import util
import json
from pathlib import Path
import tempfile
import os

if TYPE_CHECKING:
    import pandas as pd
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList

class ExcelTools:
    """Tools for working with Excel files."""
    
    def __init__(self):
        """Initialize ExcelTools."""
        pass

    def _get_pandas(self) -> Optional['pd']:
        """Get pandas module, installing if needed"""
        if util.find_spec('pandas') is None:
            error_msg = "pandas package is not available. Please install it using: pip install pandas"
            logging.error(error_msg)
            return None
        if util.find_spec('openpyxl') is None:
            error_msg = "openpyxl package is not available. Please install it using: pip install openpyxl"
            logging.error(error_msg)
            return None
        import pandas as pd
        return pd

    def read_excel(
        self,
        filepath: str,
        sheet_name: Optional[Union[str, int, List[Union[str, int]]]] = 0,
        header: Optional[int] = 0,
        usecols: Optional[List[str]] = None,
        skiprows: Optional[Union[int, List[int]]] = None,
        na_values: Optional[List[str]] = None,
        dtype: Optional[Dict[str, str]] = None
    ) -> Union[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """Read an Excel file with advanced options.
        
        Args:
            filepath: Path to Excel file
            sheet_name: Sheet name(s) or index(es)
            header: Row number(s) to use as column names
            usecols: Columns to read
            skiprows: Line numbers to skip
            na_values: Additional strings to recognize as NA/NaN
            dtype: Dict of column dtypes
            
        Returns:
            Dict of sheet names to data if multiple sheets, else list of row dicts
        """
        try:
            pd = self._get_pandas()
            if pd is None:
                return {"error": "Required packages not available"}

            # Read Excel file
            df = pd.read_excel(
                filepath,
                sheet_name=sheet_name,
                header=header,
                usecols=usecols,
                skiprows=skiprows,
                na_values=na_values,
                dtype=dtype,
                engine='openpyxl'
            )
            
            # Convert to dict format
            if isinstance(df, dict):
                return {
                    name: df[name].to_dict('records')
                    for name in df.keys()
                }
            else:
                return df.to_dict('records')
                
        except Exception as e:
            error_msg = f"Error reading Excel file {filepath}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def write_excel(
        self,
        filepath: str,
        data: Union[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]],
        sheet_name: Optional[str] = None,
        index: bool = False,
        header: bool = True,
        mode: str = 'w'
    ) -> bool:
        """Write data to an Excel file.
        
        Args:
            filepath: Path to Excel file
            data: Data to write (dict of sheet names to data or list of row dicts)
            sheet_name: Sheet name if data is a list
            index: Whether to write row indices
            header: Whether to write column headers
            mode: Write mode ('w' for write, 'a' for append)
            
        Returns:
            bool: Success status
        """
        try:
            pd = self._get_pandas()
            if pd is None:
                return False

            # Convert data to DataFrame(s)
            if isinstance(data, dict):
                if mode == 'a' and os.path.exists(filepath):
                    book = pd.ExcelFile(filepath)
                    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                        # Copy existing sheets
                        for sheet in book.sheet_names:
                            pd.read_excel(filepath, sheet_name=sheet).to_excel(
                                writer, sheet_name=sheet, index=index, header=header
                            )
                        # Add new sheets
                        for name, sheet_data in data.items():
                            df = pd.DataFrame(sheet_data)
                            df.to_excel(
                                writer, sheet_name=name, index=index, header=header
                            )
                else:
                    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                        for name, sheet_data in data.items():
                            df = pd.DataFrame(sheet_data)
                            df.to_excel(
                                writer, sheet_name=name, index=index, header=header
                            )
            else:
                if mode == 'a' and os.path.exists(filepath):
                    book = pd.ExcelFile(filepath)
                    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                        # Copy existing sheets
                        for sheet in book.sheet_names:
                            pd.read_excel(filepath, sheet_name=sheet).to_excel(
                                writer, sheet_name=sheet, index=index, header=header
                            )
                        # Add new sheet
                        df = pd.DataFrame(data)
                        df.to_excel(
                            writer,
                            sheet_name=sheet_name or 'Sheet1',
                            index=index,
                            header=header
                        )
                else:
                    df = pd.DataFrame(data)
                    df.to_excel(
                        filepath,
                        sheet_name=sheet_name or 'Sheet1',
                        index=index,
                        header=header,
                        engine='openpyxl'
                    )
            
            return True
            
        except Exception as e:
            error_msg = f"Error writing Excel file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def merge_excel(
        self,
        files: List[str],
        output_file: str,
        how: str = 'inner',
        on: Optional[Union[str, List[str]]] = None,
        suffixes: Optional[Tuple[str, str]] = None
    ) -> bool:
        """Merge multiple Excel files.
        
        Args:
            files: List of Excel files to merge
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
            
            # Read first file
            result = self.read_excel(files[0])
            
            # Merge with remaining files
            for file in files[1:]:
                df = self.read_excel(file)
                if isinstance(df, dict):
                    df = next(iter(df.values()))
                
                pd = self._get_pandas()
                if pd is None:
                    return False
                
                result = pd.merge(
                    pd.DataFrame(result),
                    pd.DataFrame(df),
                    how=how,
                    on=on,
                    suffixes=suffixes or ('_1', '_2')
                ).to_dict('records')
            
            # Write merged result
            return self.write_excel(output_file, result)
            
        except Exception as e:
            error_msg = f"Error merging Excel files: {str(e)}"
            logging.error(error_msg)
            return False

# Create instance for direct function access
_excel_tools = ExcelTools()
read_excel = _excel_tools.read_excel
write_excel = _excel_tools.write_excel
merge_excel = _excel_tools.merge_excel

if __name__ == "__main__":
    print("\n==================================================")
    print("ExcelTools Demonstration")
    print("==================================================\n")
    
    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp:
        temp_file = temp.name
        
        print("1. Writing Excel File")
        print("------------------------------")
        data = [
            {"name": "Alice", "age": 25, "city": "New York"},
            {"name": "Bob", "age": 30, "city": "San Francisco"},
            {"name": "Charlie", "age": 35, "city": "Chicago"}
        ]
        result = write_excel(temp_file, data, "People")
        print(f"Data written successfully: {result}")
        print()
        
        print("2. Reading Excel File")
        print("------------------------------")
        read_data = read_excel(temp_file)
        print("Contents of Excel file:")
        for row in read_data:
            print(row)
        print()
        
        print("3. Merging Excel Files")
        print("------------------------------")
        # Create a second file for merging
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp2:
            temp_file2 = temp2.name
            data2 = [
                {"name": "Alice", "salary": 75000},
                {"name": "Bob", "salary": 85000},
                {"name": "Charlie", "salary": 95000}
            ]
            write_excel(temp_file2, data2, "Salaries")
            
            # Merge files
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp3:
                temp_file3 = temp3.name
                result = merge_excel(
                    [temp_file, temp_file2],
                    temp_file3,
                    how='inner',
                    on='name'
                )
                print(f"Files merged successfully: {result}")
                if result:
                    merged_data = read_excel(temp_file3)
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
