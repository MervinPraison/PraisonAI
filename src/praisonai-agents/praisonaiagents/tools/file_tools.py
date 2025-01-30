"""File handling tools for basic file operations.

Usage:
from praisonaiagents.tools import file_tools
content = file_tools.read_file("example.txt")
file_tools.write_file("output.txt", "Hello World")

or 
from praisonaiagents.tools import read_file, write_file, list_files
content = read_file("example.txt")
"""

import os
import json
from typing import List, Dict, Union, Optional
from pathlib import Path
import shutil
import logging

class FileTools:
    """Tools for file operations including read, write, list, and information."""
    
    @staticmethod
    def read_file(filepath: str, encoding: str = 'utf-8') -> str:
        """
        Read content from a file.
        
        Args:
            filepath: Path to the file
            encoding: File encoding (default: utf-8)
            
        Returns:
            str: Content of the file
        """
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()
        except Exception as e:
            error_msg = f"Error reading file {filepath}: {str(e)}"
            logging.error(error_msg)
            return error_msg

    @staticmethod
    def write_file(filepath: str, content: str, encoding: str = 'utf-8') -> bool:
        """
        Write content to a file.
        
        Args:
            filepath: Path to the file
            content: Content to write
            encoding: File encoding (default: utf-8)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(content)
            return True
        except Exception as e:
            error_msg = f"Error writing to file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    @staticmethod
    def list_files(directory: str, pattern: Optional[str] = None) -> List[Dict[str, Union[str, int]]]:
        """
        List files in a directory with optional pattern matching.
        
        Args:
            directory: Directory path
            pattern: Optional glob pattern (e.g., "*.txt")
            
        Returns:
            List[Dict]: List of file information dictionaries
        """
        try:
            path = Path(directory)
            if pattern:
                files = path.glob(pattern)
            else:
                files = path.iterdir()

            result = []
            for file in files:
                if file.is_file():
                    stat = file.stat()
                    result.append({
                        'name': file.name,
                        'path': str(file),
                        'size': stat.st_size,
                        'modified': stat.st_mtime,
                        'created': stat.st_ctime
                    })
            return result
        except Exception as e:
            error_msg = f"Error listing files in {directory}: {str(e)}"
            logging.error(error_msg)
            return [{'error': error_msg}]

    @staticmethod
    def get_file_info(filepath: str) -> Dict[str, Union[str, int]]:
        """
        Get detailed information about a file.
        
        Args:
            filepath: Path to the file
            
        Returns:
            Dict: File information including size, dates, etc.
        """
        try:
            path = Path(filepath)
            if not path.exists():
                return {'error': f'File not found: {filepath}'}
            
            stat = path.stat()
            return {
                'name': path.name,
                'path': str(path),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'created': stat.st_ctime,
                'is_file': path.is_file(),
                'is_dir': path.is_dir(),
                'extension': path.suffix,
                'parent': str(path.parent)
            }
        except Exception as e:
            error_msg = f"Error getting file info for {filepath}: {str(e)}"
            logging.error(error_msg)
            return {'error': error_msg}

    @staticmethod
    def copy_file(src: str, dst: str) -> bool:
        """
        Copy a file from source to destination.
        
        Args:
            src: Source file path
            dst: Destination file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create destination directory if it doesn't exist
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return True
        except Exception as e:
            error_msg = f"Error copying file from {src} to {dst}: {str(e)}"
            logging.error(error_msg)
            return False

    @staticmethod
    def move_file(src: str, dst: str) -> bool:
        """
        Move a file from source to destination.
        
        Args:
            src: Source file path
            dst: Destination file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create destination directory if it doesn't exist
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            return True
        except Exception as e:
            error_msg = f"Error moving file from {src} to {dst}: {str(e)}"
            logging.error(error_msg)
            return False

    @staticmethod
    def delete_file(filepath: str) -> bool:
        """
        Delete a file.
        
        Args:
            filepath: Path to the file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            os.remove(filepath)
            return True
        except Exception as e:
            error_msg = f"Error deleting file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

# Create instance for direct function access
_file_tools = FileTools()
read_file = _file_tools.read_file
write_file = _file_tools.write_file
list_files = _file_tools.list_files
get_file_info = _file_tools.get_file_info
copy_file = _file_tools.copy_file
move_file = _file_tools.move_file
delete_file = _file_tools.delete_file

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("FileTools Demonstration")
    print("==================================================\n")

    # Create a test directory
    test_dir = os.path.join(os.getcwd(), "test_files")
    os.makedirs(test_dir, exist_ok=True)
    
    # Create test files
    test_file = os.path.join(test_dir, "test_file.txt")
    test_content = "Hello, this is a test file!"
    
    print("1. Writing to file")
    print("------------------------------")
    success = write_file(test_file, test_content)
    print(f"Write successful: {success}\n")
    
    print("2. Reading from file")
    print("------------------------------")
    content = read_file(test_file)
    print(f"Content: {content}\n")
    
    print("3. File Information")
    print("------------------------------")
    info = get_file_info(test_file)
    print(json.dumps(info, indent=2))
    print()
    
    print("4. Listing Files")
    print("------------------------------")
    files = list_files(test_dir, "*.txt")
    for file in files:
        print(f"Found: {file['name']} ({file['size']} bytes)")
    print()
    
    print("5. Copying File")
    print("------------------------------")
    copy_file_path = os.path.join(test_dir, "test_file_copy.txt")
    copy_success = copy_file(test_file, copy_file_path)
    print(f"Copy successful: {copy_success}\n")
    
    print("6. Moving File")
    print("------------------------------")
    move_file_path = os.path.join(test_dir, "test_file_moved.txt")
    move_success = move_file(copy_file_path, move_file_path)
    print(f"Move successful: {move_success}\n")
    
    print("7. Deleting Files")
    print("------------------------------")
    delete_success = delete_file(test_file)
    print(f"Delete original successful: {delete_success}")
    delete_success = delete_file(move_file_path)
    print(f"Delete moved file successful: {delete_success}\n")
    
    # Clean up test directory
    try:
        shutil.rmtree(test_dir)
        print("Test directory cleaned up successfully")
    except Exception as e:
        print(f"Error cleaning up test directory: {str(e)}")
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
