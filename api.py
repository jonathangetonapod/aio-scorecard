"""
AIO Scorecard API

Simple FastAPI backend for AI visibility checking.
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
    location: Optional[str] = None
    services: Optional[list] = None


class QueryResult(BaseModel):
    platform: str
    query: str
    query_type: str  # research, quote, urgent, compare
    service: str
    location_type: str  # local, national
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


class AnalyzeResponse(BaseModel):
    domain: str
    company_name: str
    vertical: str
    location: str
    services: list[str] = []
    
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
    
    # Status
    status: str = "complete"


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_domain(req: AnalyzeRequest):
    """
    Analyze a domain's AI visibility.
    
    Queries AI chatbots to check if the domain gets recommended.
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
        
        # Auto-detect if needed
        if not req.company_name or not req.vertical:
            print(f"🔍 Auto-detecting info for {req.domain}...")
            try:
                info = await detect_from_domain(req.domain)
                
                if not req.company_name:
                    req.company_name = info.company_name or req.domain.split('.')[0].title()
                if not req.vertical:
                    req.vertical = info.vertical or "business services"
                if not req.location:
                    req.location = info.location or ""
                if not req.services:
                    req.services = info.services or []
            except Exception as e:
                print(f"Auto-detect failed: {e}")
                req.company_name = req.company_name or req.domain.split('.')[0].title()
                req.vertical = req.vertical or "business services"
                req.location = req.location or ""
                req.services = req.services or []
        
        print(f"📊 Checking visibility for {req.company_name} ({req.vertical})")
        if req.location:
            print(f"   Location: {req.location}")
        if req.services:
            print(f"   Services: {', '.join(req.services[:5])}")
        
        # Run visibility check with both APIs
        perplexity_key = os.getenv('PERPLEXITY_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        
        if not perplexity_key and not openai_key:
            raise HTTPException(status_code=500, detail="No AI API keys configured")
        
        checker = AIChecker(
            perplexity_key=perplexity_key,
            openai_key=openai_key
        )
        
        report = await checker.check_visibility(
            domain=req.domain,
            company_name=req.company_name,
            vertical=req.vertical,
            location=req.location or "",
            services=req.services or []
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
                service=r.service,
                location_type=r.location_type,
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
            target_services=req.services or [],
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
            if c.is_valid  # Only include accessible domains
        ]
        
        return AnalyzeResponse(
            domain=report.domain,
            company_name=report.company_name,
            vertical=report.vertical,
            location=report.location,
            services=req.services or [],
            visibility_score=report.visibility_score,
            total_queries=report.total_queries,
            total_mentions=report.total_mentions,
            perplexity_queries=report.perplexity_queries,
            perplexity_mentions=report.perplexity_mentions,
            chatgpt_queries=report.chatgpt_queries,
            chatgpt_mentions=report.chatgpt_mentions,
            query_results=query_results,
            competitors=competitors
        )
        
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
