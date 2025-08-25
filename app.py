import os
import re
import base64
import tempfile
import logging
import sys
import traceback
import uuid
import json
import time
from datetime import datetime, timedelta

# Create necessary directories first
os.makedirs("logs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

from auth import login_required, is_authenticated
from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from main import process_single_pdf, process_multiple_pdfs
from report_handlers import ReportTypeFactory
from google_auth import get_google_sheets_service, get_google_auth_url, finish_google_auth
from news_utils import ClaudeWebSearchEngine, create_source_url_mapping

from news_utils import fetch_comprehensive_news_guaranteed_30_enhanced
from company_ticker_service import fast_company_ticker_service as company_ticker_service
from configuration_and_integration import ConfigurationManager, IntegrationHelper

# Database imports
from db_utils import initialize_database, get_pmi_data_by_month, get_index_time_series, get_industry_status_over_time, get_all_indices, get_all_report_dates, get_db_connection
from config_loader import config_loader 
from typing import List, Dict, Optional, Tuple

from openai import OpenAI

RUN_CACHE = {}  # In-memory cache - replace with Redis for production

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/app.log'
)
logger = logging.getLogger(__name__)
logger.info("Starting app.py execution...")

if 'GOOGLE_CREDENTIALS_BASE64' in os.environ:
    credentials_data = base64.b64decode(os.environ['GOOGLE_CREDENTIALS_BASE64'])
    with open('credentials.json', 'wb') as f:
        f.write(credentials_data)

# Add console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# Create Flask application
app = Flask(__name__)
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
logger.info("Secret key set.")

# --- ADD THIS WRAPPER ---
# Tell Flask it is behind one proxy (Railway's load balancer)
# and to trust X-Forwarded-Proto for determining the scheme (http/https)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
logger.info("Flask app wrapped with ProxyFix.")

# Set upload folder and maximum file size
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

def convert_markdown_bullet(bullet):
    # Convert **bold:** to <strong>bold:</strong>
    bullet = re.sub(r"\*\*(.+?)\*\*:", r"<strong>\1:</strong>", bullet)
    # Convert [text](url) to HTML links
    bullet = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', bullet)
    return bullet

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Check for anthropic availability (following existing pattern from news_utils.py)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

def _build_source_map(articles):
    """Build source map for chatbot citations from articles list."""
    def safe_get(obj, key, default=""):
        """Safely get value from dict, handling Jinja2 Undefined objects."""
        try:
            value = obj.get(key, default)
            # Check if value is a Jinja2 Undefined object
            if hasattr(value, '__class__') and 'Undefined' in value.__class__.__name__:
                return default
            # Convert None to empty string for JSON serialization
            if value is None:
                return default
            return str(value)
        except Exception:
            return default
    
    smap = {}
    for i, article in enumerate(articles, start=1):
        smap[str(i)] = {
            "url": (article.get("link") or article.get("url") or article.get("web_url") or article.get("href") or "#"),
            "title": safe_get(article, "title", "Unknown Source"),
            "published_at": safe_get(article, "published", ""),
            "source": safe_get(article, "source", "")
        }
    return smap

# ADD: normalize alt citation tokens to [S#]
def _normalize_citation_tokens(text: str) -> str:
    if not text:
        return text
    # [^12] -> [S12], [12] -> [S12]  (won't hit [Text](url))
    text = re.sub(r'\[\^?(\d+)\]', r'[S\1]', text)
    # (S12) or (s 12) -> [S12]
    text = re.sub(r'\(\s*[Ss]\s*(\d+)\s*\)', r'[S\1]', text)
    # {S12} -> [S12]
    text = re.sub(r'\{\s*[Ss]\s*(\d+)\s*\}', r'[S\1]', text)
    return text

# ADD: render bullets with [S#] → anchor tags, plus basic markdown
def _render_bullet_with_citations(bullet: str, source_map: Dict[str, Dict[str, str]]) -> str:
    import html as _html

    if not bullet:
        return ""

    # 1) Normalize alt tokens to [S#]
    text = _normalize_citation_tokens(bullet)

    # 2) Basic markdown to HTML (bold + inline [text](url))
    #    (keep this minimal, you already trust |safe in the template)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)

    # 3) Replace [S#] with clickable badges using source_map
    def _sref(match):
        sid = match.group(1)
        data = source_map.get(str(sid)) or {}
        url = (data.get("url") or "").strip()
        title = data.get("title") or "Source"
        if url:
            return (
                f'<a href="{_html.escape(url)}" target="_blank" rel="noopener" '
                f'class="badge bg-secondary text-decoration-none source-badge" '
                f'title="{_html.escape(title)}"><i class="fas fa-link"></i> S{sid}</a>'
            )
        # leave the raw token if we can’t resolve
        return f'[S{sid}]'

    text = re.sub(r'\[S(\d+)\]', _sref, text)

    return text

def _normalize_chat_citations(text: str) -> str:
    """Normalize citation tokens in chat responses."""
    if not text:
        return text
    # Convert (S 12), {S12}, [^12] etc. to [S12]
    text = re.sub(r'\(\s*[Ss]\s*(\d+)\s*\)', r'[S\1]', text)
    text = re.sub(r'\{\s*[Ss]\s*(\d+)\s*\}', r'[S\1]', text)
    text = re.sub(r'\[\^(\d+)\]', r'[S\1]', text)
    return text

def _extract_citations(answer_text, max_id):
    """Extract [S#] citations from answer text."""
    text = _normalize_citation_tokens(answer_text or "")
    nums, seen = [], set()
    for match in re.finditer(r"\[S(\d+)\]", text):
        try:
            n = int(match.group(1))
            if 1 <= n <= max_id and n not in seen:
                seen.add(n)
                nums.append(n)
        except ValueError:
            continue
    return nums

def _compose_context(run_data):
    """Compose concise context for Claude from cached run data."""
    summaries = run_data["summaries"]
    lines = []
    
    lines.append(f"COMPANY: {run_data['company']} | ANALYSIS PERIOD: {run_data['date_range']}")
    
    lines.append("\n== EXECUTIVE SUMMARY ==")
    for bullet in summaries.get("executive", []):
        # Strip HTML for Claude
        clean_bullet = re.sub(r'<[^>]+>', '', bullet)
        lines.append(f"• {clean_bullet}")
    
    lines.append("\n== INVESTOR INSIGHTS ==")
    for bullet in summaries.get("investor", []):
        clean_bullet = re.sub(r'<[^>]+>', '', bullet)
        lines.append(f"• {clean_bullet}")
    
    lines.append("\n== CATALYSTS & RISKS ==")
    for bullet in summaries.get("catalysts", []):
        clean_bullet = re.sub(r'<[^>]+>', '', bullet)
        lines.append(f"• {clean_bullet}")
    
    lines.append("\n== SOURCES INDEX ==")
    for i, article in enumerate(run_data["articles"], start=1):
        title = article.get("title", "Unknown")[:60]
        source = article.get("source", "Unknown")
        date = article.get("published", "")
        lines.append(f"[S{i}] {title} | {source} | {date}")
    
    return "\n".join(lines)

# System prompt for chatbot
CHATBOT_SYSTEM_PROMPT = """You are a financial analysis assistant answering questions about a specific company analysis.

CRITICAL RULES:
1. Answer ONLY using the provided analysis context
2. If information isn't in the context, clearly state "This information is not available in the current analysis"
3. Always cite sources using [S#] tokens that match the Sources Index
4. Keep answers concise and investor-focused
5. Include specific dates, numbers, and metrics when available in context
6. Do not fabricate information or use outside knowledge

CITATION FORMAT:
- Use [S#] where # matches the Sources Index number
- Example: "Revenue grew 15% [S3] driven by strong demand [S7]"

RESPONSE STYLE:
- Direct and actionable for investors
- Include specific metrics and timelines when available
- Professional but accessible tone"""


@app.route('/landing')
@app.route('/welcome')
def landing():
    """Landing page for the application."""
    return render_template('landing.html')

@app.route('/login')
def login():
    """Initiate Google login flow."""
    if is_authenticated():
        return redirect(url_for('index'))
    
    try:
        # Get the auth URL
        auth_url = get_google_auth_url()
        if not auth_url:
            flash('Error setting up Google authentication.', 'danger')
            return redirect(url_for('landing'))
        
        # Redirect to Google's auth page
        return redirect(auth_url)
    except Exception as e:
        flash(f'Error with Google authentication: {str(e)}', 'danger')
        return redirect(url_for('landing'))

@app.route('/logout')
def logout():
    """Log out the user."""
    session.pop('authenticated', None)
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('landing'))

@app.route('/')
def root():
    """Root route that checks auth and redirects appropriately."""
    if is_authenticated():
        return redirect(url_for('index'))
    return redirect(url_for('landing'))

@app.route('/home')
@login_required
def index():
    """Main dashboard or upload page after authentication."""
    try:
        # Your existing index code...
        # Check if database is initialized and has data
        has_data = False
        try:
            initialize_database()
            dates = get_all_report_dates()
            has_data = len(dates) > 0
        except Exception as e:
            logger.error(f"Error checking database: {str(e)}")
        
        # If data exists, show dashboard; otherwise, show upload page
        if has_data:
            # Get data for dashboard
            heatmap_data = get_pmi_data_by_month(24)  # Get last 24 months of data
            indices = get_all_indices()
            report_dates = get_all_report_dates()
            
            return render_template('dashboard.html', 
                               heatmap_data=heatmap_data,
                               indices=indices,
                               report_dates=report_dates)
        else:
            # No data yet, redirect to upload page
            return redirect(url_for('upload_view'))
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        logger.error(traceback.format_exc())
        # On error, fall back to the upload page
        return redirect(url_for('upload_view'))
    
# News Summarizer Code
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/news")
@login_required
def news_form():
    """Display the enhanced news analysis form."""
    return render_template("news_simple.html")

@app.route("/news/summary", methods=["POST"])
@login_required
def get_news_summary():
    """
    Generate institutional-grade financial news analysis with chatbot support.
    CORRECTED V3 to handle UISections object with nested citations.
    """
    try:
        company = request.form.get("company", "").strip()
        days_back = int(request.form.get("days_back", 7))
        
        if not company:
            return render_template("news_simple.html", error="Please enter a company name or ticker symbol")

        ticker, company_name = company_ticker_service.get_both_ticker_and_company(company)
        display_name = company_name or ticker or company
        
        logger.info(f"Processing analysis V3: '{company}' → '{display_name}' ({days_back} days)")
        
        results = fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back)

        if not results['success']:
            return render_template("news_simple.html", error=results.get('error', 'No articles found.'))
        
        articles = results['articles']
        metrics = results['metrics']
        
        # ✅ NEW: Directly use the UISections object. No conversion needed.
        summaries_ui = results['summaries']
        article_index_map = results.get('article_index_map', {})

        # Build the source map for the chatbot from the final article list
        source_map_for_chatbot = _build_source_map(articles)

        date_range = f"{(datetime.now() - timedelta(days=days_back)).strftime('%B %d, %Y')} – {datetime.now().strftime('%B %d, %Y')}"
        
        # Cache data for the chatbot
        run_id = str(uuid.uuid4())
        RUN_CACHE[run_id] = {
            "ts": time.time(), "company": display_name, "date_range": date_range,
            "summaries": summaries_ui, "articles": articles, "source_map": source_map_for_chatbot,
            "metrics": metrics
        }
        
        logger.info(f"✅ V3 ANALYSIS COMPLETE for {display_name} (run_id: {run_id[:8]})")
        
        # Pass the rich objects directly to the template
        return render_template(
            "news_results.html",
            company=display_name,
            summaries=summaries_ui, # Pass the full UI object
            articles=articles,
            article_index_map=article_index_map, # Pass the map for rendering
            date_range=date_range,
            metrics=metrics,
            quality_validation=results.get('quality_validation', {}),
            run_id=run_id,
            sources_map_json=source_map_for_chatbot
        )

    except Exception as e:
        logger.error(f"Error in news analysis V3: {e}", exc_info=True)
        return render_template("news_simple.html", error="Analysis temporarily unavailable. Please try again.")
    
@app.route("/api/news/<company>")
@login_required  
def api_news_summary(company):
    """API endpoint for enhanced 30-article analysis with guaranteed AlphaVantage representation."""
    try:
        days_back = request.args.get('days', 7, type=int)
        
        # Validate input
        if days_back < 1 or days_back > 30:
            days_back = 7
        
        # Enhanced company/ticker resolution
        ticker, company_name = company_ticker_service.get_both_ticker_and_company(company)
        display_name = company_name if company_name else ticker if ticker else company
        
        logger.info(f"API request ENHANCED: '{company}' → ticker: '{ticker}', company: '{company_name}' ({days_back} days)")
        
        # Use the enhanced orchestration function
        results = fetch_comprehensive_news_guaranteed_30_enhanced(company, days_back)
        
        # Format for API response with enhanced metrics
        response_data = {
            "company": display_name,
            "original_input": company,
            "resolved_ticker": ticker,
            "resolved_company_name": company_name,
            "summaries": results['summaries'],
            "metadata": {
                "total_articles": results['metrics']['total_articles'],
                "articles_analyzed": results['metrics']['articles_analyzed'],  # Always 30
                "alphavantage_articles": results['metrics']['alphavantage_articles'],
                "nyt_articles": results['metrics']['nyt_articles'],
                "rss_articles": results['metrics']['rss_articles'],
                "google_articles": results['metrics']['google_articles'],
                "premium_sources_count": results['metrics']['premium_sources_count'],
                "high_quality_sources": results['metrics']['high_quality_sources'],
                "premium_coverage": results['metrics']['premium_coverage'],
                "alphavantage_coverage": results['metrics']['alphavantage_coverage'],
                "analysis_quality": results['metrics']['analysis_quality'],
                "response_time_seconds": results['metrics']['response_time'],
                "date_range": f"{(datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}",
                "analysis_timestamp": datetime.now().isoformat(),
                "source_performance": results['source_performance'],
                "success": results['success'],
                "guaranteed_article_count": 30,
                "minimum_alphavantage_target": "25%"
            }
        }
        
        # Include articles if requested
        include_articles = request.args.get('include_articles', 'false').lower() == 'true'
        if include_articles:
            response_data["articles"] = results['articles'][:20]  # Limit for API response
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Enhanced API error for {company}: {str(e)}")
        return jsonify({
            "error": str(e),
            "company": company,
            "metadata": {
                "analysis_timestamp": datetime.now().isoformat(),
                "success": False,
                "enhanced_analysis": True
            }
        }), 500
    
@app.route('/upload', methods=['GET'])
@login_required
def upload_view():
    # Check if Google auth is set up
    google_auth_ready = os.path.exists('token.pickle')
    
    # Check if database is initialized and has data
    has_data = False
    try:
        initialize_database()
        dates = get_all_report_dates()
        has_data = len(dates) > 0
    except Exception as e:
        logger.error(f"Error checking database: {str(e)}")
    
    return render_template('index.html', 
                          google_auth_ready=google_auth_ready,
                          has_data=has_data)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    # Check if Google auth is set up
    if not os.path.exists('token.pickle'):
        flash('Please set up Google Authentication first.', 'danger')
        return redirect(url_for('upload_view'))

    if 'file' not in request.files:
        flash('No file part in the request.', 'danger')
        return redirect(url_for('upload_view'))
    
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('upload_view'))

    # Visualization options are removed from UI, so use defaults
    visualization_options = {
        'basic': True, 'heatmap': True, 'timeseries': True, 'industry': True
    }

    results = {}
    processed_successfully_count = 0
    first_processed_report_type = None

    # SIMPLIFIED: Process each file individually, even if multiple files
    for file_idx, file in enumerate(files):
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            try:
                file.save(filepath)
                logger.info(f"File {filename} saved to {filepath}")

                # Determine report type for the redirect (use the first file's type)
                if first_processed_report_type is None:
                    try:
                        detected_type = ReportTypeFactory.detect_report_type(filepath)
                        first_processed_report_type = detected_type
                        logger.info(f"Detected report type for {filename} as {first_processed_report_type}")
                    except Exception as e:
                        logger.error(f"Could not detect report type for {filename}: {e}")
                        first_processed_report_type = "Manufacturing" 

                # Process each file individually
                logger.info(f"Processing file: {filename} of type {first_processed_report_type}")
                process_result = process_single_pdf(filepath, visualization_options)
                
                if process_result:
                    results[filename] = "Success"
                    processed_successfully_count += 1
                    logger.info(f"Successfully processed {filename}")
                else:
                    results[filename] = "Failed"
                    logger.error(f"Failed to process {filename}")

                # Clean up the uploaded file immediately after processing
                try:
                    os.remove(filepath)
                    logger.info(f"Removed uploaded file: {filepath}")
                except OSError as e:
                    logger.warning(f"Could not delete uploaded file {filepath}: {e}")

            except Exception as e:
                logger.error(f"Error processing {filename}: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                results[filename] = f"Error: {str(e)}"
                
                # Try to clean up on error
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except:
                    pass

        elif file.filename:
            results[file.filename] = "File type not allowed"

    # Flash messages for overall status
    total_files = len(results)
    if total_files > 0:
        if processed_successfully_count == total_files:
            flash("All files processed successfully!", "success")
        elif processed_successfully_count > 0:
            flash(f"Processing complete. {processed_successfully_count} succeeded, {total_files - processed_successfully_count} failed.", "warning")
        else:
            flash("File processing failed for all files.", "danger")
    else:
        flash("No valid files were processed.", "info")
        
    # Redirect to dashboard
    if first_processed_report_type:
        logger.info(f"Redirecting to dashboard with report_type: {first_processed_report_type}")
        return redirect(url_for('dashboard', report_type=first_processed_report_type))
    else:
        logger.info("Redirecting to dashboard without specific report_type.")
        return redirect(url_for('dashboard'))

@app.route('/setup-google')
def setup_google():
    try:
        # Get the auth URL
        auth_url = get_google_auth_url()
        if not auth_url:
            flash('Error setting up Google authentication.')
            return redirect(url_for('index'))
        
        # Redirect to Google's auth page
        return redirect(auth_url)
    except Exception as e:
        flash(f'Error with Google authentication: {str(e)}')
        return redirect(url_for('index'))

@app.route('/oauth2callback')
def oauth2callback():
    try:
        # Get state and code from query parameters
        state = request.args.get('state')
        code = request.args.get('code')
        
        if not state or not code:
            flash('Invalid authentication response', 'danger')
            return redirect(url_for('landing'))
        
        # Complete the authentication flow
        creds = finish_google_auth(state, code)
        
        if creds:
            # Set authenticated session
            session['authenticated'] = True
            flash('Google Sheets authentication successful!', 'success')
            
            # Redirect to original URL if it exists
            next_url = session.pop('next_url', None)
            if next_url and 'upload' in next_url:
                # Don't pass the flash message to upload page
                session['_flashes'] = [(cat, msg) for cat, msg in session.get('_flashes', []) 
                                      if msg != 'Google Sheets authentication successful!']
            
            if next_url:
                return redirect(next_url)
            return redirect(url_for('index'))
        else:
            flash('Google Sheets authentication failed.', 'danger')
            return redirect(url_for('landing'))
    except Exception as e:
        flash(f'Error with Google authentication: {str(e)}', 'danger')
        return redirect(url_for('landing'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        # Get report_type from query parameter, default to Manufacturing
        report_type = request.args.get('report_type', 'Manufacturing')
        
        # Validate report_type
        valid_report_types = ['Manufacturing', 'Services']
        if report_type not in valid_report_types:
            report_type = 'Manufacturing'
        
        # REMOVED: Don't auto-redirect if report_type not in args - this causes issues
        # Instead, just use the default and let the frontend handle the state
        
        # Get PMI heatmap data from database for the specified report type
        heatmap_data = get_pmi_data_by_month(24, report_type)  # Get last 24 months of data
        
        # Get all available indices for this report type
        indices = get_all_indices(report_type)
        
        # Get all report dates for this report type
        report_dates = get_all_report_dates(report_type)
        
        # Get available report types directly from database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT report_type 
                FROM reports 
                ORDER BY report_type
            """)
            
            available_report_types = [row['report_type'] for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logger.error(f"Error getting report types: {str(e)}")
            available_report_types = ["Manufacturing", "Services"]  # Default fallback
        
        # Include report_type in template context
        return render_template('dashboard.html', 
                           heatmap_data=heatmap_data,
                           indices=indices,
                           report_dates=report_dates,
                           report_type=report_type,
                           available_report_types=available_report_types)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error loading dashboard: {str(e)}")
        return redirect(url_for('upload_view'))
    
@app.route('/api/index_trends/<index_name>')
def get_index_trends(index_name):
    try:
        # Get optional parameters
        months = request.args.get('months', 24, type=int)
        report_type = request.args.get('report_type')
        
        # Get time series data for the specified index
        time_series_data = get_index_time_series(index_name, months, report_type)
        
        # Return as JSON
        return jsonify(time_series_data)
    except Exception as e:
        logger.error(f"Error getting index trends: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/industry_status/<index_name>')
def get_industry_status(index_name):
    try:
        # Get optional parameters
        months = request.args.get('months', 12, type=int)
        report_type = request.args.get('report_type')
        debug = request.args.get('debug', False, type=bool)

        logger.info(f"In industry_status, report_type is: {report_type}")
        
        if debug:
            logger.info(f"Fetching industry status for {index_name}, {months} months, report type: {report_type}")
            
        industry_data = get_industry_status_over_time(index_name, months, report_type)
        
        if debug and not industry_data['industries']:
            logger.warning(f"No industry data found for {index_name}")
            
        # Ensure all standard industries are included based on report type
        standard_industries = get_standard_industries(report_type)
        
        # Add any missing standard industries with neutral status
        if 'industries' in industry_data:
            dates = industry_data.get('dates', [])
            for industry in standard_industries:
                if industry not in industry_data['industries']:
                    industry_data['industries'][industry] = {}
                    for date in dates:
                        industry_data['industries'][industry][date] = {
                            'status': 'Neutral',
                            'category': 'Not Reported'
                        }
        
        # Fetch rank information for the industries from the database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Find most recent report date with optional report_type filter
            query = """
                SELECT report_date FROM reports 
                {}
                ORDER BY report_date DESC LIMIT 1
            """
            
            params = []
            if report_type:
                query = query.format("WHERE report_type = ?")
                params = [report_type]
            else:
                query = query.format("")
                
            cursor.execute(query, params)
            latest_date_row = cursor.fetchone()
            
            if latest_date_row:
                latest_date = latest_date_row['report_date']
                
                # Get ranks for each industry in this index
        
                # Base query for ranks
                rank_query_sql = """
                    SELECT industry_name, rank 
                    FROM industry_status 
                    WHERE index_name = ? AND report_date = ?
                """
                # Base parameters for ranks
                rank_params_list = [index_name, latest_date]
                
                # Conditionally add report_type filter if it was provided
                # This ensures the ranks are fetched for the same report_type context
                # as the latest_date, assuming industry_status has a report_type column.
                if report_type: 
                    rank_query_sql += " AND report_type = ?"
                    rank_params_list.append(report_type)
                    
                cursor.execute(rank_query_sql, tuple(rank_params_list)) # Use tuple for db params
                
                # Add rank to response
                ranks = {row['industry_name']: row['rank'] for row in cursor.fetchall()}
                industry_data['ranks'] = ranks
            
            conn.close()
        except Exception as e:
            logger.error(f"Error fetching ranks: {str(e)}")
            
        return jsonify(industry_data)
    except Exception as e:
        logger.error(f"Error getting industry status: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "industries": {}, "dates": []}), 500
     
@app.route('/api/industry_alphabetical/<index_name>')
def get_industry_alphabetical(index_name):
    try:
        # Get industry status data for the specified index (last 12 months)
        industry_data = get_industry_status_over_time(index_name, 12)
        
        # Return as JSON
        return jsonify(industry_data)
    except Exception as e:
        logger.error(f"Error getting alphabetical industry status: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/industry_numerical/<index_name>')
def get_industry_numerical(index_name):
    try:
        # Get industry status data for the specified index (last 12 months)
        industry_data = get_industry_status_over_time(index_name, 12)
        
        # Return as JSON with additional ranking information
        return jsonify(industry_data)
    except Exception as e:
        logger.error(f"Error getting numerical industry status: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/heatmap_data', defaults={'months': 24})
@app.route('/api/heatmap_data/<int:months>')
@app.route('/api/heatmap_data/all')
def api_heatmap_data(months=None):
    try:
        # Get report_type from query params (optional)
        report_type = request.args.get('report_type')
        
        # DEBUG: Log what we're looking for
        logger.info(f"API heatmap_data called with report_type: {report_type}, months: {months}")
        
        # Validate report_type
        if report_type and report_type not in ['Manufacturing', 'Services']:
            logger.warning(f"Invalid report_type: {report_type}, defaulting to Manufacturing")
            report_type = 'Manufacturing'
        
        if months == 'all':
            months = None
        
        # Convert string 'months' to integer if needed
        if isinstance(months, str) and months.isdigit():
            months = int(months)
            
        # DEBUG: Check what's actually in the database
        from db_utils import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check all reports in database
        cursor.execute("SELECT report_date, month_year, report_type FROM reports ORDER BY report_date DESC LIMIT 10")
        all_reports = cursor.fetchall()
        logger.info(f"All reports in DB: {[dict(row) for row in all_reports]}")
        
        # Check specific report type
        if report_type:
            cursor.execute("SELECT COUNT(*) as count FROM reports WHERE report_type = ?", (report_type,))
            count_result = cursor.fetchone()
            logger.info(f"Count of {report_type} reports: {count_result['count']}")
        
        conn.close()
            
        logger.info(f"Fetching heatmap data for report_type: {report_type}, months: {months}")
        heatmap_data = get_pmi_data_by_month(months, report_type)
        
        logger.info(f"Retrieved {len(heatmap_data) if heatmap_data else 0} records from get_pmi_data_by_month")
        
        if not heatmap_data:
            logger.warning(f"No heatmap data found for report_type: {report_type}")
            return jsonify([])  # Return empty array instead of null
            
        return jsonify(heatmap_data)
    except Exception as e:
        logger.error(f"Error getting heatmap data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    

@app.route('/api/all_indices')
def get_indices_list():
    try:
        # Get optional report_type parameter
        report_type = request.args.get('report_type')
        
        # Validate report_type
        if report_type and report_type not in ['Manufacturing', 'Services']:
            logger.warning(f"Invalid report_type: {report_type}, defaulting to Manufacturing")
            report_type = 'Manufacturing'
        
        logger.info(f"Fetching indices for report_type: {report_type}")
        
        # Get list of indices directly from database
        indices = get_all_indices(report_type)
        
        if not indices:
            logger.warning(f"No indices found for report_type: {report_type}, using fallback")
            # Return at least a fallback list
            if report_type == 'Services':
                indices = [
                    'Services PMI', 'Business Activity', 'New Orders', 'Employment', 'Supplier Deliveries',
                    'Inventories', 'Inventory Sentiment', 'Prices', 'Backlog of Orders',
                    'New Export Orders', 'Imports'
                ]
            else:
                indices = [
                    'Manufacturing PMI', 'New Orders', 'Production', 'Employment', 'Supplier Deliveries',
                    'Inventories', 'Customers\' Inventories', 'Prices', 'Backlog of Orders',
                    'New Export Orders', 'Imports'
                ]
        
        return jsonify(indices)
    except Exception as e:
        logger.error(f"Error getting indices list: {str(e)}")
        logger.error(traceback.format_exc())
        # Return at least a fallback list
        fallback_indices = []
        if report_type == 'Services':
            fallback_indices = [
                'Services PMI', 'Business Activity', 'New Orders', 'Employment', 'Supplier Deliveries',
                'Inventories', 'Inventory Sentiment', 'Prices', 'Backlog of Orders',
                'New Export Orders', 'Imports'
            ]
        else:
            fallback_indices = [
                'Manufacturing PMI', 'New Orders', 'Production', 'Employment', 'Supplier Deliveries',
                'Inventories', 'Customers\' Inventories', 'Prices', 'Backlog of Orders',
                'New Export Orders', 'Imports'
            ]
        return jsonify(fallback_indices)
    
def get_standard_industries(report_type_str: Optional[str]) -> List[str]:
    """
    Get the standard list of industries based on report type, primarily from config.
    """
    # Ensure report_type is a string and capitalize it
    if report_type_str is None:
        report_type = "Manufacturing"
    else:
        report_type = str(report_type_str).strip().capitalize()
    
    canonical_list = config_loader.get_canonical_industries(report_type)
    if canonical_list:
        logger.debug(f"Using canonical industries from config for report type: {report_type}")
        return canonical_list

    # Fallback to hardcoded lists if config is missing or empty for the type
    logger.warning(f"Canonical industries not found in config for {report_type}. Using hardcoded fallback.")
    if report_type == 'Services':
        return [
            "Accommodation & Food Services", 
            "Agriculture, Forestry, Fishing & Hunting",
            "Arts, Entertainment & Recreation", 
            "Construction", 
            "Educational Services",
            "Finance & Insurance", 
            "Health Care & Social Assistance", 
            "Information",
            "Management of Companies & Support Services", 
            "Mining", 
            "Professional, Scientific & Technical Services",
            "Public Administration", 
            "Real Estate, Rental & Leasing", 
            "Retail Trade",
            "Transportation & Warehousing", 
            "Utilities", 
            "Wholesale Trade",
            "Other Services"
        ]
    else:  # Manufacturing or default
        return [
            "Apparel, Leather & Allied Products",
            "Chemical Products",
            "Computer & Electronic Products",
            "Electrical Equipment, Appliances & Components",
            "Fabricated Metal Products",
            "Food, Beverage & Tobacco Products",
            "Furniture & Related Products",
            "Machinery",
            "Miscellaneous Manufacturing",
            "Nonmetallic Mineral Products",
            "Paper Products",
            "Petroleum & Coal Products",
            "Plastics & Rubber Products",
            "Primary Metals",
            "Printing & Related Support Activities",
            "Textile Mills",
            "Transportation Equipment",
            "Wood Products"
        ]
    
@app.route('/api/report_types')
def get_report_types():
    """Get available report types."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT report_type 
            FROM reports 
            ORDER BY report_type
        """)
        
        report_types = [row['report_type'] for row in cursor.fetchall()]
        conn.close()
        
        return jsonify(report_types)
    except Exception as e:
        logger.error(f"Error getting report types: {str(e)}")
        return jsonify(["Manufacturing", "Services"]), 500  # Default fallback
    
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    """Handle chatbot questions about specific analysis runs."""
    
    # Validate content type
    if not request.content_type or not request.content_type.startswith("application/json"):
        return jsonify({"error": "Content-Type must be application/json"}), 415
    
    # Parse request
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON in request body"}), 400
    
    # Extract and validate parameters
    company = payload.get("company", "").strip()
    question = payload.get("question", "").strip()
    run_id = payload.get("run_id", "").strip()
    conversation_history = payload.get("conversation_history", []) 
    window_days = payload.get("window_days", 30)
    verify_with_web_raw = payload.get("verify_with_web", False)
    if isinstance(verify_with_web_raw, str):
        verify_with_web = verify_with_web_raw.lower() in ('true', '1', 'yes')
    else:
        verify_with_web = bool(verify_with_web_raw)
    
    # Input validation
    if not question:
        return jsonify({"error": "Question is required"}), 400
    
    if not company:
        return jsonify({"error": "Company name is required"}), 400
    
    if not run_id:
        return jsonify({"error": "Analysis run_id is required"}), 400
    
    if len(question) > 500:
        return jsonify({"error": "Question too long (max 500 characters)"}), 400
    
    try:
        window_days = int(window_days)
        if not (1 <= window_days <= 365):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "window_days must be between 1 and 365"}), 400
    
    # Retrieve cached analysis data
    run_data = RUN_CACHE.get(run_id)
    if not run_data:
        return jsonify({
            "error": "Analysis session expired. Please re-run the analysis and try again."
        }), 410
    
    # Check if cached data matches request
    if run_data["company"] != company:
        return jsonify({
            "error": "Company mismatch with cached analysis"
        }), 400
    
    # Handle missing Anthropic availability or API key
    if not ANTHROPIC_AVAILABLE:
        return jsonify({
            "answer": f"Chat functionality requires the 'anthropic' package. "
                     f"Based on the analysis for {company}, please refer to the summary sections above for insights.",
            "citations": []
        }), 200
    
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        return jsonify({
            "answer": f"Chat functionality requires ANTHROPIC_API_KEY to be configured. "
                     f"Based on the analysis for {company}, please refer to the summary sections above for insights.",
            "citations": []
        }), 200
    
    # Compose context for Claude
    try:
        context = _compose_context(run_data)
    except Exception as e:
        logger.error(f"Error composing context: {e}")
        return jsonify({"error": "Failed to prepare analysis context"}), 500
    
    # Prepare verification note
    verify_note = ""
    if verify_with_web:
        verify_note = "\n\n(User requested web verification. If the context lacks current data, note this limitation.)"
    
    # Call Claude (create client locally following existing pattern)
    try:
        # Use ClaudeWebSearchEngine for web search capabilities
        web_search_engine = ClaudeWebSearchEngine(anthropic_api_key)

        # Handle async call properly with conversation history
        import asyncio
        try:
            # Check if we're in an async context
            loop = asyncio.get_running_loop()
            # Run in thread pool to avoid blocking
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, 
                    web_search_engine.chat_with_web_search(
                        question, context, company, conversation_history  # ✅ ADD conversation_history
                    )
                )
                chat_result = future.result(timeout=55)  # Increased timeout
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            chat_result = asyncio.run(
                web_search_engine.chat_with_web_search(
                    question, context, company, conversation_history  # ✅ ADD conversation_history
                )
            )
        
        answer = chat_result.get('answer', 'I was unable to generate a response.')
        citations = chat_result.get('citations', [])
        
        if not answer:
            answer = "I wasn't able to generate a response. Please try rephrasing your question."
            
    except Exception as e:
        # Enhanced error handling for web search
        logger.error(f"Chat with web search error: {e}")
        
        # Fallback to basic Claude without web search
        try:
            anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
            
            fallback_response = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                temperature=0.2,
                system=CHATBOT_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user", 
                        "content": f"QUESTION: {question}{verify_note}\n\nANALYSIS CONTEXT:\n{context}"
                    }
                ],
            )
            
            # Extract answer text from fallback
            answer_parts = []
            for block in fallback_response.content:
                if block.type == "text":
                    answer_parts.append(block.text)
            
            answer = "\n".join(answer_parts).strip()
            citations = []
            
            if not answer:
                answer = "I wasn't able to generate a response. Please try rephrasing your question."
            
            logger.info(f"Used fallback Claude (no web search) for {company}")
            
        except Exception as fallback_error:
            logger.error(f"Both web search and fallback failed: {fallback_error}")
            return jsonify({
                "error": "AI service temporarily unavailable. Please try again."
            }), 502
    
   # Build citations (prefer Claude tc → fallback to [S#] in text)
    source_map = run_data["source_map"]
    tc = chat_result.get("citations") or []

    def _num_from_tc(c):
        if isinstance(c, dict):
            if "s" in c and str(c["s"]).isdigit():
                return int(c["s"])
            if "source_number" in c and str(c["source_number"]).isdigit():
                return int(c["source_number"])
            if isinstance(c.get("source"), str) and c["source"].upper().startswith("S") and c["source"][1:].isdigit():
                return int(c["source"][1:])
        return None

    hydrated = []
    seen = set()

    # 1) Use Claude's tc first, but hydrate title/url from our map
    for c in tc:
        n = _num_from_tc(c)
        if not n or n in seen:
            continue
        meta = source_map.get(str(n), {})
        hydrated.append({
            "s": n,
            "title": c.get("title") or meta.get("title") or f"Source S{n}",
            "url":   c.get("url")   or meta.get("url")   or ""
        })
        seen.add(n)

    # 2) Fallback to parsing [S#] tokens in the answer text
    if not hydrated:
        max_source_id = len(run_data["articles"])
        for n in _extract_citations(answer, max_source_id):
            if n in seen:
                continue
            meta = source_map.get(str(n), {})
            hydrated.append({
                "s": n,
                "title": meta.get("title") or f"Source S{n}",
                "url":   meta.get("url")   or ""
            })
            seen.add(n)

    citations = hydrated

    # Log the interaction
    logger.info(
        f"Chat query for {company} (run_id: {run_id[:8]}): '{question[:50]}...' -> {len(citations)} citations "
        f"(tc={len(tc)}, hydrated={len(citations)})"
    )
    
    return jsonify({
        "answer": answer,
        "citations": citations
    }), 200

@app.route('/admin/monitoring')
@login_required
def monitoring_dashboard():
    from monitoring import get_performance_dashboard
    dashboard_data = get_performance_dashboard()
    return render_template('monitoring_dashboard.html', data=dashboard_data)

@app.route('/api/monitoring/performance')
@login_required
def api_monitoring_performance():
    from monitoring import get_performance_dashboard
    return jsonify(get_performance_dashboard())

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# Blueprint registration for web insights
try:
    from web_insight import web_insight_bp
    app.register_blueprint(web_insight_bp, url_prefix='/web_insight')
    
    # Add redirect route
    @app.route('/web_insights')
    def web_insights_redirect():
        """Redirect to the web insights dashboard."""
        return redirect(url_for('web_insight.index'))
    
    print("Web Insights module loaded successfully")
except ImportError as e:
    print(f"Note: Web Insights module not available: {e}")

# Ensure app is available at the module level
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)