"""
PDF Report Generator - Returns printable HTML
"""

from datetime import datetime


def generate_report_html(data: dict) -> str:
    """Generate beautiful printable HTML report"""
    
    score = round(data.get('visibility_score', 0))
    company = data.get('company_name', 'Company')
    domain = data.get('domain', '')
    location = data.get('location', '')
    keywords = data.get('keywords', data.get('primary_keyword', '').split() if data.get('primary_keyword') else [])
    competitors = [c for c in data.get('competitors', []) if c.get('is_valid', True)]
    total_queries = data.get('total_queries', 0)
    total_mentions = data.get('total_mentions', 0)
    query_results = data.get('query_results', [])
    pplx_q = data.get('perplexity_queries', 0)
    pplx_m = data.get('perplexity_mentions', 0)
    gpt_q = data.get('chatgpt_queries', 0)
    gpt_m = data.get('chatgpt_mentions', 0)
    logo = data.get('logo', '')  # Base64 encoded logo
    
    # Grade
    if score >= 70:
        grade, grade_color = "Strong", "#059669"
    elif score >= 40:
        grade, grade_color = "Moderate", "#2563eb"
    elif score >= 15:
        grade, grade_color = "Low", "#d97706"
    else:
        grade, grade_color = "Critical", "#dc2626"
    
    # Revenue calc
    service_lower = (keywords[0] if keywords else 'manufacturing').lower()
    if 'aerospace' in service_lower: deal_size = 75000
    elif 'medical' in service_lower: deal_size = 50000
    elif 'automotive' in service_lower: deal_size = 40000
    else: deal_size = 25000
    
    monthly_searches = 150 if location else 350
    missed_pct = max(0, (100 - score)) / 100
    monthly_missed = round(monthly_searches * 0.03 * missed_pct)
    monthly_risk = monthly_missed * 0.15 * deal_size
    
    # Preformat for f-string (avoid nested format)
    monthly_risk_fmt = "{:,.0f}".format(monthly_risk)
    deal_size_fmt = "{:,}".format(deal_size)
    missed_pct_fmt = round(missed_pct * 100)
    
    # Build competitor rows FIRST (before competitors_html f-string)
    competitor_rows = ""
    for i, c in enumerate(competitors[:8], 1):
        relevant_badge = '<span style="color: #059669;">✓</span>' if c.get('is_relevant') else '-'
        competitor_rows += f'''
            <tr>
                <td style="text-align: center;">{i}</td>
                <td>{c.get('domain', '')}</td>
                <td style="text-align: center;">{c.get('mentions', 0)}</td>
                <td style="text-align: center;">{relevant_badge}</td>
            </tr>
        '''

    # Build query items FIRST (before mentioned_html and missed_html f-strings)
    mentioned_queries = ""
    missed_queries = ""

    for q in query_results:
        platform = "Perplexity" if q.get('platform') == 'perplexity' else "ChatGPT"
        query_text = q.get('query', '')[:80]
        snippet = q.get('snippet', '')[:150]
        comps = q.get('competitors_found', [])[:2]

        if q.get('mentioned'):
            mentioned_queries += f'''
                <div class="query-item mentioned">
                    <div class="query-header">
                        <span class="platform">{platform}</span>
                        <span class="status mentioned">✓ Mentioned</span>
                    </div>
                    <div class="query-text">"{query_text}"</div>
                    {f'<div class="snippet">"{snippet}..."</div>' if snippet else ''}
                </div>
            '''
        else:
            comp_text = f'<div class="comps">Recommended instead: {", ".join(comps)}</div>' if comps else ''
            missed_queries += f'''
                <div class="query-item missed">
                    <div class="query-header">
                        <span class="platform">{platform}</span>
                        <span class="status missed">✗ Not Mentioned</span>
                    </div>
                    <div class="query-text">"{query_text}"</div>
                    {comp_text}
                    {f'<div class="snippet">"{snippet}..."</div>' if snippet else ''}
                </div>
            '''

    # Build conditional sections (all variables now defined above)
    impact_html = ""
    if monthly_risk > 0:
        impact_html = f'''
    <div class="impact-box">
        <div class="impact-title">ESTIMATED MONTHLY REVENUE AT RISK</div>
        <div class="impact-value">${monthly_risk_fmt}</div>
        <div class="impact-detail">
            Based on ~{monthly_searches} AI searches/month x {missed_pct_fmt}% going to competitors x ${deal_size_fmt} avg deal
        </div>
    </div>
        '''

    competitors_html = ""
    if competitors:
        competitors_html = f'''
    <h2>Who AI Recommends Instead</h2>
    <table>
        <tr>
            <th style="width: 40px;">#</th>
            <th>Competitor</th>
            <th style="width: 80px;">Mentions</th>
            <th style="width: 80px;">Industry</th>
        </tr>
        {competitor_rows}
    </table>
        '''

    mentioned_html = f'<h3 style="color: #059669;">✓ Where You Were Mentioned</h3>{mentioned_queries}' if mentioned_queries else ''
    missed_html = f'<h3 style="color: #dc2626;">✗ Where You Were NOT Mentioned</h3>{missed_queries}' if missed_queries else ''
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AI Visibility Report - {company}</title>
    <style>
        @media print {{
            body {{ margin: 0; padding: 20px; }}
            .no-print {{ display: none !important; }}
            .page-break {{ page-break-before: always; }}
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #1f2937;
            line-height: 1.5;
            padding: 40px;
            max-width: 800px;
            margin: 0 auto;
            background: white;
        }}
        
        .print-btn {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: #2563eb;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            z-index: 1000;
        }}
        .print-btn:hover {{ background: #1d4ed8; }}
        
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e5e7eb;
        }}
        .header h1 {{
            font-size: 28px;
            color: #111827;
            margin-bottom: 5px;
        }}
        .header .company {{
            font-size: 18px;
            color: #6b7280;
        }}
        
        .score-section {{
            text-align: center;
            padding: 30px;
            background: #f9fafb;
            border-radius: 12px;
            margin-bottom: 30px;
        }}
        .score-number {{
            font-size: 64px;
            font-weight: bold;
            color: {grade_color};
        }}
        .score-grade {{
            font-size: 20px;
            color: {grade_color};
            margin-bottom: 15px;
        }}
        .score-summary {{
            color: #6b7280;
            font-size: 14px;
        }}
        
        h2 {{
            font-size: 18px;
            color: #111827;
            margin: 30px 0 15px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        h3 {{
            font-size: 14px;
            margin: 20px 0 10px 0;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-box {{
            background: #f9fafb;
            padding: 15px;
            border-radius: 8px;
        }}
        .stat-label {{
            font-size: 12px;
            color: #6b7280;
            margin-bottom: 5px;
        }}
        .stat-value {{
            font-size: 18px;
            font-weight: 600;
        }}
        .stat-value.green {{ color: #059669; }}
        .stat-value.red {{ color: #dc2626; }}
        
        .impact-box {{
            background: #fef2f2;
            border: 1px solid #fecaca;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
        }}
        .impact-title {{
            color: #dc2626;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 5px;
        }}
        .impact-value {{
            font-size: 28px;
            font-weight: bold;
            color: #dc2626;
        }}
        .impact-detail {{
            font-size: 12px;
            color: #6b7280;
            margin-top: 8px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 14px;
        }}
        th {{
            background: #111827;
            color: white;
            padding: 10px;
            text-align: left;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #e5e7eb;
        }}
        tr:nth-child(even) {{
            background: #f9fafb;
        }}
        
        .query-item {{
            padding: 15px;
            margin-bottom: 12px;
            border-radius: 8px;
            border-left: 4px solid;
        }}
        .query-item.mentioned {{
            background: #f0fdf4;
            border-color: #059669;
        }}
        .query-item.missed {{
            background: #fef2f2;
            border-color: #dc2626;
        }}
        .query-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .platform {{
            font-size: 12px;
            color: #6b7280;
        }}
        .status {{
            font-size: 12px;
            font-weight: 600;
        }}
        .status.mentioned {{ color: #059669; }}
        .status.missed {{ color: #dc2626; }}
        .query-text {{
            font-weight: 500;
            margin-bottom: 8px;
        }}
        .comps {{
            font-size: 12px;
            color: #d97706;
            margin-bottom: 8px;
        }}
        .snippet {{
            font-size: 12px;
            color: #6b7280;
            font-style: italic;
        }}
        
        .rec-item {{
            margin-bottom: 20px;
        }}
        .rec-title {{
            font-weight: 600;
            margin-bottom: 5px;
        }}
        .rec-text {{
            color: #4b5563;
            font-size: 14px;
        }}
        
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
        }}
        .footer-cta {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 5px;
        }}
        .footer-link {{
            color: #2563eb;
            font-size: 16px;
            font-weight: 600;
        }}
        .footer-meta {{
            color: #9ca3af;
            font-size: 11px;
            margin-top: 20px;
        }}
        
        .page-break {{
            page-break-before: always;
        }}
    </style>
</head>
<body>
    <button class="print-btn no-print" onclick="window.print()">📄 Print / Save as PDF</button>
    
    <div class="header">
        {f'<img src="{logo}" alt="Company Logo" style="max-height: 60px; margin-bottom: 15px;" />' if logo else ''}
        <h1>AI Visibility Report</h1>
        <div class="company">{company} • {domain}</div>
    </div>
    
    <div class="score-section">
        <div class="score-number">{score}%</div>
        <div class="score-grade">{grade} Visibility</div>
        <div class="score-summary">
            Your company was mentioned in {total_mentions} of {total_queries} AI queries
        </div>
    </div>
    
    <h2>Platform Results</h2>
    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-label">Perplexity</div>
            <div class="stat-value {'green' if pplx_m > 0 else 'red'}">{pplx_m} / {pplx_q} mentions</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">ChatGPT (o3-mini)</div>
            <div class="stat-value {'green' if gpt_m > 0 else 'red'}">{gpt_m} / {gpt_q} mentions</div>
        </div>
    </div>
    
    
    {impact_html}
    
    {competitors_html}
    
    <div class="page-break"></div>
    
    <h2>Query Details</h2>
    
    {mentioned_html}
    
    {missed_html}
    
    <div class="page-break"></div>
    
    <h2>How to Improve Your AI Visibility</h2>
    
    <div class="rec-item">
        <div class="rec-title">1. Update Your Website Content</div>
        <div class="rec-text">Clearly describe your services, location, and industries served using the language your customers search for.</div>
    </div>
    
    <div class="rec-item">
        <div class="rec-title">2. Publish Helpful Content</div>
        <div class="rec-text">Create case studies, guides, and FAQs. AI cites authoritative sources when making recommendations.</div>
    </div>
    
    <div class="rec-item">
        <div class="rec-title">3. Build Your Digital Presence</div>
        <div class="rec-text">Get listed on industry directories, maintain your Google Business profile, and collect customer reviews.</div>
    </div>
    
    <div class="rec-item">
        <div class="rec-title">4. Monitor Progress</div>
        <div class="rec-text">Run this analysis quarterly to track improvements and adjust your strategy.</div>
    </div>
    
    <div class="footer">
        <div class="footer-cta">Ready to improve your AI visibility?</div>
        <div class="footer-link">marketmagnetix.agency</div>
        <div class="footer-meta">
            Report generated {datetime.now().strftime('%B %d, %Y')} • Powered by MarketMagnetix Media Group
        </div>
    </div>
</body>
</html>'''
    
    return html


def generate_pdf(data: dict, output_path: str = None) -> bytes:
    """Return HTML for browser printing"""
    # Return the HTML content as bytes
    html = generate_report_html(data)
    return html.encode('utf-8')
