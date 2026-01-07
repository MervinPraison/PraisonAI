"""
Sourcegraph Integration Tool for PraisonAI Agents.

Provides code search across repositories using Sourcegraph API.
"""

import os
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SOURCEGRAPH_API_URL = "https://sourcegraph.com/.api"


@dataclass
class CodeResult:
    """A code search result."""
    repository: str
    file_path: str
    line_number: int
    content: str
    url: str
    
    def to_dict(self) -> dict:
        return {
            "repository": self.repository,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "content": self.content,
            "url": self.url,
        }


class SourcegraphTools:
    """
    Sourcegraph code search integration.
    
    Provides code search across public and private repositories
    using the Sourcegraph API.
    
    Usage:
        tools = SourcegraphTools()
        results = tools.search("function handleError")
        
        for result in results:
            print(f"{result.repository}: {result.file_path}:{result.line_number}")
    """
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.api_url = api_url or os.environ.get("SOURCEGRAPH_URL", SOURCEGRAPH_API_URL)
        self.access_token = access_token or os.environ.get("SOURCEGRAPH_ACCESS_TOKEN")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"token {self.access_token}"
        return headers
    
    def search(
        self,
        query: str,
        repo: Optional[str] = None,
        file_pattern: Optional[str] = None,
        max_results: int = 20,
    ) -> List[CodeResult]:
        """
        Search code using Sourcegraph.
        
        Args:
            query: Search query
            repo: Optional repository filter (e.g., "github.com/owner/repo")
            file_pattern: Optional file pattern filter (e.g., "*.py")
            max_results: Maximum number of results
            
        Returns:
            List of CodeResult objects
        """
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed. Install with: pip install httpx")
            return []
        
        # Build search query
        search_query = query
        if repo:
            search_query = f"repo:{repo} {search_query}"
        if file_pattern:
            search_query = f"file:{file_pattern} {search_query}"
        
        # GraphQL query
        graphql_query = """
        query Search($query: String!, $first: Int!) {
            search(query: $query, version: V2) {
                results {
                    results {
                        ... on FileMatch {
                            repository {
                                name
                            }
                            file {
                                path
                                url
                            }
                            lineMatches {
                                lineNumber
                                preview
                            }
                        }
                    }
                }
            }
        }
        """
        
        try:
            response = httpx.post(
                f"{self.api_url}/graphql",
                headers=self._get_headers(),
                json={
                    "query": graphql_query,
                    "variables": {
                        "query": search_query,
                        "first": max_results,
                    }
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            search_results = data.get("data", {}).get("search", {}).get("results", {}).get("results", [])
            
            for match in search_results[:max_results]:
                if "repository" not in match:
                    continue
                    
                repo_name = match["repository"]["name"]
                file_path = match.get("file", {}).get("path", "")
                file_url = match.get("file", {}).get("url", "")
                
                for line_match in match.get("lineMatches", []):
                    results.append(CodeResult(
                        repository=repo_name,
                        file_path=file_path,
                        line_number=line_match.get("lineNumber", 0),
                        content=line_match.get("preview", ""),
                        url=f"{self.api_url.replace('/.api', '')}{file_url}",
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"Sourcegraph search failed: {e}")
            return []
    
    def get_file_content(
        self,
        repo: str,
        file_path: str,
        revision: str = "HEAD",
    ) -> Optional[str]:
        """
        Get file content from a repository.
        
        Args:
            repo: Repository name (e.g., "github.com/owner/repo")
            file_path: Path to file in repository
            revision: Git revision (default: HEAD)
            
        Returns:
            File content or None if not found
        """
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed")
            return None
        
        graphql_query = """
        query GetFile($repo: String!, $path: String!, $rev: String!) {
            repository(name: $repo) {
                commit(rev: $rev) {
                    file(path: $path) {
                        content
                    }
                }
            }
        }
        """
        
        try:
            response = httpx.post(
                f"{self.api_url}/graphql",
                headers=self._get_headers(),
                json={
                    "query": graphql_query,
                    "variables": {
                        "repo": repo,
                        "path": file_path,
                        "rev": revision,
                    }
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            
            content = (
                data.get("data", {})
                .get("repository", {})
                .get("commit", {})
                .get("file", {})
                .get("content")
            )
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to get file content: {e}")
            return None


def get_sourcegraph_tools() -> List[callable]:
    """Get Sourcegraph tools as callable functions for agent use."""
    tools = SourcegraphTools()
    
    def search_code(query: str, repo: str = None, max_results: int = 10) -> str:
        """Search code across repositories using Sourcegraph."""
        results = tools.search(query, repo=repo, max_results=max_results)
        if not results:
            return "No results found"
        
        output = []
        for r in results:
            output.append(f"{r.repository}/{r.file_path}:{r.line_number}")
            output.append(f"  {r.content.strip()}")
            output.append("")
        
        return "\n".join(output)
    
    return [search_code]
