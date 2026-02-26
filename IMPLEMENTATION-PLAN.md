# AIO Scorecard v2 - Implementation Plan

## Overview
Shift from **location-based** to **vertical/keyword-based** AI visibility analysis.

---

## Phase 1: Enhanced Keyword Extraction
**File:** `pipeline/auto_detect.py`
**Time:** ~30 min

### Changes:
1. Add manufacturing vertical categories (the 15 from David)
2. Extract **specific unique keywords** from website, not just generic vertical
   - Look for: product names, processes, materials, certifications
   - Examples: "investment casting", "turbine blades", "5-axis CNC", "ISO 13485"
3. Map extracted keywords to parent vertical category
4. Return both: `vertical` (category) + `keywords` (specific terms)

### New Output Structure:
```python
{
    "vertical": "aerospace",  # Parent category
    "keywords": ["investment casting", "turbine blades", "nadcap certified"],
    "primary_keyword": "investment casting"  # Most prominent/unique
}
```

---

## Phase 2: Vertical-Based Query Generation
**File:** `pipeline/ai_checker.py`
**Time:** ~30 min

### Changes:
1. Rewrite query templates to be keyword-focused:
   - OLD: "Best {vertical} companies in {city}, {state}"
   - NEW: "Find me {keyword} manufacturing companies"
   - NEW: "Best {keyword} manufacturers in the US"
   - NEW: "Who are the top {keyword} suppliers?"

2. Compare against **vertical competitors**, not geographic
   - "How does {company} compare to other {keyword} manufacturers?"

3. Keep location as optional secondary signal (if provided)

### New Query Templates:
```python
VERTICAL_QUERIES = [
    "Find me {keyword} manufacturing companies",
    "Best {keyword} manufacturers",
    "Top {keyword} suppliers in the United States",
    "Who should I contact for {keyword} services?",
    "I need a quote for {keyword} - who are the best companies?",
    "Compare {keyword} manufacturers - who's the best?",
]
```

---

## Phase 3: API Response Enhancement
**File:** `api.py`
**Time:** ~20 min

### Changes:
1. Add `primary_keyword` to response (for email personalization)
2. Add `keywords` array to response
3. Update `AnalyzeResponse` model

### New Response Fields:
```python
{
    "domain": "example.com",
    "company_name": "Example Mfg",
    "vertical": "aerospace",
    "primary_keyword": "investment casting",  # NEW - for email
    "keywords": ["investment casting", "turbine blades"],  # NEW
    "visibility_score": 8,
    ...
}
```

---

## Phase 4: Frontend Updates
**File:** `frontend/index.html`
**Time:** ~20 min

### Changes:
1. Show extracted keywords in results
2. Update messaging to be vertical-focused (not location)
3. Add "Copy for Instantly" button with pre-formatted variables

---

## Phase 5: Email Template Output
**New capability**
**Time:** ~15 min

### Add endpoint or output:
```json
{
    "instantly_variables": {
        "keyword": "investment casting",
        "vertical": "aerospace",
        "visibility_score": "8%",
        "top_competitor": "protolabs.com"
    },
    "email_snippet": "I noticed you're not ranking in LLMs for what you focus on — investment casting. I ran a report comparing you to other investment casting manufacturers..."
}
```

---

## Total Estimated Time: ~2 hours

## Order of Execution:
1. ✅ Phase 1 - Keyword extraction (foundation)
2. ✅ Phase 2 - Query generation (core logic)
3. ✅ Phase 3 - API response (connect it)
4. ✅ Phase 4 - Frontend (show it)
5. ✅ Phase 5 - Email output (use it)

---

## Testing Plan:
Test with manufacturers from David's verticals:
- A CNC shop → should extract specific processes
- An aerospace company → should extract certifications, materials
- A medical device mfg → should extract ISO 13485, FDA, etc.

---

## Notes:
- Employee count filter (50-200) is a **lead list** thing, not tool-side
- Cost stays ~$0.05/prospect (same # of API calls)
- Can add more LLMs later (Claude, Gemini) if needed
