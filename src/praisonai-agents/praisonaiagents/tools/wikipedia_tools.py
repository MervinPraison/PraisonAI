"""Wikipedia tools for accessing and searching Wikipedia content.

Usage:
from praisonaiagents.tools import wikipedia_tools
summary = wikipedia_tools.wiki_summary("Python programming language")
page = wikipedia_tools.wiki_page("Python programming language")
results = wikipedia_tools.wiki_search("Python programming")

or
from praisonaiagents.tools import wiki_search, wiki_summary, wiki_page
summary = wiki_summary("Python programming language")
"""

import logging
from typing import List, Dict, Union, Any
from importlib import util
import json

class WikipediaTools:
    """Tools for accessing and searching Wikipedia content."""
    
    def __init__(self):
        """Initialize WikipediaTools and check for wikipedia package."""
        self._check_wikipedia()
        
    def _check_wikipedia(self):
        """Check if wikipedia package is installed."""
        if util.find_spec("wikipedia") is None:
            raise ImportError("wikipedia package is not available. Please install it using: pip install wikipedia")
        global wikipedia
        import wikipedia
        # Set default language to English
        wikipedia.set_lang("en")

    def wiki_search(
        self, 
        query: str, 
        results: int = 10, 
        suggestion: bool = True
    ) -> Union[List[str], Dict[str, str]]:
        """
        Search Wikipedia for a query.
        
        Args:
            query: Search query
            results: Maximum number of results to return
            suggestion: Whether to suggest similar queries
            
        Returns:
            List[str] or Dict: List of search results or error dict
        """
        try:
            search_results = wikipedia.search(query, results=results, suggestion=suggestion)
            if isinstance(search_results, tuple):
                # If suggestion is True, returns (results, suggestion)
                return {
                    "results": search_results[0],
                    "suggestion": search_results[1] if search_results[1] else None
                }
            return {"results": search_results, "suggestion": None}
        except Exception as e:
            error_msg = f"Error searching Wikipedia for '{query}': {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def wiki_summary(
        self, 
        title: str, 
        sentences: int = 5, 
        auto_suggest: bool = True
    ) -> Union[str, Dict[str, str]]:
        """
        Get a summary of a Wikipedia page.
        
        Args:
            title: Title of the Wikipedia page
            sentences: Number of sentences to return
            auto_suggest: Whether to auto-suggest similar titles
            
        Returns:
            str or Dict: Page summary if successful, error dict if failed
        """
        try:
            return wikipedia.summary(title, sentences=sentences, auto_suggest=auto_suggest)
        except wikipedia.exceptions.DisambiguationError as e:
            return {
                "error": "Disambiguation page",
                "options": e.options[:10]  # Limit to first 10 options
            }
        except Exception as e:
            error_msg = f"Error getting summary for '{title}': {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def wiki_page(
        self, 
        title: str, 
        auto_suggest: bool = True
    ) -> Union[Dict[str, Any], Dict[str, str]]:
        """
        Get detailed information about a Wikipedia page.
        
        Args:
            title: Title of the Wikipedia page
            auto_suggest: Whether to auto-suggest similar titles
            
        Returns:
            Dict: Page information if successful, error dict if failed
        """
        try:
            page = wikipedia.page(title, auto_suggest=auto_suggest)
            return {
                "title": page.title,
                "url": page.url,
                "content": page.content,
                "summary": page.summary,
                "references": page.references,
                "categories": page.categories,
                "links": page.links,
                "images": page.images,
                "sections": self.get_sections(page)
            }
        except wikipedia.exceptions.DisambiguationError as e:
            return {
                "error": "Disambiguation page",
                "options": e.options[:10]  # Limit to first 10 options
            }
        except Exception as e:
            error_msg = f"Error getting page for '{title}': {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_sections(self, page: Any) -> List[Dict[str, Any]]:
        """
        Extract sections and their content from a Wikipedia page.
        
        Args:
            page: Wikipedia page object
            
        Returns:
            List[Dict]: List of sections with their titles and content
        """
        sections = []
        content = page.content
        section_titles = [s.strip() for s in content.split("==")[1::2]]
        section_contents = [s.strip() for s in content.split("==")[2::2]]
        
        # Add introduction section
        intro = content.split("==")[0].strip()
        if intro:
            sections.append({
                "title": "Introduction",
                "level": 0,
                "content": intro
            })
        
        # Process remaining sections
        for title, content in zip(section_titles, section_contents):
            # Count leading '=' to determine section level
            level = title.count("=") // 2
            clean_title = title.strip("= ")
            
            sections.append({
                "title": clean_title,
                "level": level,
                "content": content.strip()
            })
        
        return sections

    def wiki_random(self, pages: int = 1) -> Union[List[str], Dict[str, str]]:
        """
        Get random Wikipedia page titles.
        
        Args:
            pages: Number of random pages to return
            
        Returns:
            List[str] or Dict: List of random page titles or error dict
        """
        try:
            return wikipedia.random(pages)
        except Exception as e:
            error_msg = f"Error getting random pages: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def wiki_language(self, language: str) -> bool:
        """
        Set the language for Wikipedia searches.
        
        Args:
            language: Language code (e.g., 'en' for English, 'es' for Spanish)
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            wikipedia.set_lang(language)
            return True
        except Exception as e:
            error_msg = f"Error setting language to '{language}': {str(e)}"
            logging.error(error_msg)
            return False

# Create instance for direct function access
_wikipedia_tools = WikipediaTools()
wiki_search = _wikipedia_tools.wiki_search
wiki_summary = _wikipedia_tools.wiki_summary
wiki_page = _wikipedia_tools.wiki_page
wiki_random = _wikipedia_tools.wiki_random
wiki_language = _wikipedia_tools.wiki_language

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("WikipediaTools Demonstration")
    print("==================================================\n")
    
    # 1. Search for a topic
    print("1. Searching Wikipedia")
    print("------------------------------")
    search_results = wiki_search("Python programming language")
    print("Search results:")
    print(json.dumps(search_results, indent=2))
    print()
    
    # 2. Get a page summary
    print("2. Getting Page Summary")
    print("------------------------------")
    summary = wiki_summary("Python programming language", sentences=3)
    print("Summary:")
    print(summary)
    print()
    
    # 3. Get detailed page information
    print("3. Getting Full Page Information")
    print("------------------------------")
    page = wiki_page("Python programming language")
    if isinstance(page, dict) and "error" not in page:
        print("Page sections:")
        for section in page["sections"]:
            print(f"- {section['title']} (Level {section['level']})")
        print(f"\nNumber of references: {len(page['references'])}")
        print(f"Number of categories: {len(page['categories'])}")
        print(f"Number of links: {len(page['links'])}")
        print(f"Number of images: {len(page['images'])}")
    else:
        print("Error getting page:", page.get("error"))
    print()
    
    # 4. Get random pages
    print("4. Getting Random Pages")
    print("------------------------------")
    random_pages = wiki_random(3)
    print("Random page titles:")
    print(json.dumps(random_pages, indent=2))
    print()
    
    # 5. Try different language
    print("5. Changing Language")
    print("------------------------------")
    success = wiki_language("es")
    if success:
        summary = wiki_summary("Python (lenguaje de programación)", sentences=1)
        print("Spanish summary:")
        print(summary)
    print()
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
