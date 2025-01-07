from langchain_community.tools import YouTubeSearchTool
from langchain_community.utilities import WikipediaAPIWrapper

def test_tools():
    """Test both YouTube and Wikipedia tools"""
    
    print("\n=== Testing YouTube Search ===")
    # Test YouTube
    yt = YouTubeSearchTool()
    
    # Test basic search
    print("\nBasic YouTube Search:")
    query = "AI advancements 2024"
    print(f"Query: {query}")
    result = yt.run(query)
    print(f"Results: {result}")
    
    # Test with max results
    print("\nYouTube Search with max results:")
    query = "AI advancements 2024, 3"  # Format: query, max_results
    print(f"Query: {query}")
    result = yt.run(query)
    print(f"Results: {result}")
    
    print("\n=== Testing Wikipedia Search ===")
    # Test Wikipedia
    wiki = WikipediaAPIWrapper(
        top_k_results=2,
        doc_content_chars_max=500
    )
    
    # Test basic search
    print("\nBasic Wikipedia Search:")
    query = "Artificial Intelligence"
    print(f"Query: {query}")
    result = wiki.run(query)
    print(f"Results: {result[:200]}..." if result else "No result")
    
    # Test with different parameters
    print("\nWikipedia Search with different language:")
    wiki_fr = WikipediaAPIWrapper(
        lang='fr',
        top_k_results=1,
        doc_content_chars_max=300
    )
    result = wiki_fr.run("Intelligence Artificielle")
    print(f"French Results: {result[:200]}..." if result else "No result")

def print_tool_info():
    """Print detailed information about the tools"""
    
    print("\n=== Tool Information ===")
    
    # YouTube Tool Info
    print("\nYouTube Tool:")
    yt = YouTubeSearchTool()
    print("Type:", type(yt))
    print("Name:", getattr(yt, 'name', None))
    print("Description:", getattr(yt, 'description', None))
    print("Arguments:", getattr(yt, 'args', None))
    
    # Wikipedia Tool Info
    print("\nWikipedia Tool:")
    wiki = WikipediaAPIWrapper()
    print("Type:", type(wiki))
    print("Available Settings:")
    print("- Language:", wiki.lang)
    print("- Top K Results:", wiki.top_k_results)
    print("- Max Characters:", wiki.doc_content_chars_max)

if __name__ == "__main__":
    print_tool_info()
    test_tools() 