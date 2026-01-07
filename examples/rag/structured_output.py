"""
Structured Output RAG: Guided and Constrained Generation

This example demonstrates how to guide RAG output into specific formats
and structures using Pydantic models and output constraints.

RAG Concept: Sometimes you need RAG answers in a specific format - JSON,
tables, or structured data. Guided generation ensures the LLM output
conforms to your schema.
"""

from typing import List
from pydantic import BaseModel, Field
from praisonaiagents import Agent

# Sample knowledge base: Product catalog
PRODUCT_CATALOG = [
    {
        "id": "prod_001",
        "content": """
        Product: UltraWidget Pro
        Category: Electronics
        Price: $299.99
        Rating: 4.5/5 (1,250 reviews)
        Features: Wireless connectivity, 12-hour battery, water-resistant
        Availability: In stock
        SKU: UW-PRO-2024
        """
    },
    {
        "id": "prod_002",
        "content": """
        Product: SmartHome Hub
        Category: Home Automation
        Price: $149.99
        Rating: 4.2/5 (890 reviews)
        Features: Voice control, 100+ device compatibility, energy monitoring
        Availability: In stock
        SKU: SH-HUB-2024
        """
    },
    {
        "id": "prod_003",
        "content": """
        Product: ErgoDesk Standing Desk
        Category: Furniture
        Price: $599.99
        Rating: 4.8/5 (2,100 reviews)
        Features: Electric height adjustment, memory presets, cable management
        Availability: Ships in 3-5 days
        SKU: ED-STAND-2024
        """
    },
    {
        "id": "prod_004",
        "content": """
        Product: CloudSync Backup Drive
        Category: Storage
        Price: $199.99
        Rating: 4.6/5 (1,800 reviews)
        Features: 4TB capacity, automatic backup, encrypted storage
        Availability: In stock
        SKU: CS-4TB-2024
        """
    }
]


# Pydantic models for structured output
class ProductInfo(BaseModel):
    """Structured product information."""
    name: str = Field(description="Product name")
    price: float = Field(description="Price in USD")
    rating: float = Field(description="Rating out of 5")
    in_stock: bool = Field(description="Whether product is in stock")
    key_features: List[str] = Field(description="Top 3 features")


class ProductComparison(BaseModel):
    """Structured comparison of products."""
    products: List[str] = Field(description="Names of compared products")
    winner: str = Field(description="Recommended product")
    reason: str = Field(description="Why this product is recommended")
    price_range: str = Field(description="Price range of compared products")


class SearchResult(BaseModel):
    """Structured search result."""
    query: str = Field(description="Original search query")
    matches: List[str] = Field(description="Matching product names")
    total_found: int = Field(description="Number of matches")
    summary: str = Field(description="Brief summary of results")


def json_output_rag():
    """Demonstrate RAG with JSON-structured output."""
    
    print("=" * 60)
    print("JSON-STRUCTURED RAG OUTPUT")
    print("=" * 60)
    
    agent = Agent(
        name="Product Assistant",
        instructions="""You are a product assistant that provides structured information.
        Always respond with valid JSON matching the requested format.
        Extract accurate information from the product catalog.""",
        knowledge=PRODUCT_CATALOG,
        user_id="json_demo"
    )
    
    # Request structured product info
    query = """
    Tell me about the UltraWidget Pro. Respond in this JSON format:
    {
        "name": "product name",
        "price": 0.00,
        "rating": 0.0,
        "in_stock": true/false,
        "key_features": ["feature1", "feature2", "feature3"]
    }
    """
    
    print("\n📝 Query: Get structured product info")
    response = agent.chat(query)
    print("💡 Structured Response:\n" + str(response))
    print("-" * 40)


def pydantic_guided_rag():
    """Demonstrate RAG with Pydantic model guidance."""
    
    print("\n" + "=" * 60)
    print("PYDANTIC-GUIDED RAG")
    print("=" * 60)
    
    # Generate schema from Pydantic model
    schema = ProductComparison.model_json_schema()
    
    agent = Agent(
        name="Product Comparator",
        instructions=f"""You compare products and provide structured recommendations.
        Your response MUST be valid JSON matching this schema:
        {schema}
        
        Be objective and base recommendations on the product data.""",
        knowledge=PRODUCT_CATALOG,
        user_id="pydantic_demo"
    )
    
    query = "Compare the UltraWidget Pro and SmartHome Hub. Which should I buy?"
    
    print(f"\n📝 Query: {query}")
    print("📋 Expected Schema: ProductComparison")
    
    response = agent.chat(query)
    print(f"\n💡 Structured Comparison:\n{response}")


def table_format_rag():
    """Demonstrate RAG with table-formatted output."""
    
    print("\n" + "=" * 60)
    print("TABLE-FORMATTED RAG")
    print("=" * 60)
    
    agent = Agent(
        name="Catalog Browser",
        instructions="""You present product information in clean table format.
        Use markdown tables for structured data.
        Include relevant columns based on the query.""",
        knowledge=PRODUCT_CATALOG,
        user_id="table_demo"
    )
    
    query = "Show me all products in a table with name, price, and rating."
    
    print(f"\n📝 Query: {query}")
    response = agent.chat(query)
    print(f"\n💡 Table Output:\n{response}")


def list_format_rag():
    """Demonstrate RAG with list-formatted output."""
    
    print("\n" + "=" * 60)
    print("LIST-FORMATTED RAG")
    print("=" * 60)
    
    agent = Agent(
        name="Feature Lister",
        instructions="""You extract and present information as organized lists.
        Use bullet points and numbered lists appropriately.
        Group related items together.""",
        knowledge=PRODUCT_CATALOG,
        user_id="list_demo"
    )
    
    queries = [
        "List all product features across the catalog",
        "What are the top-rated products? List them in order."
    ]
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 List Output:\n{response[:400]}..." if len(str(response)) > 400 else f"💡 List Output:\n{response}")
        print("-" * 40)


def constrained_generation():
    """Demonstrate constrained/guided generation patterns."""
    
    print("\n" + "=" * 60)
    print("CONSTRAINED GENERATION PATTERNS")
    print("=" * 60)
    
    print("""
    🎯 Constrained Generation Techniques:
    
    1. **Schema Enforcement**
       - Provide JSON schema in instructions
       - Agent outputs valid JSON matching schema
       ```python
       instructions = f"Respond with JSON matching: {schema}"
       ```
    
    2. **Format Templates**
       - Give explicit output templates
       - Agent fills in the blanks
       ```python
       instructions = '''
       Respond in this format:
       PRODUCT: [name]
       PRICE: $[amount]
       VERDICT: [recommendation]
       '''
       ```
    
    3. **Pydantic Validation**
       - Parse agent output with Pydantic
       - Retry if validation fails
       ```python
       response = agent.chat(query)
       try:
           result = ProductInfo.model_validate_json(response)
       except ValidationError:
           # Retry with clarification
       ```
    
    4. **Output Parsers**
       - Post-process agent output
       - Extract structured data from text
       ```python
       def parse_product(text: str) -> dict:
           # Extract price, rating, etc.
           return structured_data
       ```
    
    5. **Few-Shot Examples**
       - Show examples of desired output format
       - Agent learns pattern from examples
       ```python
       instructions = '''
       Example:
       Q: Tell me about Product X
       A: {"name": "Product X", "price": 99.99}
       
       Now answer the user's question in the same format.
       '''
       ```
    """)


def multi_format_rag():
    """Demonstrate switching between output formats."""
    
    print("\n" + "=" * 60)
    print("MULTI-FORMAT RAG")
    print("=" * 60)
    
    base_knowledge = PRODUCT_CATALOG
    query = "Tell me about the ErgoDesk Standing Desk"
    
    formats = [
        ("JSON", "Respond with a JSON object containing name, price, and features."),
        ("Markdown", "Respond with a markdown-formatted product card with headers."),
        ("Plain Text", "Respond with a brief, conversational product description."),
        ("Bullet Points", "Respond with bullet points covering key product details.")
    ]
    
    print(f"\n📝 Base Query: {query}")
    print("\n🔄 Same query, different output formats:\n")
    
    for format_name, format_instruction in formats:
        agent = Agent(
            name=f"{format_name} Agent",
            instructions=f"You are a product expert. {format_instruction}",
            knowledge=base_knowledge,
            user_id=f"format_{format_name.lower()}"
        )
        
        response = agent.chat(query)
        print(f"📋 {format_name} Format:")
        print(f"{response[:250]}..." if len(str(response)) > 250 else response)
        print("-" * 40)


def main():
    """Run all structured output RAG examples."""
    print("\n🚀 PraisonAI Structured Output RAG Examples\n")
    
    # Example 1: JSON output
    json_output_rag()
    
    # Example 2: Pydantic-guided
    pydantic_guided_rag()
    
    # Example 3: Table format
    table_format_rag()
    
    # Example 4: List format
    list_format_rag()
    
    # Example 5: Constrained generation patterns
    constrained_generation()
    
    # Example 6: Multi-format
    multi_format_rag()
    
    print("\n✅ Structured output RAG examples completed!")


if __name__ == "__main__":
    main()
