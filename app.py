import os
import tempfile
import logging
import sys
import traceback
from db_utils import initialize_database, get_pmi_data_by_month, get_index_time_series, get_industry_status_over_time, get_all_indices, get_all_report_dates

# Create necessary directories first
os.makedirs("logs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from main import process_single_pdf, process_multiple_pdfs
from google_auth import get_google_sheets_service, get_google_auth_url, finish_google_auth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/app.log'
)
logger = logging.getLogger(__name__)

# Add console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# Create Flask application
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Set upload folder and maximum file size
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    try:
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
def upload_file():
    # Check if Google auth is set up
    if not os.path.exists('token.pickle'):
        flash('Please set up Google Authentication first')
        return redirect(url_for('upload_view'))
    
    # Check if the post request has the file part
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('upload_view'))
    
    files = request.files.getlist('file')
    
    if len(files) == 1 and files[0].filename == '':
        flash('No selected file')
        return redirect(url_for('upload_view'))
    
    # Get visualization options
    visualization_types = request.form.getlist('visualization_types')
    visualization_options = {
        'basic': 'basic' in visualization_types,
        'heatmap': 'heatmap' in visualization_types,
        'timeseries': 'timeseries' in visualization_types,
        'industry': 'industry' in visualization_types
    }

    # Log what we're storing
    logger.info(f"Storing visualization options in session: {visualization_options}")
    session['visualization_options'] = visualization_options
    
    # Store visualization options in session
    session['visualization_options'] = visualization_options
    
    # Process files
    saved_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            saved_files.append(filepath)
    
    if not saved_files:
        flash('No valid files uploaded')
        return redirect(url_for('upload_view'))
    
    # Store file paths in session
    session['files'] = saved_files
    
    return redirect(url_for('process'))

@app.route('/process')
def process():
    files = session.get('files', [])
    if not files:
        flash('No files to process')
        return redirect(url_for('upload_view'))
    
    # Make sure to get this from the session
    visualization_options = session.get('visualization_options', {
        'basic': True,
        'heatmap': True,
        'timeseries': True,
        'industry': True
    })
    
    # Explicitly log what options were retrieved
    logger.info(f"Processing with visualization options: {visualization_options}")
    
    results = {}
    
    # Process each file
    for filepath in files:
        try:
            filename = os.path.basename(filepath)
            if len(files) == 1:
                # If visualization options exist, pass them; otherwise, don't
                if visualization_options:
                    result = process_single_pdf(filepath, visualization_options)
                else:
                    result = process_single_pdf(filepath)
                results[filename] = "Success" if result else "Failed"
            else:
                # Just store the files to process them together
                pass
        except Exception as e:
            logger.error(f"Error processing {filepath}: {str(e)}")
            results[filename] = f"Error: {str(e)}"
    
    if len(files) > 1:
        # Process all PDFs together
        try:
            temp_dir = tempfile.mkdtemp()
            for filepath in files:
                filename = os.path.basename(filepath)
                temp_path = os.path.join(temp_dir, filename)
                with open(filepath, 'rb') as src_file:
                    with open(temp_path, 'wb') as dst_file:
                        dst_file.write(src_file.read())
            
            batch_result = process_multiple_pdfs(temp_dir)
            if isinstance(batch_result, dict) and batch_result.get('success'):
                for filename, status in batch_result.get('results', {}).items():
                    results[filename] = "Success" if status else "Failed"
            else:
                for filepath in files:
                    filename = os.path.basename(filepath)
                    results[filename] = "Failed in batch processing"
        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}")
            for filepath in files:
                filename = os.path.basename(filepath)
                results[filename] = f"Batch error: {str(e)}"
    
    # Clear session
    session.pop('files', None)
    session.pop('visualization_options', None)
    
    # Delete uploaded files
    for filepath in files:
        try:
            os.remove(filepath)
        except:
            pass
    
    # Return results page which should then redirect to dashboard on success
    return render_template('results.html', results=results)

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
            flash('Invalid authentication response')
            return redirect(url_for('index'))
        
        # Complete the authentication flow
        creds = finish_google_auth(state, code)
        
        if creds:
            flash('Google Sheets authentication successful!')
        else:
            flash('Google Sheets authentication failed.')
    except Exception as e:
        flash(f'Error with Google authentication: {str(e)}')
    
    return redirect(url_for('index'))

@app.route('/dashboard')
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
        industry_data = get_industry_status_over_time(index_name, 12)
        
        # Return as JSON
        return jsonify(industry_data)
    except Exception as e:
        logger.error(f"Error getting industry status: {str(e)}")
        return jsonify({"error": str(e)}), 500

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

@app.route('/api/industry_status/<index_name>')
def s(index_name):
    try:
        # Get industry status data for the specified index (last 12 months)
        months = request.args.get('months', 12, type=int)
        industry_data = get_industry_status_over_time(index_name, months)
        return jsonify(industry_data)
    except Exception as e:
        logger.error(f"Error getting industry status: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

# Ensure app is available at the module level
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)