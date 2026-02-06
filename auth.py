import os
import functools
from flask import session, redirect, url_for, flash, request

def login_required(f):
    """
    Decorator to require login for all routes.
    Redirects to login page if not authenticated.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session or not session['authenticated']:
            # Store the original URL for redirection after login
            session['next_url'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def is_authenticated():
    """Check if the user is authenticated."""
    return 'authenticated' in session and session['authenticated']