"""Langextract tools for interactive text analysis and extraction.

Provides first-class tool integration for langextract functionality,
allowing agents to create interactive HTML visualizations from text.

Usage:
    from praisonaiagents.tools import langextract_extract
    
    # Agent can call this tool directly
    result = langextract_extract(
        text="The quick brown fox jumps over the lazy dog.",
        extractions=["fox", "dog"]
    )

Architecture:
    - Follows AGENTS.md tool patterns (decorator-based, lazy imports)
    - Protocol-driven design with optional dependencies
    - Zero overhead when langextract is not installed
"""

from typing import List, Optional, Dict, Any
from ..approval import require_approval
from .decorator import tool


@tool
def langextract_extract(
    text: str,
    extractions: Optional[List[str]] = None,
    document_id: str = "agent-analysis",
    output_path: Optional[str] = None,
    auto_open: bool = False
) -> Dict[str, Any]:
    """Extract and annotate text using langextract for interactive visualization.
    
    Creates an interactive HTML document with highlighted extractions that can be
    viewed in a browser. Useful for text analysis, entity extraction, and 
    document annotation workflows.
    
    Args:
        text: The source text to analyze and extract from
        extractions: List of text snippets to highlight in the document
        document_id: Identifier for the document (used in HTML output)
        output_path: Path to save HTML file (defaults to temp file)
        auto_open: Whether to automatically open the HTML file in browser
        
    Returns:
        Dict containing:
        - html_path: Path to the generated HTML file
        - extractions_count: Number of extractions processed
        - document_id: The document identifier used
        - success: True if successful, False otherwise
        - error: Error message if success is False
        
    Raises:
        ImportError: If langextract is not installed
        ValueError: If text is empty or invalid
    """
    if not text or not text.strip():
        return {
            "success": False,
            "error": "Text cannot be empty",
            "html_path": None,
            "extractions_count": 0,
            "document_id": document_id
        }
    
    try:
        # Lazy import langextract (optional dependency)
        try:
            import langextract as lx  # type: ignore
        except ImportError:
            return {
                "success": False,
                "error": "langextract is not installed. Install with: pip install langextract",
                "html_path": None,
                "extractions_count": 0,
                "document_id": document_id
            }
        
        # Process extractions if provided
        extractions_list = extractions or []
        extraction_objects = []
        added_count = 0
        
        for i, extraction_text in enumerate(extractions_list):
            if not extraction_text.strip():
                continue
                
            # Find all occurrences of the extraction in the text
            start_pos = 0
            while True:
                pos = text.lower().find(extraction_text.lower(), start_pos)
                if pos == -1:
                    break
                
                # Create extraction with proper CharInterval
                extraction = lx.data.Extraction(
                    extraction_class=f"extraction_{i}",
                    extraction_text=extraction_text,
                    char_interval=lx.data.CharInterval(
                        start_pos=pos,
                        end_pos=pos + len(extraction_text)
                    ),
                    attributes={
                        "index": i,
                        "original_text": extraction_text,
                        "tool": "langextract_extract"
                    }
                )
                extraction_objects.append(extraction)
                added_count += 1
                start_pos = pos + 1
        
        # Create AnnotatedDocument with extractions
        document = lx.data.AnnotatedDocument(
            document_id=document_id,
            text=text,
            extractions=extraction_objects
        )
        
        # Determine output path
        if not output_path:
            import tempfile
            import os
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"langextract_{document_id}.html"
            )
        
        # Save as JSONL first, then render HTML
        import tempfile
        import os
        
        # Create temporary JSONL file
        jsonl_dir = tempfile.gettempdir()
        jsonl_path = os.path.join(jsonl_dir, f"langextract_{document_id}.jsonl")
        
        lx.io.save_annotated_documents(
            [document],
            output_name=os.path.basename(jsonl_path),
            output_dir=jsonl_dir
        )
        
        # Generate HTML using visualize
        html = lx.visualize(jsonl_path)
        html_content = html.data if hasattr(html, 'data') else html
        
        # Write HTML file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        # Clean up temporary JSONL
        try:
            os.remove(jsonl_path)
        except OSError:
            pass
        
        # Auto-open if requested
        if auto_open:
            import webbrowser
            from pathlib import Path
            webbrowser.open(Path(output_path).resolve().as_uri())
        
        return {
            "success": True,
            "html_path": output_path,
            "extractions_count": added_count,
            "document_id": document_id,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "html_path": None,
            "extractions_count": 0,
            "document_id": document_id
        }


@tool
@require_approval(risk_level="high")
def langextract_render_file(
    file_path: str,
    extractions: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    auto_open: bool = False
) -> Dict[str, Any]:
    """Read a text file and create langextract visualization.
    
    Reads a text file from disk and creates an interactive HTML visualization
    with optional extractions highlighted.
    
    Args:
        file_path: Path to the text file to read
        extractions: List of text snippets to highlight
        output_path: Path to save HTML file (defaults to same dir as input)
        auto_open: Whether to automatically open the HTML file in browser
        
    Returns:
        Dict with same structure as langextract_extract
        
    Raises:
        FileNotFoundError: If file_path does not exist
        ImportError: If langextract is not installed
    """
    import os
    
    if not os.path.exists(file_path):
        return {
            "success": False,
            "error": f"File not found: {file_path}",
            "html_path": None,
            "extractions_count": 0,
            "document_id": os.path.basename(file_path)
        }
    
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Default output path to same directory as input
        if not output_path:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_dir = os.path.dirname(file_path)
            output_path = os.path.join(output_dir, f"{base_name}_annotated.html")
        
        # Use the main extract function
        return langextract_extract(
            text=text,
            extractions=extractions,
            document_id=os.path.basename(file_path),
            output_path=output_path,
            auto_open=auto_open
        )
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "html_path": None,
            "extractions_count": 0,
            "document_id": os.path.basename(file_path)
        }


# Export for direct import
__all__ = ["langextract_extract", "langextract_render_file"]