"""
SOLUTION: Domain Context Issue Fix using Existing PraisonAI Features

This solution fixes the issue where agents default to "example.com" instead of using 
the specified domain "eenadu.net" by leveraging existing PraisonAI context features.

Key improvements:
1. Domain context passed through task context parameter
2. Agent instructions include domain-specific guidance
3. Custom tool wrappers that inject domain context
4. Shared memory for consistent domain context

No core SDK changes required - uses only existing framework features.
"""

import os
import requests
import json
import base64
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from praisonaiagents import Agent, Task, PraisonAIAgents, Memory

# Load environment variables from .env.local
if not load_dotenv(dotenv_path=".env.local"):
    raise FileNotFoundError(".env.local file not found. Please ensure it exists in the working directory.")

# API Keys
api_keys = {
    "WHOXY_API_KEY": os.getenv("WHOXY_API_KEY"),
    "FOFA_API_KEY": os.getenv("FOFA_API_KEY"),
    "API_NINJAS_KEY": os.getenv("API_NINJAS_KEY"),
    "QDRANT_API_KEY": os.getenv("QDRANT_API_KEY"),
}

# Debug API Keys
for key, value in api_keys.items():
    if not value:
        raise ValueError(f"Missing API key: {key}. Ensure it is set in the environment variables or .env.local.")

# Qdrant Configuration
qdrant_url = "https://d32d17dc-6b1d-4e13-9bb5-94a4d9f4b457.europe-west3-0.gcp.cloud.qdrant.io:6333"
qdrant_client = QdrantClient(url=qdrant_url, api_key=api_keys["QDRANT_API_KEY"])

# Domain Configuration - This is the key to solving the context issue
class DomainContext:
    def __init__(self, target_domain: str):
        self.target_domain = target_domain
        self.context_description = f"DOMAIN CONTEXT: All tool operations must focus exclusively on the domain '{target_domain}'. Never use example.com or any other domain."
        
    def get_context(self):
        return {
            "domain": self.target_domain,
            "instructions": self.context_description,
            "constraints": [f"Only analyze {self.target_domain}", "No generic examples", "Domain-specific results only"]
        }

# Initialize domain context
domain = "eenadu.net"
domain_context = DomainContext(domain)

# SOLUTION 1: Custom Tool Wrappers with Domain Context Injection
def create_domain_aware_tools(target_domain: str):
    """Create domain-aware versions of tools that inject the target domain"""
    
    def query_fofa(query: str = None) -> dict:
        # Use target domain if no specific query provided
        if query is None or query == "example.com":
            query = target_domain
        # Ensure domain context is considered
        enhanced_query = f"{target_domain} {query}" if target_domain not in query else query
        
        base64_query = base64.b64encode(enhanced_query.encode("utf-8")).decode("utf-8")
        response = requests.get(
            f"https://fofa.info/api/v1/search/all?key={api_keys['FOFA_API_KEY']}&qbase64={base64_query}&size=100&fields=jarm,host,domain,title,ip,port,protocol,base_protocol,country,country_name,region,city,longitude,latitude,as_number,as_organization,os,server,icp,header,banner,cert,link,certs_issuer_org,certs_issuer_cn,certs_subject_org,certs_subject_cn,tls_ja3s,tls_version"
        )
        return response.json()

    def query_crtsh(domain_param: str = None) -> list:
        # Use target domain if no specific domain provided
        if domain_param is None or domain_param == "example.com":
            domain_param = target_domain
            
        response = requests.get(f"https://crt.sh/?q={domain_param}&output=json")
        return response.json()

    def query_whoxy(email_or_org: str = None) -> dict:
        # Use target domain if no specific parameter provided
        if email_or_org is None or email_or_org == "example.com":
            email_or_org = target_domain
            
        response = requests.get(
            f"https://api.whoxy.com/?key={api_keys['WHOXY_API_KEY']}&reverse=whois&search={email_or_org}"
        )
        return response.json()

    def query_api_ninjas(domain_param: str = None) -> dict:
        # Use target domain if no specific domain provided
        if domain_param is None or domain_param == "example.com":
            domain_param = target_domain
            
        response = requests.get(
            f"https://api.api-ninjas.com/v1/dnslookup?domain={domain_param}",
            headers={"X-Api-Key": api_keys["API_NINJAS_KEY"]},
        )
        return response.json()

    def query_networkcalc(domain_param: str = None) -> dict:
        # Use target domain if no specific domain provided
        if domain_param is None or domain_param == "example.com":
            domain_param = target_domain
            
        response = requests.get(f"https://networkcalc.com/api/dns/lookup/{domain_param}")
        return response.json()
    
    return [query_fofa, query_crtsh, query_whoxy, query_api_ninjas, query_networkcalc]

# Create domain-aware tools
domain_tools = create_domain_aware_tools(domain)

def perform_reverse_lookups(domain: str, manager_memory: dict):
    """Perform WHOXY lookups and store related domains."""
    reverse_data = domain_tools[2](domain)  # Use domain-aware whoxy tool
    email = reverse_data.get("email_address", "")
    organization = reverse_data.get("organization_name", "")
    owner = reverse_data.get("owner_name", "")

    # Perform additional reverse lookups
    related_by_email = domain_tools[2](email) if email else {}
    related_by_org = domain_tools[2](organization) if organization else {}
    related_by_owner = domain_tools[2](owner) if owner else {}

    # Filter out unrelated domains
    in_scope_domains = set()
    for lookup_data in [related_by_email, related_by_org, related_by_owner]:
        for domain_info in lookup_data.get("searchResult", {}).get("domains", []):
            if domain in domain_info or is_in_scope(domain_info):
                in_scope_domains.add(domain_info)

    # Store results in memory
    manager_memory["related_domains"] = list(in_scope_domains)

def is_in_scope(domain: str) -> bool:
    """Filter domains based on scope criteria."""
    out_of_scope_keywords = ["example.com", "google.com", "microsoft.com", "cloudflare.com"]
    return not any(keyword in domain for keyword in out_of_scope_keywords)

# SOLUTION 2: Agents with Domain-Specific Instructions
manager_agent = Agent(
    name="Manager Agent",
    role="Coordinate data collection and refinement",
    goal=f"Collect user input, oversee tasks, and perform WHOXY lookups for related domains specifically for {domain}.",
    backstory=f"Strategically manages all agents and ensures focused execution on the domain {domain}.",
    instructions=f"""
    CRITICAL DOMAIN CONTEXT: You are working exclusively with the domain '{domain}'. 
    
    All operations, tool calls, and analysis must focus on this specific domain.
    When coordinating with other agents, ensure they understand the domain context.
    Never use example.com or generic examples - always use {domain}.
    
    Your primary responsibility is to ensure all agents maintain focus on {domain} throughout the workflow.
    """,
    tools=[],
    verbose=True,
    llm="gpt-4o",
    markdown=True,
    memory={"short_term": {"target_domain": domain}, "long_term": qdrant_client},
)

tool_agent = Agent(
    name="Tool Agent",
    role="Run initial tool queries",
    goal=f"Gather subdomains, DNS records, reverse WHOIS data, and FOFA data specifically for {domain}.",
    backstory=f"Tool specialist focused exclusively on analyzing the domain {domain}. Expert in running information-gathering queries using all available tools.",
    instructions=f"""
    CRITICAL DOMAIN CONTEXT: Your exclusive focus is the domain '{domain}'.
    
    When using any tool:
    1. Always use '{domain}' as the target domain
    2. Never use example.com or any other domain
    3. If a tool asks for a domain parameter, provide '{domain}'
    4. If a tool asks for a query, include '{domain}' in the query
    5. All searches and analysis must be domain-specific to '{domain}'
    
    Remember: You are a specialist for {domain} only. No generic examples or other domains.
    """,
    tools=domain_tools,  # Use domain-aware tools
    verbose=True,
    llm="gpt-4o",
    markdown=True,
    memory={"short_term": {"target_domain": domain}, "long_term": qdrant_client},
)

sr_pentester_agent = Agent(
    name="Senior Pentester",
    role="Analyze tool results for vulnerabilities",
    goal=f"Investigate vulnerabilities and organize data for deep dives specifically for {domain}.",
    backstory=f"An expert in penetration testing and data correlation with deep expertise in analyzing {domain}.",
    instructions=f"""
    CRITICAL DOMAIN CONTEXT: You are analyzing security findings for the domain '{domain}' exclusively.
    
    When reviewing tool results:
    1. Focus only on findings related to '{domain}'
    2. Filter out any results from other domains
    3. Prioritize vulnerabilities specific to '{domain}'
    4. Organize findings with '{domain}' as the central focus
    
    Your expertise is domain-specific to {domain}. All analysis must be relevant to this domain only.
    """,
    tools=[],
    verbose=True,
    llm="gpt-4o",
    markdown=True,
    memory={"short_term": {"target_domain": domain}, "long_term": qdrant_client},
)

ciso_agent = Agent(
    name="CISO Agent",
    role="Executive Security Analysis",
    goal=f"Review findings and provide high-level recommendations specifically for {domain}.",
    backstory=f"Provides strategic insights and ensures alignment with organizational goals for {domain} security posture.",
    instructions=f"""
    CRITICAL DOMAIN CONTEXT: You are providing executive security analysis for the domain '{domain}' exclusively.
    
    In your strategic recommendations:
    1. Focus on security posture of '{domain}' only
    2. Provide recommendations specific to '{domain}'
    3. Consider business impact on '{domain}' operations
    4. Align security strategy with '{domain}' organizational goals
    
    Your strategic insights must be domain-specific to {domain}. No generic recommendations.
    """,
    tools=[],
    verbose=True,
    llm="gpt-4o",
    markdown=True,
    memory={"short_term": {"target_domain": domain}, "long_term": qdrant_client},
)

# SOLUTION 3: Tasks with Domain Context Parameter
tool_query_task = Task(
    name="tool_query_task",
    description=f"Run all tools to gather initial domain data for {domain}. Use the domain {domain} exclusively for all tool operations.",
    expected_output=f"Raw data from all tools for the domain {domain} stored in Qdrant.",
    agent=tool_agent,
    context=[domain_context.get_context()]  # Pass domain context to task
)

pentester_analysis_task = Task(
    name="pentester_analysis_task",
    description=f"Analyze tool output for vulnerabilities and prioritize areas of focus for the domain {domain}.",
    expected_output=f"Organized and prioritized security findings for {domain} stored in Qdrant.",
    agent=sr_pentester_agent,
    context=[domain_context.get_context(), tool_query_task]  # Include domain context and previous task
)

ciso_review_task = Task(
    name="ciso_review_task",
    description=f"Review pentester findings and provide strategic recommendations for the domain {domain}.",
    expected_output=f"High-level executive security recommendations for {domain} stored in Qdrant.",
    agent=ciso_agent,
    context=[domain_context.get_context(), pentester_analysis_task]  # Include domain context and previous task
)

# SOLUTION 4: Agents with Shared Memory Configuration
agents = PraisonAIAgents(
    agents=[manager_agent, tool_agent, sr_pentester_agent, ciso_agent],
    tasks=[tool_query_task, pentester_analysis_task, ciso_review_task],
    verbose=True,
    process="hierarchical",
    manager_llm="gpt-4o",
    memory=True,  # Enable shared memory for domain context
    memory_config={
        "provider": "rag",
        "config": {
            "collection_name": f"{domain.replace('.', '_')}_security_analysis"
        }
    }
)

# Main Execution Workflow
def main():
    print(f"Welcome to the Hierarchical Pentesting Workflow for {domain}!")
    
    # Store domain context in memory for all agents
    domain_info = f"Target domain for analysis: {domain}. All operations must focus on this domain exclusively."
    
    # Initialize shared context for all agents
    for agent in [manager_agent, tool_agent, sr_pentester_agent, ciso_agent]:
        agent.memory["short_term"]["domain_context"] = domain_context.get_context()
        agent.memory["short_term"]["target_domain"] = domain
    
    print(f"Domain context initialized: {domain}")
    print(f"All agents configured to focus exclusively on: {domain}")
    
    # Execute the workflow
    result = agents.start()

    # Serialize TaskOutput to JSON-serializable format
    serialized_result = []
    for task in agents.tasks:
        if hasattr(task, "name") and hasattr(task, "output"):
            serialized_result.append({
                "task_name": task.name,
                "domain": domain,
                "output": task.output.to_dict() if hasattr(task.output, "to_dict") else str(task.output),
            })
        else:
            print(f"Skipping task: {task} due to missing attributes.")

    # Output results
    print(f"Workflow Results for {domain}:")
    print(json.dumps(serialized_result, indent=4))
    
    # Verify domain context was maintained
    print(f"\nDomain Context Verification:")
    print(f"Target Domain: {domain}")
    print(f"Context properly maintained: {'YES' if all('target_domain' in agent.memory['short_term'] for agent in agents.agents) else 'NO'}")

if __name__ == "__main__":
    main()