"""
AI Visibility Checker v2 - Vertical-Based Queries

Queries AI chatbots using specific manufacturing keywords instead of location.

Uses:
- Perplexity API (sonar model with web search)
- OpenAI ChatGPT (gpt-5)
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
    query_type: str = ""  # 'research', 'compare', 'quote', 'supplier'
    keyword: str = ""  # which keyword this query is about
    response: str = ""
    response_snippet: str = ""  # First 400 chars for display
    mentions_target: bool = False
    competitors_found: list = field(default_factory=list)


@dataclass
class VisibilityReport:
    """Full visibility report"""
    domain: str
    company_name: str
    vertical: str
    primary_keyword: str = ""
    keywords: list = field(default_factory=list)
    location: str = ""  # Optional, kept for reference
    
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


# Query templates - What B2B buyers ACTUALLY ask AI
QUERY_TEMPLATES = {
    "research": [
        "What companies offer {keyword} services?",
        "Who are the best {keyword} manufacturers in the US?",
        "List {keyword} companies I should consider for a project",
        "Recommend {keyword} suppliers with good reputation",
    ],
    "quote": [
        "I need {keyword} for a project - which companies should I get quotes from?",
        "Who can I contact for {keyword} manufacturing quotes?",
    ],
    "supplier": [
        "Best {keyword} suppliers for {vertical} applications",
        "Which companies specialize in {keyword}?",
        "Top rated {keyword} manufacturers",
    ],
    "compare": [
        "Compare the top {keyword} companies - who is best?",
        "What are the differences between {keyword} manufacturers?",
    ],
}


def extract_domains(text: str) -> list[str]:
    """Extract domain names from text"""
    pattern = r'\b(?:https?://)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)\b'
    matches = re.findall(pattern, text.lower())
    
    # Filter out common non-company domains
    ignore = {'google.com', 'youtube.com', 'facebook.com', 'twitter.com', 'linkedin.com',
              'instagram.com', 'wikipedia.org', 'amazon.com', 'reddit.com', 'yelp.com',
              'bbb.org', 'glassdoor.com', 'indeed.com', 'craigslist.org', 'forbes.com',
              'businessinsider.com', 'thomasnet.com', 'dnb.com', 'zoominfo.com',
              'openai.com', 'perplexity.ai', 'chatgpt.com', 'github.com', 'medium.com',
              'shopify.com', 'wordpress.com', 'wix.com', 'squarespace.com'}
    
    return [d for d in set(matches) if d not in ignore and len(d) > 4]


def check_domain_mentioned(text: str, domain: str, company_name: str = "") -> bool:
    """Check if domain or company appears in text - with fuzzy matching"""
    text_lower = text.lower()
    domain_clean = domain.lower().replace('www.', '')

    # Check full domain
    if domain_clean in text_lower:
        return True

    # Check domain without TLD (word boundary to avoid partial matches)
    domain_name = domain_clean.split('.')[0]
    if len(domain_name) > 3 and re.search(r'\b' + re.escape(domain_name) + r'\b', text_lower):
        return True

    # Check company name if provided (with variations)
    if company_name and len(company_name) > 3:
        company_lower = company_name.lower()

        # Direct match (word boundary)
        if re.search(r'\b' + re.escape(company_lower) + r'\b', text_lower):
            return True

        # Try without common suffixes
        for suffix in [' inc', ' llc', ' corp', ' ltd', ' co', ' company', ' manufacturing', ' mfg']:
            if company_lower.endswith(suffix):
                base_name = company_lower[:-len(suffix)].strip()
                if len(base_name) > 3 and re.search(r'\b' + re.escape(base_name) + r'\b', text_lower):
                    return True

        # Try with spaces removed (e.g., "Proto Labs" vs "Protolabs")
        no_space = company_lower.replace(' ', '')
        if len(no_space) > 4 and no_space in text_lower.replace(' ', ''):
            return True

    return False


class AIChecker:
    """Query AI chatbots and check for domain visibility"""

    def __init__(self, perplexity_key: str = None, openai_key: str = None):
        self.perplexity_key = perplexity_key
        self.openai_key = openai_key

        if not perplexity_key and not openai_key:
            raise ValueError("At least one API key required (Perplexity or OpenAI)")

    async def verify_mention_with_llm(self, response_text: str, company_name: str, domain: str) -> bool:
        """Use a fast LLM to verify if the company is actually mentioned/recommended."""
        if not self.openai_key:
            # Fall back to regex if no OpenAI key
            return check_domain_mentioned(response_text, domain, company_name)

        domain_clean = domain.lower().replace('www.', '')
        prompt = f"""I need you to check if a SPECIFIC company is mentioned in this text.

Company to find: "{company_name}"
Domain to find: "{domain_clean}"

Rules:
- Answer YES ONLY if you see the EXACT company name "{company_name}" or the EXACT domain "{domain_clean}" in the text
- Similar-sounding companies are NOT matches. For example:
  "Window World" is NOT "{company_name}"
  "Windows Direct USA" is NOT "{company_name}"
  "windowworld.com" is NOT "{domain_clean}"
- Partial matches do NOT count. The company name or domain must appear as written above.

Text to search:
\"\"\"
{response_text[:2000]}
\"\"\"

Is "{company_name}" or "{domain_clean}" explicitly written in the text above? YES or NO only."""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-5-mini-2025-08-07",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 5,
                        "temperature": 0
                    }
                )
                if resp.status_code != 200:
                    return check_domain_mentioned(response_text, domain, company_name)

                answer = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
                return answer.startswith("YES")
        except Exception as e:
            print(f"    ⚠ LLM verification failed ({type(e).__name__}), falling back to regex")
            return check_domain_mentioned(response_text, domain, company_name)
    
    async def query_perplexity(self, prompt: str, retries: int = 2) -> str:
        """Query Perplexity API with web search"""
        if not self.perplexity_key:
            return ""
        
        for attempt in range(retries + 1):
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
                                    "content": "You are a helpful manufacturing industry research assistant. When recommending companies, always include their website domains. Be specific and mention actual company names and websites. Focus on US-based manufacturers."
                                },
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": 1000,
                            "temperature": 0.3
                        }
                    )
                    
                    if response.status_code == 429:  # Rate limit
                        if attempt < retries:
                            wait = (attempt + 1) * 2
                            print(f"    ⏳ Perplexity rate limit, waiting {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        print(f"    ⚠ Perplexity rate limited (try again later)")
                        return ""
                    
                    if response.status_code == 401:
                        print(f"    ⚠ Perplexity: Invalid API key")
                        self.perplexity_key = None  # Disable further attempts
                        return ""
                    
                    response.raise_for_status()
                    data = response.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
            except httpx.TimeoutException:
                print(f"    ⚠ Perplexity timeout")
                return ""
            except Exception as e:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                print(f"    ⚠ Perplexity error: {type(e).__name__}")
                return ""
        return ""
    
    async def query_chatgpt(self, prompt: str, retries: int = 2) -> str:
        """Query OpenAI o3-mini (reasoning model)"""
        if not self.openai_key:
            return ""
        
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openai_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "o3-mini",
                            "messages": [
                                {
                                    "role": "system", 
                                    "content": "You are a helpful manufacturing industry research assistant. When recommending companies, always include their website domains. Be specific and mention actual company names and their websites. Focus on US-based manufacturers."
                                },
                                {"role": "user", "content": prompt}
                            ],
                            "max_completion_tokens": 4000
                        }
                    )
                    
                    if response.status_code == 429:  # Rate limit
                        if attempt < retries:
                            wait = (attempt + 1) * 3  # Longer wait for OpenAI
                            print(f"    ⏳ OpenAI rate limit, waiting {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        print(f"    ⚠ OpenAI rate limited")
                        return ""
                    
                    if response.status_code == 401:
                        print(f"    ⚠ OpenAI: Invalid API key")
                        self.openai_key = None
                        return ""
                    
                    response.raise_for_status()
                    data = response.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
            except httpx.TimeoutException:
                print(f"    ⚠ OpenAI timeout (reasoning models are slow)")
                return ""
            except Exception as e:
                if attempt < retries:
                    await asyncio.sleep(2)
                    continue
                print(f"    ⚠ OpenAI error: {type(e).__name__}")
                return ""
        return ""
    
    def build_queries(
        self,
        primary_keyword: str,
        keywords: list,
        vertical: str
    ) -> list[tuple[str, str, str]]:
        """
        Build query list based on keywords.
        Returns list of (query_text, keyword, query_type).
        """
        queries = []
        
        # Primary keyword gets all query types
        for query_type, templates in QUERY_TEMPLATES.items():
            for template in templates[:2]:  # Max 2 per type
                query = template.format(
                    keyword=primary_keyword,
                    vertical=vertical
                )
                queries.append((query, primary_keyword, query_type))
        
        # Secondary keywords get research queries only (to keep costs down)
        for kw in keywords[:2]:  # Max 2 secondary keywords
            if kw != primary_keyword:
                query = QUERY_TEMPLATES["research"][0].format(
                    keyword=kw,
                    vertical=vertical
                )
                queries.append((query, kw, "research"))
        
        return queries
    
    async def check_visibility(
        self,
        domain: str,
        company_name: str,
        vertical: str,
        primary_keyword: str = "",
        keywords: list = None,
        location: str = "",  # Optional, kept for reference
        services: list = None  # Legacy compatibility
    ) -> VisibilityReport:
        """
        Check AI visibility for a domain using vertical-based queries.
        """
        # Handle legacy 'services' parameter
        if keywords is None and services:
            keywords = services
        keywords = keywords or []
        
        # If no primary keyword, use first keyword or vertical
        if not primary_keyword:
            primary_keyword = keywords[0] if keywords else vertical
        
        report = VisibilityReport(
            domain=domain,
            company_name=company_name,
            vertical=vertical,
            primary_keyword=primary_keyword,
            keywords=keywords,
            location=location
        )
        
        # Build queries
        queries = self.build_queries(primary_keyword, keywords, vertical)
        
        if not queries:
            print("  ⚠ No queries to run")
            return report
        
        domain_clean = domain.lower().replace('www.', '')
        
        print(f"  📊 Running {len(queries)} queries across platforms...")
        
        for query_text, keyword, query_type in queries:
            # Query Perplexity
            if self.perplexity_key:
                print(f"    → Perplexity [{query_type}]: {keyword}")
                response = await self.query_perplexity(query_text)
                
                if response:
                    report.perplexity_queries += 1
                    report.total_queries += 1

                    mentioned = await self.verify_mention_with_llm(response, company_name, domain)
                    if mentioned:
                        report.perplexity_mentions += 1
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
                        platform='perplexity',
                        query=query_text,
                        query_type=query_type,
                        keyword=keyword,
                        response=response,
                        response_snippet=snippet,
                        mentions_target=mentioned,
                        competitors_found=competitors_in_response[:5]
                    ))

                await asyncio.sleep(0.3)

            # Query ChatGPT
            if self.openai_key:
                print(f"    → GPT [{query_type}]: {keyword}")
                response = await self.query_chatgpt(query_text)

                if response:
                    report.chatgpt_queries += 1
                    report.total_queries += 1

                    mentioned = await self.verify_mention_with_llm(response, company_name, domain)
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
                        query_type=query_type,
                        keyword=keyword,
                        response=response,
                        response_snippet=snippet,
                        mentions_target=mentioned,
                        competitors_found=competitors_in_response[:5]
                    ))

                await asyncio.sleep(0.3)
        
        # Calculate visibility score
        if report.total_queries > 0:
            report.visibility_score = (report.total_mentions / report.total_queries) * 100
        
        print(f"  ✓ Complete: {report.total_mentions}/{report.total_queries} mentions ({report.visibility_score:.0f}%)")
        
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
    
    print("\n🔍 Testing Vertical-Based AI Visibility Checker (v2)\n")
    print("="*60)
    
    report = await checker.check_visibility(
        domain="xometry.com",
        company_name="Xometry",
        vertical="CNC Machining",
        primary_keyword="cnc machining",
        keywords=["cnc machining", "3d printing", "injection molding"]
    )
    
    print(f"\n{'='*60}")
    print(f"📊 VISIBILITY REPORT: {report.domain}")
    print(f"{'='*60}")
    print(f"\nPrimary Keyword: {report.primary_keyword}")
    print(f"Vertical: {report.vertical}")
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
