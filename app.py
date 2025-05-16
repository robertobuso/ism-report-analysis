import os
import base64
import tempfile
import logging
import sys
import traceback
import uuid
import threading
from db_utils import initialize_database, get_pmi_data_by_month, get_index_time_series, get_industry_status_over_time, get_all_indices, get_all_report_dates, migrate_database, get_report_type_counts, get_pmi_data_by_type

# Create necessary directories first
os.makedirs("logs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

from auth import login_required, is_authenticated
from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from main import process_single_pdf, process_multiple_pdfs
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

# Run migration function during application startup
def initialize_app():
    try:
        # Initialize and migrate the database
        migrate_database()
        logger.info("Database migration completed successfully")
    except Exception as e:
        logger.error(f"Error during database migration: {str(e)}")
        logger.error(traceback.format_exc())

# Call the initialization function
initialize_app()

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
    
    # Get report type counts for UI
    report_counts = get_report_type_counts()
    
    return render_template('index.html', 
                          google_auth_ready=google_auth_ready,
                          has_data=has_data,
                          report_counts=report_counts)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    # Check if Google auth is set up
    if not os.path.exists('token.pickle'):
        return jsonify({"status": "error", "message": "Please set up Google Authentication first"})
    
    # Check if the post request has the file part
    if 'file' not in request.files:
        flash('No file part in the request.', 'danger')
        return redirect(url_for('upload_view')) # Redirect back on error
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
         flash('No file selected.', 'warning')
         return redirect(url_for('upload_view'))

    visualization_types = request.form.getlist('visualization_types')
    visualization_options = {
        'basic': 'basic' in visualization_types,
        'heatmap': 'heatmap' in visualization_types,
        'timeseries': 'timeseries' in visualization_types,
        'industry': 'industry' in visualization_types
    }

    # Check if report type was specified or if we should auto-detect
    report_type = request.form.get('report_type', 'auto')

    # --- Process Files Directly ---
    results = {}
    saved_files_paths = [] # Keep track for deletion

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(filepath)
                saved_files_paths.append(filepath)
                # Process single file immediately (if only one)
                if len(files) == 1:
                     logger.info(f"Processing single file: {filename}, report_type: {report_type}")
                     process_result = process_single_pdf(filepath, visualization_options, report_type)
                     results[filename] = "Success" if process_result else "Failed"
                else:
                     # Mark for batch processing below
                     results[filename] = "Pending Batch"

            except Exception as e:
                 logger.error(f"Failed to save or initially process {filename}: {e}")
                 results[filename] = f"Error: Save/Initial processing failed"
                 flash(f"Error processing file {filename}. Please check logs.", "danger")

        elif file.filename: # If a file was selected but disallowed
             flash(f"File type not allowed: {file.filename}", "warning")


    # If multiple files were uploaded, process them as a batch
    if len(files) > 1:
         logger.info(f"Processing batch of {len(saved_files_paths)} files.")
         temp_dir = None
         try:
             temp_dir = tempfile.mkdtemp(prefix='ism_batch_sync_')
             for path in saved_files_paths:
                 fname = os.path.basename(path)
                 temp_path = os.path.join(temp_dir, fname)
                 with open(path, 'rb') as src, open(temp_path, 'wb') as dst:
                      dst.write(src.read())

             batch_result_data = process_multiple_pdfs(temp_dir, report_type)
             logger.info("Batch processing function returned.")

             if isinstance(batch_result_data, dict) and batch_result_data.get('success'):
                  batch_file_results = batch_result_data.get('results', {})
                  for fname, status in batch_file_results.items():
                     results[fname] = "Success" if status else "Failed"
                  for fname in results: # Mark remaining pending as success
                     if results[fname] == "Pending Batch": results[fname] = "Success"
                  flash("Batch processed successfully.", "success")
             else:
                  logger.warning("Batch processing failed or returned unexpected data.")
                  for fname in results: results[fname] = "Failed in Batch"
                  flash("Batch processing failed.", "danger")

         except Exception as e:
              logger.error(f"Error during synchronous batch processing: {e}")
              for fname in results: results[fname] = "Error: Batch failed"
              flash("An error occurred during batch processing.", "danger")
         finally:
             if temp_dir and os.path.exists(temp_dir):
                  try:
                      import shutil
                      shutil.rmtree(temp_dir)
                  except Exception as e:
                      logger.error(f"Failed to cleanup temp directory {temp_dir}: {e}")


    # Clean up uploaded files
    for path in saved_files_paths:
        try:
            os.remove(path)
        except OSError as e:
            logger.warning(f"Could not delete uploaded file {path}: {e}")

    # Check results and flash messages (optional)
    success_count = sum(1 for status in results.values() if status == "Success")
    fail_count = len(results) - success_count
    if fail_count > 0:
         flash(f"Processing complete. {success_count} succeeded, {fail_count} failed.", "warning")
    elif success_count > 0:
         flash("All files processed successfully!", "success")
    # If results is empty (e.g., no valid files), maybe add another message

    # --- Redirect to dashboard AFTER processing is complete ---
    return redirect(url_for('dashboard')) # Or index() if that renders dashboard

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
        # Get PMI heatmap data from database
        heatmap_data = get_pmi_data_by_month(24)  # Get last 24 months of data
        
        # Get all available indices
        indices = get_all_indices()
        
        # Get all report dates
        report_dates = get_all_report_dates()
        
        return render_template('dashboard.html', 
                               heatmap_data=heatmap_data,
                               indices=indices,
                               report_dates=report_dates)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error loading dashboard: {str(e)}")
        return redirect(url_for('upload_view'))
    
@app.route('/dashboard/<report_type>')
@login_required
def filtered_dashboard(report_type):
    """Display a dashboard filtered by report type."""
    try:
        # Validate report_type
        if report_type not in ['manufacturing', 'service', 'combined']:
            return redirect(url_for('dashboard'))
        
        # Get PMI heatmap data from database based on report type
        if report_type == 'manufacturing':
            heatmap_data = get_pmi_data_by_type('Manufacturing', 24)
        elif report_type == 'service':
            heatmap_data = get_pmi_data_by_type('Service', 24)
        else:  # combined
            heatmap_data = get_pmi_data_by_month(24)  # Get all types
        
        # Get all available indices (might differ by report type)
        if report_type == 'manufacturing':
            indices = get_all_indices('Manufacturing')
        elif report_type == 'service':
            indices = get_all_indices('Service')
        else:
            indices = get_all_indices()  # Get all indices
        
        # Get all report dates, possibly filtered by type
        if report_type != 'combined':
            report_dates = get_report_dates_by_type(report_type.capitalize())
        else:
            report_dates = get_all_report_dates()
        
        # Get counts for navigation badges
        report_counts = get_report_type_counts()
        
        return render_template('dashboard.html', 
                           heatmap_data=heatmap_data,
                           indices=indices,
                           report_dates=report_dates,
                           report_type=report_type,
                           report_counts=report_counts)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error loading dashboard: {str(e)}")
        return redirect(url_for('upload_view'))

@app.route('/api/compare_pmi')
def compare_pmi():
    """API endpoint for comparing Manufacturing and Service PMI."""
    try:
        # Get data for both report types, limited to same timeframe
        manufacturing_data = get_pmi_data_by_type('Manufacturing', 24)
        service_data = get_pmi_data_by_type('Service', 24)
        
        # Prepare the comparison data
        comparison_data = {
            'dates': [],
            'manufacturing': [],
            'service': []
        }
        
        # Get all unique dates from both datasets
        all_dates = set()
        for data in manufacturing_data:
            all_dates.add(data['month_year'])
        for data in service_data:
            all_dates.add(data['month_year'])
        
        # Sort dates
        all_dates = sorted(list(all_dates))
        comparison_data['dates'] = all_dates
        
        # Fill in the manufacturing data
        for date in all_dates:
            # Find matching date in manufacturing data
            match = next((d for d in manufacturing_data if d['month_year'] == date), None)
            if match and 'indices' in match and 'Manufacturing PMI' in match['indices']:
                comparison_data['manufacturing'].append(float(match['indices']['Manufacturing PMI']['value']))
            else:
                comparison_data['manufacturing'].append(None)  # No data for this date
        
        # Fill in the service data
        for date in all_dates:
            # Find matching date in service data
            match = next((d for d in service_data if d['month_year'] == date), None)
            if match and 'indices' in match and 'Services PMI' in match['indices']:
                comparison_data['service'].append(float(match['indices']['Services PMI']['value']))
            else:
                comparison_data['service'].append(None)  # No data for this date
        
        return jsonify(comparison_data)
    except Exception as e:
        logger.error(f"Error comparing PMI data: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/index_trends/<index_name>')
def get_index_trends(index_name):
    try:
        # Get time series data for the specified index (last 24 months)
        time_series_data = get_index_time_series(index_name, 24)
        
        # Return as JSON
        return jsonify(time_series_data)
    except Exception as e:
        logger.error(f"Error getting index trends: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/industry_status/<index_name>')
def get_industry_status(index_name):
    try:
        # Get industry status data for the specified index (last 12 months)
        months = request.args.get('months', 12, type=int)
        debug = request.args.get('debug', False, type=bool)
        
        if debug:
            logger.info(f"Fetching industry status for {index_name}, {months} months")
            
        industry_data = get_industry_status_over_time(index_name, months)
        
        if debug and not industry_data['industries']:
            logger.warning(f"No industry data found for {index_name}")
            
        # Ensure all standard industries are included
        standard_industries = [
            "Chemical",
            "Computer & Electronic",
            "Electrical Equipment, Appliances & Components",
            "Fabricated Metal",
            "Food, Beverage & Tobacco",
            "Furniture & Related",
            "Machinery",
            "Miscellaneous Manufacturing",
            "Nonmetallic Mineral",
            "Paper",
            "Petroleum & Coal",
            "Plastics & Rubber",
            "Primary Metals",
            "Printing & Related Support Activities",
            "Textile Mills",
            "Transportation Equipment",
            "Wood"
        ]
        
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
        from db_utils import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Find most recent report date
        cursor.execute("""
            SELECT report_date FROM reports ORDER BY report_date DESC LIMIT 1
        """)
        latest_date_row = cursor.fetchone()
        
        if latest_date_row:
            latest_date = latest_date_row['report_date']
            
            # Get ranks for each industry in this index
            cursor.execute("""
                SELECT industry_name, rank 
                FROM industry_status 
                WHERE index_name = ? AND report_date = ?
            """, (index_name, latest_date))
            
            # Add rank to response
            ranks = {row['industry_name']: row['rank'] for row in cursor.fetchall()}
            industry_data['ranks'] = ranks
        
        conn.close()
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
    
@app.route('/api/heatmap_data/<int:months>')
@app.route('/api/heatmap_data/all')
def api_heatmap_data(months=None):
    try:
        if months == 'all':
            months = None
        heatmap_data = get_pmi_data_by_month(months)
        return jsonify(heatmap_data)
    except Exception as e:
        logger.error(f"Error getting heatmap data: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/all_indices')
def get_indices_list():
    try:
        # Get list of indices directly from database
        indices = get_all_indices()
        return jsonify(indices)
    except Exception as e:
        logger.error(f"Error getting indices list: {str(e)}")
        logger.error(traceback.format_exc())
        # Return at least a fallback list
        fallback_indices = [
            'New Orders', 'Production', 'Employment', 'Supplier Deliveries',
            'Inventories', 'Customers\' Inventories', 'Prices', 'Backlog of Orders',
            'New Export Orders', 'Imports'
        ]
        return jsonify(fallback_indices)

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