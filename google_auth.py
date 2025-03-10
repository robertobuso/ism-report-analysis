import os
import pickle
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import logging
from flask import url_for, session, redirect

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_client_config():
    """Get client configuration from credentials file."""
    if not os.path.exists('credentials.json'):
        logger.error("Missing credentials.json file")
        return None
    
    return 'credentials.json'

def get_google_auth_url():
    """Get Google authentication URL."""
    try:
        client_config = get_client_config()
        if not client_config:
            return None
        
        # Create flow instance using client secrets file
        flow = Flow.from_client_secrets_file(
            client_config,
            scopes=SCOPES,
            redirect_uri=url_for('oauth2callback', _external=True)
        )
        
        # Generate the authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        # Save the state in session for verification later
        session['state'] = state
        
        return authorization_url
    except Exception as e:
        logger.error(f"Error generating auth URL: {str(e)}")
        return None

def finish_google_auth(state, code):
    """Complete the Google authentication flow."""
    try:
        # Verify state to prevent CSRF
        if state != session.get('state'):
            logger.error("State verification failed")
            return None
        
        client_config = get_client_config()
        if not client_config:
            return None
        
        # Create flow instance using client secrets file
        flow = Flow.from_client_secrets_file(
            client_config,
            scopes=SCOPES,
            redirect_uri=url_for('oauth2callback', _external=True)
        )
        
        # Use the state from the session
        flow.fetch_token(code=code)
        
        # Save credentials to token.pickle
        with open('token.pickle', 'wb') as token:
            pickle.dump(flow.credentials, token)
        
        return flow.credentials
    except Exception as e:
        logger.error(f"Error finishing auth: {str(e)}")
        return None

def get_google_sheets_service():
    """Get a Google Sheets API service."""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    # If there are no valid credentials, return None to prompt for auth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save the refreshed credentials
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        else:
            return None
    
    # Return the Google Sheets API service
    return build('sheets', 'v4', credentials=creds)