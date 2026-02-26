"""
Auto-detect company info from domain

Enhanced v2: Uses LLM to intelligently extract manufacturing keywords.

Flow:
1. Scrape website homepage
2. Pass content to GPT-4o-mini for intelligent extraction
3. Return structured company info with specific keywords
"""

import re
import os
import json
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


@dataclass
class CompanyInfo:
    """Detected company information"""
    domain: str
    company_name: str = ""
    vertical: str = ""  # Parent category (e.g., "aerospace")
    primary_keyword: str = ""  # Most specific term (e.g., "investment casting")
    keywords: list = field(default_factory=list)  # All extracted keywords
    location: str = ""
    description: str = ""
    services: list = field(default_factory=list)  # Legacy - kept for compatibility
    detected: bool = False


# Target manufacturing verticals (from client feedback)
TARGET_VERTICALS = {
    "automotive_oem": {
        "name": "Automotive OEM",
        "triggers": ["automotive", "oem", "tier 1", "tier 2", "iatf 16949", "iatf", "auto parts", "vehicle components"],
        "keywords": ["automotive stamping", "automotive tooling", "vehicle components", "auto parts manufacturing"]
    },
    "medical_devices": {
        "name": "Medical Devices",
        "triggers": ["medical device", "iso 13485", "fda", "medical manufactur", "surgical", "implant", "biomedical"],
        "keywords": ["medical device manufacturing", "surgical instruments", "implant manufacturing", "fda registered"]
    },
    "fluid_handling": {
        "name": "Fluid Handling",
        "triggers": ["fluid handling", "valve", "pump", "hydraulic", "pneumatic", "piping", "flow control"],
        "keywords": ["valve manufacturing", "pump components", "hydraulic systems", "fluid control"]
    },
    "oil_gas": {
        "name": "Oil & Gas",
        "triggers": ["oil and gas", "oil & gas", "petroleum", "drilling", "pipeline", "refinery", "offshore", "downhole"],
        "keywords": ["oilfield equipment", "drilling components", "pipeline manufacturing", "downhole tools"]
    },
    "defense": {
        "name": "Defense",
        "triggers": ["defense", "military", "dod", "itar", "government contract", "mil-spec", "mil spec"],
        "keywords": ["defense manufacturing", "military components", "itar compliant", "mil-spec parts"]
    },
    "aviation": {
        "name": "Aviation",
        "triggers": ["aviation", "aircraft", "airline", "flight", "landing gear", "avionics"],
        "keywords": ["aircraft components", "aviation parts", "landing gear manufacturing", "avionics assembly"]
    },
    "aerospace": {
        "name": "Aerospace",
        "triggers": ["aerospace", "as9100", "nadcap", "space", "satellite", "rocket", "propulsion"],
        "keywords": ["aerospace manufacturing", "as9100 certified", "nadcap approved", "flight-critical parts"]
    },
    "space_exploration": {
        "name": "Space Exploration",
        "triggers": ["space exploration", "spacecraft", "satellite", "rocket", "launch vehicle", "orbital"],
        "keywords": ["spacecraft components", "satellite manufacturing", "rocket parts", "space-grade"]
    },
    "industrial": {
        "name": "Industrial",
        "triggers": ["industrial", "factory", "plant", "machinery", "equipment manufactur"],
        "keywords": ["industrial equipment", "factory machinery", "industrial components"]
    },
    "power_generation": {
        "name": "Power Generation",
        "triggers": ["power generation", "turbine", "generator", "energy", "power plant", "steam turbine", "gas turbine"],
        "keywords": ["turbine manufacturing", "generator components", "power plant equipment", "turbine blades"]
    },
    "heavy_machinery": {
        "name": "Heavy Machinery",
        "triggers": ["heavy machinery", "heavy equipment", "construction equipment", "mining equipment", "earthmoving"],
        "keywords": ["heavy equipment manufacturing", "construction machinery", "mining equipment parts"]
    },
    "robotics": {
        "name": "Robotics",
        "triggers": ["robotics", "robot", "automation", "automated", "cobot", "robotic arm"],
        "keywords": ["robotics manufacturing", "robotic components", "automation systems", "robotic assembly"]
    },
    "drones": {
        "name": "Drones/UAV",
        "triggers": ["drone", "uav", "unmanned", "uas", "quadcopter", "aerial vehicle"],
        "keywords": ["drone manufacturing", "uav components", "unmanned systems", "drone parts"]
    },
    "vehicle_electrification": {
        "name": "Vehicle Electrification",
        "triggers": ["electrification", "ev", "electric vehicle", "battery", "charging", "e-mobility", "hybrid"],
        "keywords": ["ev components", "electric vehicle manufacturing", "battery systems", "charging equipment"]
    },
    "cnc_machining": {
        "name": "CNC Machining",
        "triggers": ["cnc", "machining", "machine shop", "milling", "turning", "lathe", "swiss screw", "5-axis", "5 axis"],
        "keywords": ["cnc machining", "precision machining", "5-axis machining", "swiss screw machining"]
    },
}

# Specific manufacturing processes/capabilities (for keyword extraction)
SPECIFIC_KEYWORDS = [
    # Casting processes
    "investment casting", "die casting", "sand casting", "lost wax casting", "centrifugal casting",
    "precision casting", "vacuum casting", "permanent mold casting",
    
    # Machining processes
    "cnc machining", "cnc milling", "cnc turning", "5-axis machining", "swiss screw machining",
    "precision machining", "high-speed machining", "multi-axis machining", "wire edm", "sinker edm",
    "electrical discharge machining", "grinding", "honing", "lapping",
    
    # Forming processes
    "metal stamping", "progressive die stamping", "deep draw stamping", "hydroforming",
    "roll forming", "metal spinning", "forging", "cold forming", "hot forming",
    
    # Fabrication
    "sheet metal fabrication", "metal fabrication", "welding", "tig welding", "mig welding",
    "laser welding", "robotic welding", "tube bending", "pipe fabrication",
    
    # Cutting
    "laser cutting", "waterjet cutting", "plasma cutting", "fiber laser cutting",
    
    # Molding
    "injection molding", "plastic injection molding", "blow molding", "compression molding",
    "thermoforming", "rotational molding", "reaction injection molding",
    
    # Additive
    "3d printing", "additive manufacturing", "metal 3d printing", "dmls", "sls", "fdm",
    "rapid prototyping", "direct metal laser sintering",
    
    # Surface treatment
    "powder coating", "anodizing", "plating", "electroplating", "chrome plating",
    "nickel plating", "zinc plating", "passivation", "heat treatment",
    
    # Assembly
    "electromechanical assembly", "electronic assembly", "pcb assembly", "cable assembly",
    "mechanical assembly", "box build",
    
    # Specific components
    "turbine blades", "gear manufacturing", "bearing manufacturing", "spring manufacturing",
    "fastener manufacturing", "connector manufacturing", "sensor manufacturing",
    "heat exchanger", "pressure vessel",
    
    # Materials specialties
    "titanium machining", "inconel machining", "stainless steel", "aluminum machining",
    "exotic alloys", "superalloys", "composites", "carbon fiber",
    
    # Certifications (can be keywords too)
    "as9100 certified", "iso 13485 certified", "iatf 16949 certified", "nadcap certified",
    "itar registered", "fda registered",
]


def extract_keywords_from_text(text: str) -> list[tuple[str, int]]:
    """
    Extract specific manufacturing keywords from text.
    Returns list of (keyword, count) tuples sorted by count.
    """
    text_lower = text.lower()
    found = Counter()
    
    for keyword in SPECIFIC_KEYWORDS:
        # Count occurrences (case-insensitive)
        count = text_lower.count(keyword.lower())
        if count > 0:
            found[keyword] = count
    
    # Also look for keyword variations
    variations = {
        "5-axis": ["5 axis", "five axis", "5axis"],
        "cnc machining": ["cnc machine", "computer numerical control"],
        "3d printing": ["3-d printing", "three d printing"],
        "wire edm": ["wire electrical discharge", "wire erosion"],
    }
    
    for canonical, variants in variations.items():
        for variant in variants:
            if variant in text_lower:
                found[canonical] = found.get(canonical, 0) + text_lower.count(variant)
    
    return sorted(found.items(), key=lambda x: -x[1])


def detect_vertical(text: str) -> tuple[str, str]:
    """
    Detect industry vertical category from text.
    Returns (vertical_key, vertical_name).
    """
    text_lower = text.lower()
    
    scores = {}
    for key, config in TARGET_VERTICALS.items():
        score = sum(1 for trigger in config["triggers"] if trigger in text_lower)
        if score > 0:
            scores[key] = score
    
    if scores:
        best_key = max(scores, key=scores.get)
        return best_key, TARGET_VERTICALS[best_key]["name"]
    
    return "industrial", "Industrial Manufacturing"


def extract_location(text: str) -> str:
    """Try to extract location from text"""
    patterns = [
        r'(?:located in|based in|headquarters in|serving)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,?\s*[A-Z]{2})',
        r'([A-Z][a-z]+,\s*[A-Z]{2}\s*\d{5})',
        r'([A-Z][a-z]+,\s*[A-Z]{2})\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return ""


def clean_company_name(name: str, domain: str) -> str:
    """Clean up company name"""
    suffixes = [' LLC', ' Inc', ' Inc.', ' Corp', ' Corporation', ' Ltd', ' Co.', ' Company',
                ' | Home', ' - Home', ' – Home', ' | Official', ' - Official']
    
    result = name.strip()
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
    
    if len(result) > 50 or '|' in result or '-' in result:
        domain_clean = domain.replace('www.', '').split('.')[0]
        result = domain_clean.replace('-', ' ').replace('_', ' ').title()
    
    return result.strip()


async def extract_with_llm(content: str, company_name: str, openai_key: str = None, perplexity_key: str = None) -> dict:
    """
    Use GPT-4o or Perplexity to intelligently extract manufacturing info from website content.
    Prefers Perplexity (has web search) if available, falls back to GPT-4o.
    """
    prompt = f"""You are analyzing a manufacturing company's website to extract keywords that B2B buyers would search for.

TASK: Extract the most SPECIFIC and SEARCHABLE manufacturing capabilities.

RULES FOR primary_keyword:
- Must be what a buyer would actually type into ChatGPT or Perplexity
- Must be specific enough to find THIS type of company
- BAD: "manufacturing", "precision engineering", "quality products", "custom solutions"
- GOOD: "investment casting", "5-axis CNC machining", "titanium aerospace parts", "medical device injection molding", "turbine blade manufacturing"

RULES FOR keywords:
- Each must be a specific process, material specialty, or capability
- Think: "What would a procurement manager search for?"
- Include: specific processes (wire EDM, swiss screw machining), materials (inconel, titanium), certifications (AS9100, ISO 13485), or product types (turbine blades, surgical instruments)

Company name from title: {company_name}

Website content:
{content[:6000]}

Respond in JSON only:
{{
  "company_name": "actual company name",
  "vertical": "industry category (Aerospace, Medical Devices, Automotive, etc.)",
  "primary_keyword": "most specific searchable capability",
  "keywords": ["specific capability 1", "specific capability 2", "specific capability 3"],
  "location": "City, State or empty"
}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try Perplexity first (has web search for better context)
            if perplexity_key:
                print(f"    Using Perplexity for analysis...")
                response = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {perplexity_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {"role": "system", "content": "You are a manufacturing industry analyst. Extract specific, unique keywords - not generic terms. Always respond with valid JSON only."},
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 500,
                        "temperature": 0.1
                    }
                )
                response.raise_for_status()
                data = response.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Fall back to GPT-4o
            elif openai_key:
                print(f"    Using GPT-4o for analysis...")
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "o3-mini",
                        "messages": [
                            {"role": "system", "content": "You are a manufacturing industry analyst. Extract specific, unique keywords - not generic terms. Always respond with valid JSON only."},
                            {"role": "user", "content": prompt}
                        ],
                        "max_completion_tokens": 4000
                    }
                )
                response.raise_for_status()
                data = response.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                return None
            
            # Parse JSON from response
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            
            return json.loads(text)
    except Exception as e:
        print(f"    ⚠ LLM extraction failed: {e}")
        return None


async def detect_from_domain(domain: str, use_llm: bool = True) -> CompanyInfo:
    """
    Auto-detect company info from domain.
    
    Args:
        domain: Website domain to analyze
        use_llm: If True, use GPT-4o-mini for intelligent extraction (recommended)
    """
    info = CompanyInfo(domain=domain)
    
    # Clean domain
    domain_clean = domain.lower().replace('https://', '').replace('http://', '').replace('www.', '')
    if '/' in domain_clean:
        domain_clean = domain_clean.split('/')[0]
    
    info.domain = domain_clean
    info.company_name = domain_clean.split('.')[0].replace('-', ' ').replace('_', ' ').title()
    
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Fetch homepage
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
                info.description = meta_desc['content'][:500]
            
            # Get page text for analysis
            for tag in soup(['script', 'style', 'nav', 'footer']):
                tag.decompose()
            
            page_text = soup.get_text(separator=' ', strip=True)[:8000]
            combined_text = f"{info.company_name} {info.description} {page_text}"
            
            # Try LLM extraction first (smarter)
            openai_key = os.getenv('OPENAI_API_KEY')
            perplexity_key = os.getenv('PERPLEXITY_API_KEY')
            
            if use_llm and (openai_key or perplexity_key):
                print(f"  🤖 Using LLM to analyze {domain_clean}...")
                llm_result = await extract_with_llm(
                    combined_text, 
                    info.company_name, 
                    openai_key=openai_key,
                    perplexity_key=perplexity_key
                )
                
                if llm_result:
                    info.company_name = llm_result.get("company_name", info.company_name)
                    info.vertical = llm_result.get("vertical", "Manufacturing")
                    info.primary_keyword = llm_result.get("primary_keyword", "precision manufacturing")
                    info.keywords = llm_result.get("keywords", [])
                    info.location = llm_result.get("location", "")
                    info.services = info.keywords[:5]
                    info.detected = True
                    
                    print(f"  ✓ LLM Detected: {info.company_name}")
                    print(f"    Vertical: {info.vertical}")
                    print(f"    Primary keyword: {info.primary_keyword}")
                    if info.keywords:
                        print(f"    Keywords: {', '.join(info.keywords[:5])}")
                    
                    return info
            
            # Fallback to rule-based extraction
            print(f"  📝 Using rule-based extraction for {domain_clean}...")
            
            vertical_key, vertical_name = detect_vertical(combined_text)
            info.vertical = vertical_name
            
            keyword_counts = extract_keywords_from_text(combined_text)
            info.keywords = [kw for kw, count in keyword_counts[:10]]
            
            if keyword_counts:
                info.primary_keyword = keyword_counts[0][0]
            else:
                info.primary_keyword = TARGET_VERTICALS.get(vertical_key, {}).get("keywords", ["manufacturing"])[0]
            
            info.services = info.keywords[:5]
            info.location = extract_location(page_text)
            info.detected = True
            
            print(f"  ✓ Rule-based Detected: {info.company_name}")
            print(f"    Vertical: {info.vertical}")
            print(f"    Primary keyword: {info.primary_keyword}")
            if info.keywords:
                print(f"    Keywords: {', '.join(info.keywords[:5])}")
            
    except Exception as e:
        print(f"Detection error for {domain}: {e}")
        info.vertical = "Industrial Manufacturing"
        info.primary_keyword = "precision manufacturing"
        info.keywords = ["precision manufacturing"]
    
    return info


# Also try to fetch /about, /services, /capabilities pages for more keywords
async def detect_from_domain_deep(domain: str) -> CompanyInfo:
    """
    Enhanced detection that also checks /about, /services, /capabilities pages.
    Use this for more thorough keyword extraction.
    """
    info = await detect_from_domain(domain)
    
    if not info.detected:
        return info
    
    domain_clean = info.domain
    additional_text = ""
    
    # Pages to check for more keywords
    pages_to_check = ["/about", "/about-us", "/services", "/capabilities", "/what-we-do"]
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for page in pages_to_check:
            try:
                response = await client.get(
                    f"https://{domain_clean}{page}",
                    headers={"User-Agent": "Mozilla/5.0 (compatible; research bot)"}
                )
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for tag in soup(['script', 'style', 'nav', 'footer']):
                        tag.decompose()
                    additional_text += " " + soup.get_text(separator=' ', strip=True)[:3000]
            except:
                pass
    
    if additional_text:
        # Re-extract keywords with additional content
        keyword_counts = extract_keywords_from_text(additional_text)
        
        # Merge with existing keywords
        existing = set(info.keywords)
        for kw, count in keyword_counts:
            if kw not in existing:
                info.keywords.append(kw)
        
        info.keywords = info.keywords[:15]  # Cap at 15
        
        # Update primary if we found something better
        if keyword_counts and keyword_counts[0][1] > 3:  # At least 3 mentions
            info.primary_keyword = keyword_counts[0][0]
    
    return info


async def test():
    """Test LLM-powered detection with manufacturing companies"""
    from dotenv import load_dotenv
    load_dotenv()
    
    domains = [
        "xometry.com",
        "protolabs.com", 
        "pennengineering.com",
    ]
    
    print("\n🔍 Testing LLM-Powered Auto-Detection\n")
    print("="*60)
    
    for domain in domains:
        print(f"\n📊 Analyzing: {domain}")
        print("-"*40)
        info = await detect_from_domain(domain, use_llm=True)
        print(f"\n  Summary:")
        print(f"  Company: {info.company_name}")
        print(f"  Vertical: {info.vertical}")
        print(f"  Primary Keyword: {info.primary_keyword}")
        print(f"  All Keywords: {', '.join(info.keywords[:5]) if info.keywords else 'None'}")
        print(f"  Location: {info.location or 'Not found'}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
