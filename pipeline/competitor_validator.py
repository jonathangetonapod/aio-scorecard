"""
Competitor Validator - Verify that detected competitors are legitimate

Checks:
1. Domain is accessible (not dead)
2. Website content matches the industry
3. Filters out irrelevant domains
"""

import asyncio
import httpx
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidatedCompetitor:
    """Validated competitor info"""
    domain: str
    mentions: int
    is_valid: bool = False
    is_relevant: bool = False
    company_name: str = ""
    description: str = ""
    validation_note: str = ""


# Domains to always exclude
EXCLUDED_DOMAINS = {
    # Search engines / AI
    'google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com',
    'openai.com', 'perplexity.ai', 'anthropic.com', 'chatgpt.com',
    
    # Social media
    'facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com',
    'youtube.com', 'tiktok.com', 'pinterest.com',
    
    # Generic directories / review sites
    'yelp.com', 'bbb.org', 'glassdoor.com', 'indeed.com',
    'yellowpages.com', 'manta.com', 'dnb.com', 'zoominfo.com',
    
    # News / media
    'forbes.com', 'businessinsider.com', 'bloomberg.com', 'reuters.com',
    'wikipedia.org', 'wikimedia.org',
    
    # E-commerce giants
    'amazon.com', 'ebay.com', 'alibaba.com', 'aliexpress.com',
    
    # Generic tech
    'github.com', 'stackoverflow.com', 'medium.com', 'wordpress.com',
    
    # Industry directories (not competitors)
    'thomasnet.com', 'globalspec.com', 'industrynet.com', 'kompass.com',
    'made-in-china.com', 'europages.com',
}


async def check_domain_accessible(domain: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Check if domain is accessible and get title"""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                f"https://{domain}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; research bot)"}
            )
            
            if response.status_code == 200:
                # Extract title
                html = response.text[:5000]
                import re
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else ""
                return True, title
            else:
                return False, f"HTTP {response.status_code}"
                
    except Exception as e:
        return False, str(e)[:50]


def check_industry_relevance(title: str, description: str, target_services: list) -> tuple[bool, str]:
    """Check if the company appears to be in a relevant industry"""
    text = f"{title} {description}".lower()
    
    # Industry keywords that indicate a manufacturing/engineering company
    relevant_keywords = [
        'manufactur', 'machin', 'fabricat', 'engineer', 'precision',
        'aerospace', 'automotive', 'medical', 'defense', 'industrial',
        'cnc', 'mill', 'turn', 'weld', 'assembly', 'prototype',
        'metal', 'plastic', 'component', 'part', 'tool', 'die',
        'iso', 'as9100', 'nadcap', 'itar',
        'production', 'custom', 'oem', 'supplier', 'vendor',
    ]
    
    # Check for target service keywords
    for service in target_services:
        if service.lower() in text:
            return True, f"Matches service: {service}"
    
    # Check for general industry keywords
    matches = [kw for kw in relevant_keywords if kw in text]
    if matches:
        return True, f"Industry keywords: {', '.join(matches[:3])}"
    
    return False, "No industry keywords found"


async def validate_competitor(
    domain: str,
    mentions: int,
    target_services: list = None
) -> ValidatedCompetitor:
    """Validate a single competitor"""
    
    result = ValidatedCompetitor(domain=domain, mentions=mentions)
    
    # Check excluded domains
    domain_clean = domain.lower().replace('www.', '')
    if domain_clean in EXCLUDED_DOMAINS:
        result.validation_note = "Excluded: not a competitor"
        return result
    
    # Check if domain is accessible
    is_accessible, title_or_error = await check_domain_accessible(domain)
    
    if not is_accessible:
        result.validation_note = f"Inaccessible: {title_or_error}"
        return result
    
    result.is_valid = True
    result.company_name = title_or_error[:100] if title_or_error else domain
    
    # Check industry relevance
    is_relevant, relevance_note = check_industry_relevance(
        title_or_error, "", target_services or []
    )
    
    result.is_relevant = is_relevant
    result.validation_note = relevance_note if is_relevant else "May not be in same industry"
    
    return result


async def validate_competitors(
    competitors: dict,  # domain -> mention count
    target_services: list = None,
    max_to_validate: int = 15,
    max_concurrent: int = 5
) -> list[ValidatedCompetitor]:
    """
    Validate multiple competitors in parallel.
    
    Returns list of ValidatedCompetitor sorted by mentions (valid first).
    """
    # Sort by mentions and take top N
    sorted_comps = sorted(competitors.items(), key=lambda x: -x[1])[:max_to_validate]
    
    # Validate in batches
    results = []
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def validate_with_semaphore(domain, mentions):
        async with semaphore:
            return await validate_competitor(domain, mentions, target_services)
    
    tasks = [
        validate_with_semaphore(domain, mentions)
        for domain, mentions in sorted_comps
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Sort: valid & relevant first, then valid, then invalid
    def sort_key(c):
        return (
            -int(c.is_valid and c.is_relevant),  # Valid + relevant first
            -int(c.is_valid),                      # Then just valid
            -c.mentions                            # Then by mentions
        )
    
    results.sort(key=sort_key)
    
    return results


async def test():
    """Test validation"""
    test_competitors = {
        'barber-nichols.com': 4,
        'boeing.com': 3,
        'lockheedmartin.com': 2,
        'google.com': 5,  # Should be excluded
        'notarealdomainxyz123.com': 2,  # Should fail
    }
    
    print("\n🔍 Testing Competitor Validation\n")
    
    results = await validate_competitors(
        test_competitors,
        target_services=['aerospace', 'engineering']
    )
    
    for r in results:
        status = "✓" if r.is_valid else "✗"
        relevant = "🎯" if r.is_relevant else "  "
        print(f"{status} {relevant} {r.domain} ({r.mentions}x)")
        print(f"      {r.validation_note}")
        if r.company_name and r.company_name != r.domain:
            print(f"      Name: {r.company_name[:50]}")
        print()


if __name__ == "__main__":
    asyncio.run(test())
