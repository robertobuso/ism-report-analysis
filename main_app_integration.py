# Add this to your existing app.py or create a new file that's imported by your app

from flask import Flask, redirect, url_for
from web_insight import web_insight_bp

def integrate_web_insights(app):
    """
    Integrate the web insights module into the main Flask application.
    
    Args:
        app: The Flask application instance
    """
    # Register the blueprint
    app.register_blueprint(web_insight_bp, url_prefix='/web_insight')
    
    # Add a route to redirect from main dashboard
    @app.route('/web_insights')
    def web_insights_redirect():
        """Redirect to the web insights dashboard."""
        return redirect(url_for('web_insight.index'))

# If this is being run directly, create a test app
if __name__ == '__main__':
    app = Flask(__name__)
    integrate_web_insights(app)
    app.run(debug=True)