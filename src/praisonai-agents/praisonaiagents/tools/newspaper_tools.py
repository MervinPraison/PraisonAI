"""Newspaper tools for scraping and parsing news articles.

Usage:
from praisonaiagents.tools import newspaper_tools
article = newspaper_tools.get_article("https://example.com/article")
sources = newspaper_tools.get_news_sources("technology")
articles = newspaper_tools.get_articles_from_source("https://techcrunch.com")

or
from praisonaiagents.tools import get_article, get_news_sources
article = get_article("https://example.com/article")
"""

import logging
from typing import List, Dict, Union, Optional, Any
from importlib import util
import json
from urllib.parse import urlparse

# Predefined list of popular news sources
POPULAR_NEWS_SOURCES = {
    'technology': [
        'https://techcrunch.com',
        'https://www.theverge.com',
        'https://www.wired.com',
        'https://www.engadget.com',
        'https://arstechnica.com'
    ],
    'business': [
        'https://www.bloomberg.com',
        'https://www.reuters.com',
        'https://www.wsj.com',
        'https://www.ft.com',
        'https://www.cnbc.com'
    ],
    'general': [
        'https://www.nytimes.com',
        'https://www.theguardian.com',
        'https://www.washingtonpost.com',
        'https://www.bbc.com',
        'https://www.cnn.com'
    ],
    'sports': [
        'https://www.espn.com',
        'https://sports.yahoo.com',
        'https://www.cbssports.com',
        'https://www.skysports.com',
        'https://www.bleacherreport.com'
    ],
    'entertainment': [
        'https://variety.com',
        'https://www.hollywoodreporter.com',
        'https://www.ew.com',
        'https://www.deadline.com',
        'https://www.imdb.com/news'
    ],
    'science': [
        'https://www.scientificamerican.com',
        'https://www.sciencedaily.com',
        'https://www.newscientist.com',
        'https://www.sciencemag.org',
        'https://www.nature.com/news'
    ]
}

class NewspaperTools:
    """Tools for scraping and parsing news articles."""
    
    def __init__(self):
        """Initialize NewspaperTools and check for newspaper package."""
        self._check_newspaper()
        
    def _check_newspaper(self):
        """Check if newspaper package is installed."""
        if util.find_spec("newspaper") is None:
            raise ImportError("newspaper3k package is not available. Please install it using: pip install newspaper3k")
        global newspaper
        import newspaper

    def get_article(
        self, 
        url: str,
        language: str = 'en'
    ) -> Dict[str, Any]:
        """
        Extract and parse a news article from a URL.
        
        Args:
            url: URL of the article
            language: Language code (e.g., 'en' for English)
            
        Returns:
            Dict: Article information including title, text, authors, etc.
        """
        try:
            from newspaper import Article, Config
            
            # Configure article download
            config = Config()
            config.browser_user_agent = 'Mozilla/5.0'
            config.language = language
            
            # Download and parse article
            article = Article(url, config=config)
            article.download()
            article.parse()
            
            # Try to extract additional information
            try:
                article.nlp()
            except Exception as e:
                logging.warning(f"NLP processing failed: {str(e)}")
            
            # Build response
            response = {
                "url": url,
                "title": article.title,
                "text": article.text,
                "authors": article.authors,
                "publish_date": article.publish_date.isoformat() if article.publish_date else None,
                "top_image": article.top_image,
                "images": list(article.images),
                "movies": list(article.movies),
                "source_domain": urlparse(url).netloc,
            }
            
            # Add NLP results if available
            if hasattr(article, 'keywords') and article.keywords:
                response["keywords"] = article.keywords
            if hasattr(article, 'summary') and article.summary:
                response["summary"] = article.summary
            
            return response
        except Exception as e:
            error_msg = f"Error extracting article from {url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_news_sources(
        self, 
        category: Optional[str] = None,
        language: str = 'en',
        country: Optional[str] = None
    ) -> Union[List[Dict[str, str]], Dict[str, str]]:
        """
        Get a list of news sources, optionally filtered by category.
        
        Args:
            category: Category to filter by (e.g., 'technology', 'sports')
            language: Language code
            country: Country code
            
        Returns:
            List[Dict] or Dict: List of news sources or error dict
        """
        try:
            sources = []
            
            # Get sources for the specified category or all categories
            if category:
                category = category.lower()
                if category in POPULAR_NEWS_SOURCES:
                    urls = POPULAR_NEWS_SOURCES[category]
                else:
                    urls = []
                    for cat_urls in POPULAR_NEWS_SOURCES.values():
                        urls.extend(cat_urls)
            else:
                urls = []
                for cat_urls in POPULAR_NEWS_SOURCES.values():
                    urls.extend(cat_urls)
            
            # Create source objects
            for url in urls:
                domain = urlparse(url).netloc
                source = {
                    "url": url,
                    "domain": domain,
                    "name": domain.replace("www.", "").split(".")[0].title(),
                    "category": category if category else "general"
                }
                sources.append(source)
            
            return sources
        except Exception as e:
            error_msg = f"Error getting news sources: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_articles_from_source(
        self, 
        source_url: str,
        limit: int = 10,
        language: str = 'en'
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """
        Get recent articles from a news source.
        
        Args:
            source_url: URL of the news source
            limit: Maximum number of articles to return
            language: Language code
            
        Returns:
            List[Dict] or Dict: List of articles or error dict
        """
        try:
            from newspaper import Source, Config
            
            # Configure source scraping
            config = Config()
            config.browser_user_agent = 'Mozilla/5.0'
            config.language = language
            config.fetch_images = False  # Speed up processing
            
            # Build news source
            source = Source(source_url, config=config)
            source.build()
            
            # Get articles
            articles = []
            for article_url in source.article_urls()[:limit]:
                try:
                    article = self.get_article(article_url, language)
                    if "error" not in article:
                        articles.append(article)
                except Exception as e:
                    logging.warning(f"Error processing article {article_url}: {str(e)}")
                    continue
                
                if len(articles) >= limit:
                    break
            
            return articles
        except Exception as e:
            error_msg = f"Error getting articles from {source_url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_trending_topics(
        self,
        sources: Optional[List[str]] = None,
        limit: int = 10,
        language: str = 'en'
    ) -> Union[List[str], Dict[str, str]]:
        """
        Get trending topics across news sources.
        
        Args:
            sources: List of source URLs to analyze
            limit: Maximum number of trending topics to return
            language: Language code
            
        Returns:
            List[str] or Dict: List of trending topics or error dict
        """
        try:
            from collections import Counter
            
            # Use default sources if none provided
            if not sources:
                sources_data = self.get_news_sources(language=language)
                if isinstance(sources_data, dict) and "error" in sources_data:
                    return sources_data
                sources = [s["url"] for s in sources_data[:5]]  # Use top 5 sources
            
            # Collect keywords from articles
            all_keywords = []
            for source_url in sources:
                try:
                    articles = self.get_articles_from_source(source_url, limit=5, language=language)
                    if isinstance(articles, list):
                        for article in articles:
                            if "keywords" in article:
                                all_keywords.extend(article["keywords"])
                except Exception as e:
                    logging.warning(f"Error processing source {source_url}: {str(e)}")
                    continue
            
            # Get most common keywords
            trending = Counter(all_keywords).most_common(limit)
            return [topic for topic, count in trending]
        except Exception as e:
            error_msg = f"Error getting trending topics: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

# Create instance for direct function access
_newspaper_tools = NewspaperTools()
get_article = _newspaper_tools.get_article
get_news_sources = _newspaper_tools.get_news_sources
get_articles_from_source = _newspaper_tools.get_articles_from_source
get_trending_topics = _newspaper_tools.get_trending_topics

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("NewspaperTools Demonstration")
    print("==================================================\n")
    
    # 1. Get news sources
    print("1. Getting News Sources")
    print("------------------------------")
    tech_sources = get_news_sources("technology")
    print("Technology news sources:")
    if isinstance(tech_sources, list):
        print(json.dumps(tech_sources[:3], indent=2))  # Show first 3 sources
    else:
        print(tech_sources)  # Show error
    print()
    
    if isinstance(tech_sources, list) and tech_sources:
        source_url = tech_sources[0]["url"]
        
        # 2. Get articles from a source
        print("2. Getting Articles from Source")
        print("------------------------------")
        articles = get_articles_from_source(source_url, limit=2)
        print(f"Articles from {source_url}:")
        if isinstance(articles, list):
            for article in articles:
                print(f"- {article['title']}")
                if "summary" in article:
                    print(f"  Summary: {article['summary'][:200]}...")
        else:
            print(articles)  # Show error
        print()
        
        # 3. Get a single article
        print("3. Getting Single Article")
        print("------------------------------")
        if isinstance(articles, list) and articles:
            article_url = articles[0]["url"]
            article = get_article(article_url)
            if "error" not in article:
                print(f"Article: {article['title']}")
                if "summary" in article:
                    print(f"Summary: {article['summary'][:200]}...")
                print(f"Authors: {', '.join(article['authors'])}")
                print(f"Date: {article['publish_date']}")
            else:
                print(article)  # Show error
        print()
        
        # 4. Get trending topics
        print("4. Getting Trending Topics")
        print("------------------------------")
        topics = get_trending_topics([source_url], limit=5)
        print("Trending topics:")
        print(json.dumps(topics, indent=2))
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
