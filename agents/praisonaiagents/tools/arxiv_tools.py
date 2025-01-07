"""Tools for searching and retrieving papers from arXiv.

Usage:
from praisonaiagents.tools import arxiv_tools
papers = arxiv_tools.search("quantum computing")
paper = arxiv_tools.get_paper("2401.00123")

or
from praisonaiagents.tools import search_arxiv, get_arxiv_paper
papers = search_arxiv("quantum computing")
"""

import logging
from typing import List, Dict, Union, Optional, Any
from importlib import util
import json

# Map sort criteria to arxiv.SortCriterion
SORT_CRITERIA = {
    "relevance": "Relevance",
    "lastupdateddate": "LastUpdatedDate",
    "submitteddate": "SubmittedDate"
}

# Map sort order to arxiv.SortOrder
SORT_ORDER = {
    "ascending": "Ascending",
    "descending": "Descending"
}

class ArxivTools:
    """Tools for searching and retrieving papers from arXiv."""
    
    def __init__(self):
        """Initialize ArxivTools and check for arxiv package."""
        self._check_arxiv()
        
    def _check_arxiv(self):
        """Check if arxiv package is installed."""
        if util.find_spec("arxiv") is None:
            raise ImportError("arxiv package is not available. Please install it using: pip install arxiv")
        global arxiv
        import arxiv

    def search(
        self,
        query: str,
        max_results: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "descending",
        include_fields: Optional[List[str]] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """
        Search arXiv for papers matching the query.
        
        Args:
            query: Search query (e.g., "quantum computing", "author:Einstein")
            max_results: Maximum number of results to return
            sort_by: Sort results by ("relevance", "lastUpdatedDate", "submittedDate")
            sort_order: Sort order ("ascending" or "descending")
            include_fields: List of fields to include in results. If None, includes all.
                Available fields: ["title", "authors", "summary", "comment", "journal_ref",
                "doi", "primary_category", "categories", "links"]
            
        Returns:
            List[Dict] or Dict: List of papers or error dict
        """
        try:
            import arxiv
            
            # Configure search client
            client = arxiv.Client()
            
            # Map sort criteria
            sort_by_enum = getattr(arxiv.SortCriterion, SORT_CRITERIA[sort_by.lower()])
            sort_order_enum = getattr(arxiv.SortOrder, SORT_ORDER[sort_order.lower()])
            
            # Build search query
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=sort_by_enum,
                sort_order=sort_order_enum
            )
            
            # Execute search
            results = []
            for result in client.results(search):
                # Convert to dict with selected fields
                paper = self._result_to_dict(result, include_fields)
                results.append(paper)
            
            return results
        except Exception as e:
            error_msg = f"Error searching arXiv: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_paper(
        self,
        paper_id: str,
        include_fields: Optional[List[str]] = None
    ) -> Union[Dict[str, Any], Dict[str, str]]:
        """
        Get details of a specific paper by its arXiv ID.
        
        Args:
            paper_id: arXiv paper ID (e.g., "2401.00123")
            include_fields: List of fields to include in results. If None, includes all.
                Available fields: ["title", "authors", "summary", "comment", "journal_ref",
                "doi", "primary_category", "categories", "links"]
            
        Returns:
            Dict: Paper details or error dict
        """
        try:
            import arxiv
            
            # Configure client
            client = arxiv.Client()
            
            # Get paper by ID
            search = arxiv.Search(id_list=[paper_id])
            results = list(client.results(search))
            
            if not results:
                return {"error": f"Paper with ID {paper_id} not found"}
            
            # Convert to dict with selected fields
            paper = self._result_to_dict(results[0], include_fields)
            return paper
        except Exception as e:
            error_msg = f"Error getting paper {paper_id}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_papers_by_author(
        self,
        author: str,
        max_results: int = 10,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
        include_fields: Optional[List[str]] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """
        Get papers by a specific author.
        
        Args:
            author: Author name (e.g., "Einstein")
            max_results: Maximum number of results to return
            sort_by: Sort results by ("relevance", "lastUpdatedDate", "submittedDate")
            sort_order: Sort order ("ascending" or "descending")
            include_fields: List of fields to include in results
            
        Returns:
            List[Dict] or Dict: List of papers or error dict
        """
        query = f'au:"{author}"'
        return self.search(query, max_results, sort_by, sort_order, include_fields)

    def get_papers_by_category(
        self,
        category: str,
        max_results: int = 10,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
        include_fields: Optional[List[str]] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """
        Get papers from a specific category.
        
        Args:
            category: arXiv category (e.g., "cs.AI", "physics.gen-ph")
            max_results: Maximum number of results to return
            sort_by: Sort results by ("relevance", "lastUpdatedDate", "submittedDate")
            sort_order: Sort order ("ascending" or "descending")
            include_fields: List of fields to include in results
            
        Returns:
            List[Dict] or Dict: List of papers or error dict
        """
        query = f'cat:{category}'
        return self.search(query, max_results, sort_by, sort_order, include_fields)

    def _result_to_dict(
        self,
        result: Any,
        include_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Convert arxiv.Result to dictionary with selected fields."""
        # Default fields to include
        if include_fields is None:
            include_fields = [
                "title", "authors", "summary", "comment", "journal_ref",
                "doi", "primary_category", "categories", "links"
            ]
        
        # Build paper dict with selected fields
        paper = {}
        
        # Always include these basic fields
        paper["arxiv_id"] = result.entry_id.split("/")[-1]
        paper["updated"] = result.updated.isoformat() if result.updated else None
        paper["published"] = result.published.isoformat() if result.published else None
        
        # Add requested fields
        if "title" in include_fields:
            paper["title"] = result.title
        if "authors" in include_fields:
            paper["authors"] = [str(author) for author in result.authors]
        if "summary" in include_fields:
            paper["summary"] = result.summary
        if "comment" in include_fields:
            paper["comment"] = result.comment
        if "journal_ref" in include_fields:
            paper["journal_ref"] = result.journal_ref
        if "doi" in include_fields:
            paper["doi"] = result.doi
        if "primary_category" in include_fields:
            paper["primary_category"] = result.primary_category
        if "categories" in include_fields:
            paper["categories"] = result.categories
        if "links" in include_fields:
            paper["pdf_url"] = result.pdf_url
            paper["abstract_url"] = f"https://arxiv.org/abs/{paper['arxiv_id']}"
        
        return paper

# Create instance for direct function access
_arxiv_tools = ArxivTools()
search_arxiv = _arxiv_tools.search
get_arxiv_paper = _arxiv_tools.get_paper
get_papers_by_author = _arxiv_tools.get_papers_by_author
get_papers_by_category = _arxiv_tools.get_papers_by_category

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("ArxivTools Demonstration")
    print("==================================================\n")
    
    # 1. Search for papers
    print("1. Searching for Papers")
    print("------------------------------")
    query = "quantum computing"
    papers = search_arxiv(query, max_results=3)
    print(f"Papers about {query}:")
    if isinstance(papers, list):
        print(json.dumps(papers, indent=2))
    else:
        print(papers)  # Show error
    print()
    
    # 2. Get specific paper
    print("2. Getting Specific Paper")
    print("------------------------------")
    if isinstance(papers, list) and papers:
        paper_id = papers[0]["arxiv_id"]
        paper = get_arxiv_paper(paper_id)
        print(f"Paper {paper_id}:")
        if "error" not in paper:
            print(json.dumps(paper, indent=2))
        else:
            print(paper)  # Show error
    print()
    
    # 3. Get papers by author
    print("3. Getting Papers by Author")
    print("------------------------------")
    author = "Yoshua Bengio"
    author_papers = get_papers_by_author(author, max_results=3)
    print(f"Papers by {author}:")
    if isinstance(author_papers, list):
        print(json.dumps(author_papers, indent=2))
    else:
        print(author_papers)  # Show error
    print()
    
    # 4. Get papers by category
    print("4. Getting Papers by Category")
    print("------------------------------")
    category = "cs.AI"
    category_papers = get_papers_by_category(category, max_results=3)
    print(f"Papers in category {category}:")
    if isinstance(category_papers, list):
        print(json.dumps(category_papers, indent=2))
    else:
        print(category_papers)  # Show error
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
