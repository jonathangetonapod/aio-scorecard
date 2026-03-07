# AI Visibility Scorecard

B2B lead generation tool that shows prospects their AI visibility gap. Analyzes how often ChatGPT and Perplexity recommend a company when buyers search for their specific capabilities.

## How It Works

1. **Keyword Extraction** - Scrapes the prospect's website and uses Perplexity AI to extract specific, searchable capabilities (e.g., "investment casting", "5-axis CNC machining")
2. **AI Visibility Queries** - Queries both ChatGPT (o3-mini) and Perplexity (sonar) with real buyer-intent questions across 4 query types: research, quote, supplier, and compare
3. **Mention Detection** - Exact string matching for domain and company name in AI responses (no fuzzy matching, no LLM verification)
4. **Competitor Intelligence** - Extracts and validates competitor domains mentioned by AI, checks accessibility and industry relevance
5. **Report Generation** - Produces a printable HTML report with visibility score, revenue impact estimate, competitor rankings, and recommendations

## Features

- Queries ChatGPT (o3-mini) + Perplexity (sonar) with real buyer-intent questions
- Auto-detects company name, vertical, keywords, and location from domain
- Deep website crawling (/about, /services, /capabilities) for keyword extraction
- Exact string matching for mention detection (domain + company name) - no fuzzy matching
- 600-char response snippets with expandable full AI responses via modal
- Highlights target domain and company name in green in response snippets
- When mention is in full response but not visible snippet, shows "(see full response)" hint
- Shows which competitors AI recommends instead, ranked by mention frequency
- Revenue impact calculation based on AI share vs competitor share
- Printable HTML report (browser print-to-PDF)
- Pre-formatted email variables for Instantly.ai campaign integration
- Bring-your-own API keys with test/save functionality (persists in localStorage)

## Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Add your PERPLEXITY_API_KEY and/or OPENAI_API_KEY

# Run the server
python3 api.py
```

Server runs at http://localhost:3002

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the frontend |
| `/api/analyze` | POST | Runs full visibility analysis pipeline |
| `/api/report/pdf` | POST | Generates printable HTML report |
| `/api/test-key` | POST | Validates a Perplexity or OpenAI API key |
| `/api/health` | GET | Health check |

## Tech Stack

- **Backend**: Python, FastAPI, httpx (async HTTP)
- **AI Models**: OpenAI o3-mini, Perplexity sonar
- **Frontend**: Vanilla HTML/CSS/JS (single-page app)
- **Scraping**: BeautifulSoup4
- **Deployment**: Docker (Python 3.12-slim), Railway

## Project Structure

```
api.py                          # FastAPI server + endpoints
frontend/index.html             # Single-page frontend
pipeline/
  auto_detect.py                # Website scraping + keyword extraction
  ai_checker.py                 # AI platform queries + mention detection
  competitor_validator.py       # Competitor domain validation
  pdf_generator.py              # Printable HTML report generation
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PERPLEXITY_API_KEY` | One of these | Perplexity API key |
| `OPENAI_API_KEY` | required | OpenAI API key |
| `PORT` | No | Server port (default: 3002) |

## License

Proprietary - Lead Gen Jay
