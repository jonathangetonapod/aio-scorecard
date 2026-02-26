"""
AI Visibility Checker - Query multiple AI chatbots to check domain mentions

Uses:
- Perplexity API (sonar model with web search)
- OpenAI ChatGPT (gpt-4o-mini with web browsing context)
"""

import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional
import httpx


@dataclass
class AIResponse:
    """Single AI response"""
    platform: str  # 'perplexity' or 'chatgpt'
    query: str
    query_type: str = ""  # 'research', 'compare', 'quote', 'urgent'
    service: str = ""  # which service this query is about
    location_type: str = ""  # 'local' or 'national'
    response: str = ""
    response_snippet: str = ""  # First 300 chars for display
    mentions_target: bool = False
    competitors_found: list = field(default_factory=list)


@dataclass
class VisibilityReport:
    """Full visibility report"""
    domain: str
    company_name: str
    vertical: str
    location: str
    
    # Scores
    total_queries: int = 0
    total_mentions: int = 0
    visibility_score: float = 0.0
    
    # By platform
    perplexity_queries: int = 0
    perplexity_mentions: int = 0
    chatgpt_queries: int = 0
    chatgpt_mentions: int = 0
    
    # Competitors
    competitors: dict = field(default_factory=dict)  # domain -> mention count
    
    # Raw responses
    responses: list = field(default_factory=list)


def extract_domains(text: str) -> list[str]:
    """Extract domain names from text"""
    pattern = r'\b(?:https?://)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)\b'
    matches = re.findall(pattern, text.lower())
    
    # Filter out common non-company domains
    ignore = {'google.com', 'youtube.com', 'facebook.com', 'twitter.com', 'linkedin.com',
              'instagram.com', 'wikipedia.org', 'amazon.com', 'reddit.com', 'yelp.com',
              'bbb.org', 'glassdoor.com', 'indeed.com', 'craigslist.org', 'forbes.com',
              'businessinsider.com', 'thomasnet.com', 'dnb.com', 'zoominfo.com',
              'openai.com', 'perplexity.ai', 'chatgpt.com'}
    
    return [d for d in set(matches) if d not in ignore and len(d) > 4]


def check_domain_mentioned(text: str, domain: str) -> bool:
    """Check if domain or company appears in text"""
    text_lower = text.lower()
    domain_clean = domain.lower().replace('www.', '')
    
    # Check full domain
    if domain_clean in text_lower:
        return True
    
    # Check domain without TLD
    domain_name = domain_clean.split('.')[0]
    if len(domain_name) > 3 and domain_name in text_lower:
        return True
    
    return False


class AIChecker:
    """Query AI chatbots and check for domain visibility"""
    
    def __init__(self, perplexity_key: str = None, openai_key: str = None):
        self.perplexity_key = perplexity_key
        self.openai_key = openai_key
        
        if not perplexity_key and not openai_key:
            raise ValueError("At least one API key required (Perplexity or OpenAI)")
    
    async def query_perplexity(self, prompt: str) -> str:
        """Query Perplexity API with web search"""
        if not self.perplexity_key:
            return ""
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.perplexity_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {
                                "role": "system", 
                                "content": "You are a helpful business research assistant. When recommending companies, always include their website domains. Be specific and mention actual company names and websites."
                            },
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 1000,
                        "temperature": 0.3
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            print(f"Perplexity error: {e}")
            return ""
    
    async def query_chatgpt(self, prompt: str) -> str:
        """Query OpenAI ChatGPT"""
        if not self.openai_key:
            return ""
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-5.2-2025-12-11",
                        "messages": [
                            {
                                "role": "system", 
                                "content": "You are a helpful business research assistant. When recommending companies, always include their website domains. Be specific and mention actual company names and their websites."
                            },
                            {"role": "user", "content": prompt}
                        ],
                        "max_completion_tokens": 1000,
                        "temperature": 0.3
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            print(f"ChatGPT error: {e}")
            return ""
    
    async def check_visibility(
        self,
        domain: str,
        company_name: str,
        vertical: str,
        location: str = "",
        services: list = None
    ) -> VisibilityReport:
        """
        Check AI visibility for a domain across multiple platforms.
        """
        report = VisibilityReport(
            domain=domain,
            company_name=company_name,
            vertical=vertical,
            location=location
        )
        
        # Build queries - for EACH service keyword, multiple intent types
        
        # Collect all terms to query: services + vertical (deduplicated)
        # Limit to 2 terms max for speed (keeps analysis under 1 min)
        all_terms = []
        if services:
            all_terms.extend(services[:2])  # Up to 2 detected services
        if vertical and vertical.lower() not in [s.lower() for s in all_terms] and len(all_terms) < 2:
            all_terms.append(vertical)
        
        # Ensure we have at least one term
        if not all_terms:
            all_terms = ["manufacturing"]
        
        # Build queries based on whether we have location
        queries = []  # List of (query_text, service, intent_type, location_type)
        
        for term in all_terms:
            if location:
                # Location-specific queries - what real customers would ask
                queries.extend([
                    (f"What are the best {term} companies in {location}? Please include their websites.", term, 'research', 'local'),
                    (f"Who are the top {term} companies near {location}? Include websites.", term, 'research', 'local'),
                    (f"I need a quote for {term} services in {location}. Who should I contact?", term, 'quote', 'local'),
                ])
            else:
                # National queries only when no location
                queries.extend([
                    (f"What are the best {term} companies? Please include their websites.", term, 'research', 'national'),
                    (f"Who are the top {term} companies in the United States? Include websites.", term, 'research', 'national'),
                    (f"I need a quote for {term} services. Who should I contact?", term, 'quote', 'national'),
                ])
        
        # Skip urgent/compare for now to keep analysis fast
        # (Can re-enable later if needed)
        
        domain_clean = domain.lower().replace('www.', '')
        
        for query_text, service, intent_type, loc_type in queries:
            # Query Perplexity
            if self.perplexity_key:
                print(f"  → Perplexity [{intent_type}]: {query_text[:50]}...")
                response = await self.query_perplexity(query_text)
                
                if response:
                    report.perplexity_queries += 1
                    report.total_queries += 1
                    
                    mentioned = check_domain_mentioned(response, domain)
                    if mentioned:
                        report.perplexity_mentions += 1
                        report.total_mentions += 1
                    
                    # Extract competitors
                    competitors_in_response = []
                    for d in extract_domains(response):
                        if d != domain_clean and domain_clean.split('.')[0] not in d:
                            report.competitors[d] = report.competitors.get(d, 0) + 1
                            competitors_in_response.append(d)
                    
                    # Create snippet (first 400 chars, clean up)
                    snippet = response[:400].strip()
                    if len(response) > 400:
                        snippet = snippet.rsplit(' ', 1)[0] + '...'
                    
                    report.responses.append(AIResponse(
                        platform='perplexity',
                        query=query_text,
                        query_type=intent_type,
                        service=service,
                        location_type=loc_type,
                        response=response,
                        response_snippet=snippet,
                        mentions_target=mentioned,
                        competitors_found=competitors_in_response[:5]
                    ))
                
                await asyncio.sleep(0.3)
            
            # Query ChatGPT
            if self.openai_key:
                print(f"  → GPT-5 [{intent_type}]: {query_text[:50]}...")
                response = await self.query_chatgpt(query_text)
                
                if response:
                    report.chatgpt_queries += 1
                    report.total_queries += 1
                    
                    mentioned = check_domain_mentioned(response, domain)
                    if mentioned:
                        report.chatgpt_mentions += 1
                        report.total_mentions += 1
                    
                    # Extract competitors
                    competitors_in_response = []
                    for d in extract_domains(response):
                        if d != domain_clean and domain_clean.split('.')[0] not in d:
                            report.competitors[d] = report.competitors.get(d, 0) + 1
                            competitors_in_response.append(d)
                    
                    # Create snippet
                    snippet = response[:400].strip()
                    if len(response) > 400:
                        snippet = snippet.rsplit(' ', 1)[0] + '...'
                    
                    report.responses.append(AIResponse(
                        platform='chatgpt',
                        query=query_text,
                        query_type=intent_type,
                        service=service,
                        location_type=loc_type,
                        response=response,
                        response_snippet=snippet,
                        mentions_target=mentioned,
                        competitors_found=competitors_in_response[:5]
                    ))
                
                await asyncio.sleep(0.3)
        
        # Calculate visibility score
        if report.total_queries > 0:
            report.visibility_score = (report.total_mentions / report.total_queries) * 100
        
        return report


async def test():
    """Quick test"""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    checker = AIChecker(
        perplexity_key=os.getenv('PERPLEXITY_API_KEY'),
        openai_key=os.getenv('OPENAI_API_KEY')
    )
    
    print("\n🔍 Testing AI Visibility Checker (Perplexity + ChatGPT)\n")
    
    report = await checker.check_visibility(
        domain="xometry.com",
        company_name="Xometry",
        vertical="CNC machining",
        location="Denver, CO"
    )
    
    print(f"\n{'='*50}")
    print(f"📊 VISIBILITY REPORT: {report.domain}")
    print(f"{'='*50}")
    print(f"\nTotal Queries: {report.total_queries}")
    print(f"Total Mentions: {report.total_mentions}")
    print(f"Score: {report.visibility_score:.0f}%")
    print(f"\nBy Platform:")
    print(f"  Perplexity: {report.perplexity_mentions}/{report.perplexity_queries}")
    print(f"  ChatGPT: {report.chatgpt_mentions}/{report.chatgpt_queries}")
    print(f"\nTop Competitors:")
    sorted_comps = sorted(report.competitors.items(), key=lambda x: -x[1])[:10]
    for domain, count in sorted_comps:
        print(f"  • {domain}: {count} mentions")


if __name__ == "__main__":
    asyncio.run(test())
