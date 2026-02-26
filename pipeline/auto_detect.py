"""
Auto-detect company info from domain

Uses web scraping to extract:
- Company name
- Industry vertical
- Location
"""

import re
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional


@dataclass
class CompanyInfo:
    """Detected company information"""
    domain: str
    company_name: str = ""
    vertical: str = ""
    location: str = ""
    description: str = ""
    services: list = None  # Specific services found
    detected: bool = False
    
    def __post_init__(self):
        if self.services is None:
            self.services = []


# Industry keywords for vertical detection (most specific first)
VERTICALS = {
    "precision CNC machining": ["cnc machin", "precision machin", "cnc mill", "cnc turn", "5-axis", "5 axis"],
    "CNC machining": ["cnc", "machining", "milling", "turning", "lathe", "swiss screw"],
    "injection molding": ["injection mold", "plastic mold", "tooling", "thermoplastic"],
    "metal stamping": ["metal stamp", "die stamp", "progressive die", "stamping"],
    "sheet metal fabrication": ["sheet metal", "metal fabricat", "laser cut", "brake form", "punching"],
    "metal fabrication": ["fabricat", "welding", "steel", "aluminum", "stainless"],
    "3D printing": ["3d print", "additive manufactur", "rapid prototype", "fdm", "sls", "sla", "dmls"],
    "PCB manufacturing": ["pcb", "circuit board", "printed circuit"],
    "electronics manufacturing": ["electronics manufactur", "ems", "electronic assembly", "smt"],
    "aerospace manufacturing": ["aerospace", "aviation", "aircraft", "as9100", "nadcap"],
    "medical device manufacturing": ["medical device", "iso 13485", "fda", "medical manufactur"],
    "automotive manufacturing": ["automotive", "iatf", "tier 1", "tier 2", "oem"],
    "tool and die": ["tool and die", "die making", "mold making", "toolmaker"],
    "powder coating": ["powder coat", "finishing", "anodiz", "plating", "surface finish"],
    "wire EDM": ["wire edm", "edm", "electrical discharge"],
    "waterjet cutting": ["waterjet", "water jet", "abrasive jet"],
    "laser cutting": ["laser cut", "fiber laser", "co2 laser"],
    "prototype manufacturing": ["prototype", "rapid prototype", "low volume", "quick turn"],
    "contract manufacturing": ["contract manufactur", "oem manufactur", "outsource manufactur"],
    "custom manufacturing": ["custom manufactur", "custom part", "made to order", "bespoke"],
    "precision engineering": ["precision engineer", "tight tolerance", "high precision"],
    "machine shop": ["machine shop", "job shop"],
    "general manufacturing": ["manufactur", "industrial", "production", "factory"],
}


def detect_vertical(text: str) -> tuple[str, list]:
    """Detect industry vertical and specific services from text"""
    text_lower = text.lower()
    
    scores = {}
    for vertical, keywords in VERTICALS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[vertical] = score
    
    # Also extract specific service keywords found
    service_keywords = [
        "cnc machining", "cnc milling", "cnc turning", "5-axis machining",
        "injection molding", "plastic molding",
        "sheet metal", "metal fabrication", "welding", "laser cutting",
        "3d printing", "additive manufacturing", "rapid prototyping",
        "pcb assembly", "electronics assembly",
        "powder coating", "anodizing", "plating",
        "wire edm", "waterjet cutting",
        "precision machining", "swiss machining",
        "tool and die", "stamping", "die casting",
        "prototype", "low volume production",
        "aerospace", "medical device", "automotive",
        "engineering", "design services", "assembly services"
    ]
    
    services_found = [s for s in service_keywords if s in text_lower]
    
    if scores:
        return max(scores, key=scores.get), services_found
    return "manufacturing", services_found


def extract_location(text: str) -> str:
    """Try to extract location from text"""
    # Common patterns
    patterns = [
        r'(?:located in|based in|headquarters in|serving)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,?\s*[A-Z]{2})',
        r'([A-Z][a-z]+,\s*[A-Z]{2}\s*\d{5})',  # City, ST 12345
        r'([A-Z][a-z]+,\s*[A-Z]{2})\b',  # City, ST
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return ""


def clean_company_name(name: str, domain: str) -> str:
    """Clean up company name"""
    # Remove common suffixes
    suffixes = [' LLC', ' Inc', ' Inc.', ' Corp', ' Corporation', ' Ltd', ' Co.', ' Company',
                ' | Home', ' - Home', ' – Home', ' | Official', ' - Official']
    
    result = name.strip()
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
    
    # If name is too long or looks like a tagline, use domain
    if len(result) > 50 or '|' in result or '-' in result:
        # Extract from domain
        domain_clean = domain.replace('www.', '').split('.')[0]
        # Title case
        result = domain_clean.replace('-', ' ').replace('_', ' ').title()
    
    return result.strip()


async def detect_from_domain(domain: str) -> CompanyInfo:
    """
    Auto-detect company info from domain.
    
    Fetches homepage and extracts:
    - Company name from title/meta
    - Industry vertical from content
    - Location if found
    """
    info = CompanyInfo(domain=domain)
    
    # Clean domain
    domain_clean = domain.lower().replace('https://', '').replace('http://', '').replace('www.', '')
    if '/' in domain_clean:
        domain_clean = domain_clean.split('/')[0]
    
    info.domain = domain_clean
    
    # Default company name from domain
    info.company_name = domain_clean.split('.')[0].replace('-', ' ').replace('_', ' ').title()
    
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                f"https://{domain_clean}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; research bot)"}
            )
            response.raise_for_status()
            html = response.text
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract title
            title = soup.find('title')
            if title and title.string:
                info.company_name = clean_company_name(title.string, domain_clean)
            
            # Extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                info.description = meta_desc['content'][:300]
            
            # Get page text for analysis
            # Remove script/style
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            page_text = soup.get_text(separator=' ', strip=True)[:5000]
            
            # Detect vertical and services
            combined_text = f"{info.company_name} {info.description} {page_text}"
            info.vertical, info.services = detect_vertical(combined_text)
            
            # Try to find location
            info.location = extract_location(page_text)
            
            info.detected = True
            
    except Exception as e:
        print(f"Detection error for {domain}: {e}")
        # Use defaults
        info.vertical = "manufacturing"
        info.services = []
    
    return info


async def test():
    """Test detection"""
    domains = [
        "xometry.com",
        "protolabs.com",
        "genesisengineeredsolutions.com"
    ]
    
    print("\n🔍 Testing Auto-Detection\n")
    
    for domain in domains:
        print(f"Detecting: {domain}")
        info = await detect_from_domain(domain)
        print(f"  Company: {info.company_name}")
        print(f"  Vertical: {info.vertical}")
        print(f"  Location: {info.location or 'Not found'}")
        print()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
