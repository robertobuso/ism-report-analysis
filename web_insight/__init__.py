from flask import Blueprint, request, jsonify, render_template
from . import insight_generator

# Create Blueprint
web_insight_bp = Blueprint('web_insight', 
                          __name__,
                          template_folder='templates',
                          static_folder='static',
                          static_url_path='/web_insight/static')

# Initialize the insight generator
def get_insight_generator():
    return insight_generator.WebEnhancedInsightGenerator()

@web_insight_bp.route('/')
def index():
    """Render the insights dashboard."""
    return render_template('insights_dashboard.html')

@web_insight_bp.route('/api/significant_trends', methods=['GET'])
def get_significant_trends():
    """API endpoint to get significant trends."""
    try:
        # Initialize the insight generator
        generator = get_insight_generator()
        
        # Get significant trends
        trends = generator.identify_significant_trends()
        
        # Limit to configurable number of trends
        from . import config
        trends = trends[:config.MAX_TRENDS_TO_DISPLAY]
        
        return jsonify(trends)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@web_insight_bp.route('/api/insights', methods=['GET'])
def get_insights():
    """API endpoint to get all insights."""
    try:
        # Initialize the insight generator
        generator = get_insight_generator()
        
        # Get limit parameter if available
        limit = request.args.get('limit', 10, type=int)
        
        # Get all insights
        insights = generator.get_all_insights(limit)
        
        return jsonify(insights)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@web_insight_bp.route('/api/insight/<insight_id>', methods=['GET'])
def get_insight(insight_id):
    """API endpoint to get a specific insight."""
    try:
        # Initialize the insight generator
        generator = get_insight_generator()
        
        # Get the insight
        insight = generator.get_insight(insight_id)
        
        if insight is None:
            return jsonify({'error': 'Insight not found'}), 404
            
        return jsonify(insight)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@web_insight_bp.route('/api/generate_insight', methods=['POST'])
def generate_insight_api():
    """API endpoint to generate a new insight."""
    try:
        # Get parameters from request
        data = request.json or {}
        trend_index = data.get('trend_index', 0)
        
        # Initialize the insight generator
        generator = get_insight_generator()
        
        # Generate insight
        insight = generator.generate_insight(trend_index)
        
        return jsonify(insight)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@web_insight_bp.route('/api/insight/<insight_id>', methods=['DELETE'])
def delete_insight(insight_id):
    """API endpoint to delete an insight."""
    try:
        # Initialize the insight generator
        generator = get_insight_generator()
        
        # Delete the insight
        success = generator.delete_insight(insight_id)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to delete insight'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500