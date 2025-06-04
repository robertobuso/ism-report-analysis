import os
import base64
import tempfile
import logging
import sys
import traceback
import uuid
import threading
from db_utils import initialize_database, get_pmi_data_by_month, get_index_time_series, get_industry_status_over_time, get_all_indices, get_all_report_dates, get_db_connection
from config_loader import config_loader 
from typing import List, Optional

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

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        # Return a more specific error to the client if it's an AJAX request,
        # or flash and redirect for traditional form submission.
        # For now, sticking to flash and redirect.
        flash('Please set up Google Authentication first.', 'danger')
        return redirect(url_for('upload_view'))

    if 'file' not in request.files:
        flash('No file part in the request.', 'danger')
        return redirect(url_for('upload_view'))
    
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('upload_view'))

    # Visualization options are removed from UI, so use defaults or remove
    visualization_options = {
        'basic': True, 'heatmap': True, 'timeseries': True, 'industry': True
    }

    results = {}
    saved_files_paths = []
    processed_successfully_count = 0
    first_processed_report_type = None # To store the report type for redirect

    for file_idx, file in enumerate(files):
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Use a unique name for each uploaded file to prevent overwrites if multiple users upload
            # or if the same filename is uploaded again before cleanup.
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            try:
                file.save(filepath)
                saved_files_paths.append(filepath)
                logger.info(f"File {filename} saved to {filepath}")

                # Determine report type for the redirect (use the first file's type)
                if first_processed_report_type is None:
                    try:
                        detected_type = ReportTypeFactory.detect_report_type(filepath)
                        first_processed_report_type = detected_type
                        logger.info(f"Detected report type for {filename} as {first_processed_report_type}")
                    except Exception as e:
                        logger.error(f"Could not detect report type for {filename}: {e}")
                        # Default if detection fails, or handle error appropriately
                        first_processed_report_type = "Manufacturing" 

                # Process single file immediately (if only one)
                if len(files) == 1:
                    logger.info(f"Processing single file: {filename} of type {first_processed_report_type}")
                    process_result = process_single_pdf(filepath, visualization_options) # process_single_pdf now determines type internally
                    if process_result:
                        results[filename] = "Success"
                        processed_successfully_count += 1
                    else:
                        results[filename] = "Failed"
                else:
                    # Mark for batch processing (actual processing happens later for batch)
                    results[filename] = "Pending Batch" # This status will be updated after batch processing

            except Exception as e:
                logger.error(f"Failed to save or initially process {filename}: {e}")
                results[filename] = f"Error: Save/Initial processing failed"
                # Do not flash here, accumulate results and flash once

        elif file.filename: # If a file was selected but disallowed
            results[file.filename] = "File type not allowed"


    # If multiple files were uploaded, process them as a batch
    if len(files) > 1:
        logger.info(f"Processing batch of {len(saved_files_paths)} files.")
        # For batch, we'll make a temporary directory containing only successfully saved files
        valid_files_for_batch_processing = [p for p in saved_files_paths if os.path.exists(p)]

        if valid_files_for_batch_processing:
            temp_dir_for_batch = None
            try:
                # Create a temporary directory to copy files to for batch processing
                temp_dir_for_batch = tempfile.mkdtemp(prefix='ism_batch_')
                for original_path in valid_files_for_batch_processing:
                    fname = os.path.basename(original_path).split('_', 1)[-1] # Get original filename
                    temp_path = os.path.join(temp_dir_for_batch, fname)
                    with open(original_path, 'rb') as src, open(temp_path, 'wb') as dst:
                        dst.write(src.read())
                
                # Process the batch from the temporary directory
                batch_result_data = process_multiple_pdfs(temp_dir_for_batch) # process_multiple_pdfs will handle types internally
                logger.info(f"Batch processing function returned: {batch_result_data}")

                if isinstance(batch_result_data, dict) and batch_result_data.get('success'):
                    batch_file_results = batch_result_data.get('results', {})
                    for fname, status_obj in batch_file_results.items(): # Assuming status_obj might be more complex
                        # The key in batch_file_results should match the original filename
                        original_fname_key = next((k for k in results if fname in k), fname) # find original key
                        
                        # Extract boolean success from status_obj if it's complex, or use directly
                        # Let's assume process_multiple_pdfs returns a simple True/False for now per file.
                        # If it's a dict like {'status': True, 'report_type': 'Manufacturing'}, adapt here.
                        is_success = status_obj # Adjust if status_obj is more complex

                        if is_success:
                            results[original_fname_key] = "Success"
                            processed_successfully_count += 1
                            # If first_processed_report_type wasn't set by a single file, try to get it from batch
                            if first_processed_report_type is None and isinstance(status_obj, dict) and status_obj.get('report_type'):
                                first_processed_report_type = status_obj['report_type']
                        else:
                            results[original_fname_key] = "Failed in Batch"
                    
                    # Update any remaining "Pending Batch" to "Success" if the overall batch was a success
                    # This might need finer-grained status from process_multiple_pdfs
                    # For now, let's assume individual statuses are accurate.

                else:
                    logger.warning("Batch processing failed or returned unexpected data.")
                    for original_path in valid_files_for_batch_processing:
                        fname = os.path.basename(original_path).split('_', 1)[-1]
                        original_fname_key = next((k for k in results if fname in k), fname)
                        results[original_fname_key] = "Failed in Batch"
            
            except Exception as e:
                logger.error(f"Error during batch processing: {e}")
                logger.error(traceback.format_exc())
                for original_path in valid_files_for_batch_processing:
                    fname = os.path.basename(original_path).split('_', 1)[-1]
                    original_fname_key = next((k for k in results if fname in k), fname)
                    results[original_fname_key] = "Error: Batch failed"
            finally:
                if temp_dir_for_batch and os.path.exists(temp_dir_for_batch):
                    try:
                        import shutil
                        shutil.rmtree(temp_dir_for_batch)
                        logger.info(f"Cleaned up temp batch directory {temp_dir_for_batch}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup temp batch directory {temp_dir_for_batch}: {e}")
        else:
            logger.info("No valid files to process in batch.")


    # Clean up uploaded files from the app's UPLOAD_FOLDER
    for path in saved_files_paths:
        try:
            os.remove(path)
            logger.info(f"Removed uploaded file: {path}")
        except OSError as e:
            logger.warning(f"Could not delete uploaded file {path}: {e}")

    # Flash messages for overall status
    total_files = len(results)
    if total_files > 0 :
        if processed_successfully_count == total_files:
            flash("All files processed successfully!", "success")
        elif processed_successfully_count > 0:
            flash(f"Processing complete. {processed_successfully_count} succeeded, {total_files - processed_successfully_count} failed.", "warning")
        else:
            flash("File processing failed for all files.", "danger")
    else:
        flash("No valid files were processed.", "info")
        
    # Redirect to dashboard
    # If a report type was determined, use it for the redirect. Otherwise, redirect without it.
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

        # If report_type is not provided in the URL, redirect to include it
        if 'report_type' not in request.args:
            return redirect(url_for('dashboard', report_type=report_type))
        
        # Get PMI heatmap data from database for the specified report type
        heatmap_data = get_pmi_data_by_month(24, report_type)  # Get last 24 months of data
        
        # Get all available indices for this report type
        indices = get_all_indices(report_type)
        
        # Get all report dates for this report type
        report_dates = get_all_report_dates(report_type)
        
        # Include report_type in template context
        return render_template('dashboard.html', 
                           heatmap_data=heatmap_data,
                           indices=indices,
                           report_dates=report_dates,
                           report_type=report_type,
                           available_report_types=get_report_types())
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
        
        if months == 'all':
            months = None
        
        # Convert string 'months' to integer if needed
        if isinstance(months, str) and months.isdigit():
            months = int(months)
            
        heatmap_data = get_pmi_data_by_month(months, report_type)
        return jsonify(heatmap_data)
    except Exception as e:
        logger.error(f"Error getting heatmap data: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/all_indices')
def get_indices_list():
    try:
        # Get optional report_type parameter
        report_type = request.args.get('report_type')
        
        # Get list of indices directly from database
        indices = get_all_indices(report_type)
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