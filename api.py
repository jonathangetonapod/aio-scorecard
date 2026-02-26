"""
AIO Scorecard API v2

Vertical-based AI visibility checking for manufacturers.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from pipeline.auto_detect import detect_from_domain
from pipeline.ai_checker import AIChecker
from pipeline.competitor_validator import validate_competitors
from pipeline.pdf_generator import generate_pdf

app = FastAPI(title="AIO Scorecard", version="2.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    domain: str
    company_name: Optional[str] = None
    vertical: Optional[str] = None
    primary_keyword: Optional[str] = None
    keywords: Optional[list] = None
    location: Optional[str] = None
    # API keys (optional - falls back to env vars)
    perplexity_key: Optional[str] = None
    openai_key: Optional[str] = None
    # Legacy field
    services: Optional[list] = None


class QueryResult(BaseModel):
    platform: str
    query: str
    query_type: str
    keyword: str
    snippet: str
    mentioned: bool
    competitors_found: list[str] = []


class CompetitorInfo(BaseModel):
    domain: str
    mentions: int
    is_valid: bool = True
    is_relevant: bool = False
    company_name: str = ""
    note: str = ""


class InstantlyVariables(BaseModel):
    """Pre-formatted variables for Instantly email campaigns"""
    keyword: str
    vertical: str
    visibility_score: str
    top_competitor: str
    email_snippet: str


class AnalyzeResponse(BaseModel):
    domain: str
    company_name: str
    vertical: str
    primary_keyword: str  # NEW - for email personalization
    keywords: list[str] = []  # NEW - all extracted keywords
    location: str = ""
    
    # Scores
    visibility_score: float
    total_queries: int
    total_mentions: int
    
    # Platform breakdown
    perplexity_queries: int = 0
    perplexity_mentions: int = 0
    chatgpt_queries: int = 0
    chatgpt_mentions: int = 0
    
    # Query results with snippets
    query_results: list[QueryResult] = []
    
    # Competitors
    competitors: list[CompetitorInfo]
    
    # Email helpers
    instantly_variables: Optional[InstantlyVariables] = None
    
    # Status
    status: str = "complete"


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_domain(req: AnalyzeRequest):
    """
    Analyze a domain's AI visibility using vertical-based queries.
    
    v2: Uses specific manufacturing keywords instead of location-based queries.
    """
    try:
        # Clean domain input
        domain = req.domain.strip().lower()
        domain = domain.replace('https://', '').replace('http://', '').replace('www.', '')
        if '/' in domain:
            domain = domain.split('/')[0]
        
        if not domain or '.' not in domain:
            raise HTTPException(status_code=400, detail="Please enter a valid domain (e.g., yourcompany.com)")
        
        req.domain = domain
        
        # Handle legacy 'services' field
        if req.services and not req.keywords:
            req.keywords = req.services
        
        # Auto-detect if needed
        if not req.company_name or not req.primary_keyword:
            print(f"🔍 Auto-detecting info for {req.domain}...")
            try:
                info = await detect_from_domain(
                    req.domain,
                    perplexity_key=req.perplexity_key,
                    openai_key=req.openai_key
                )
                
                if not req.company_name:
                    req.company_name = info.company_name or req.domain.split('.')[0].title()
                if not req.vertical:
                    req.vertical = info.vertical or "Industrial Manufacturing"
                if not req.primary_keyword:
                    req.primary_keyword = info.primary_keyword or "precision manufacturing"
                if not req.keywords:
                    req.keywords = info.keywords or []
                if not req.location:
                    req.location = info.location or ""
                    
            except Exception as e:
                print(f"Auto-detect failed: {e}")
                req.company_name = req.company_name or req.domain.split('.')[0].title()
                req.vertical = req.vertical or "Industrial Manufacturing"
                req.primary_keyword = req.primary_keyword or "precision manufacturing"
                req.keywords = req.keywords or []
                req.location = req.location or ""
        
        print(f"\n📊 Checking visibility for {req.company_name}")
        print(f"   Vertical: {req.vertical}")
        print(f"   Primary Keyword: {req.primary_keyword}")
        if req.keywords:
            print(f"   Keywords: {', '.join(req.keywords[:5])}")
        
        # Run visibility check - use request keys if provided, fallback to env
        perplexity_key = req.perplexity_key or os.getenv('PERPLEXITY_API_KEY')
        openai_key = req.openai_key or os.getenv('OPENAI_API_KEY')
        
        if not perplexity_key and not openai_key:
            raise HTTPException(status_code=500, detail="No AI API keys provided. Please add your Perplexity or OpenAI API key.")
        
        checker = AIChecker(
            perplexity_key=perplexity_key,
            openai_key=openai_key
        )
        
        report = await checker.check_visibility(
            domain=req.domain,
            company_name=req.company_name,
            vertical=req.vertical,
            primary_keyword=req.primary_keyword,
            keywords=req.keywords or [],
            location=req.location or ""
        )
        
        # Ensure we got at least some queries through
        if report.total_queries == 0:
            raise HTTPException(status_code=500, detail="All AI queries failed. Please try again.")
        
        # Build query results
        query_results = [
            QueryResult(
                platform=r.platform,
                query=r.query,
                query_type=r.query_type,
                keyword=r.keyword,
                snippet=r.response_snippet,
                mentioned=r.mentions_target,
                competitors_found=r.competitors_found
            )
            for r in report.responses
        ]
        
        # Validate competitors
        print("  → Validating competitors...")
        validated = await validate_competitors(
            report.competitors,
            target_services=req.keywords or [],
            max_to_validate=15
        )
        
        # Build competitor list (only valid ones)
        competitors = [
            CompetitorInfo(
                domain=c.domain,
                mentions=c.mentions,
                is_valid=c.is_valid,
                is_relevant=c.is_relevant,
                company_name=c.company_name,
                note=c.validation_note
            )
            for c in validated
            if c.is_valid
        ]
        
        # Get top competitor for email
        top_competitor = competitors[0].domain if competitors else "competitors"
        
        # Build Instantly variables
        instantly_vars = InstantlyVariables(
            keyword=req.primary_keyword,
            vertical=req.vertical,
            visibility_score=f"{report.visibility_score:.0f}%",
            top_competitor=top_competitor,
            email_snippet=f"I noticed you're not ranking in LLMs for what you focus on: {req.primary_keyword}. I ran a report comparing you to other {req.primary_keyword} manufacturers, and this is where you rank. Can I send over the report?"
        )
        
        return AnalyzeResponse(
            domain=report.domain,
            company_name=report.company_name,
            vertical=report.vertical,
            primary_keyword=report.primary_keyword,
            keywords=req.keywords or [],
            location=req.location or "",
            visibility_score=report.visibility_score,
            total_queries=report.total_queries,
            total_mentions=report.total_mentions,
            perplexity_queries=report.perplexity_queries,
            perplexity_mentions=report.perplexity_mentions,
            chatgpt_queries=report.chatgpt_queries,
            chatgpt_mentions=report.chatgpt_mentions,
            query_results=query_results,
            competitors=competitors,
            instantly_variables=instantly_vars
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error analyzing {req.domain}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report/pdf")
async def generate_pdf_report(data: dict):
    """Generate printable HTML report (use browser Print > Save as PDF)"""
    try:
        from pipeline.pdf_generator import generate_report_html
        html_content = generate_report_html(data)
        
        return Response(
            content=html_content,
            media_type="text/html",
        )
    except Exception as e:
        print(f"Report generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0"}


# Serve frontend
@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3002))
    uvicorn.run(app, host="0.0.0.0", port=port)
