import os
import pickle
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import logging
from flask import url_for, session, redirect

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

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
    """Complete the Google authentication flow. Returns (credentials, user_email) tuple."""
    try:
        # Verify state to prevent CSRF
        if state != session.get('state'):
            logger.error("State verification failed")
            return None, None

        client_config = get_client_config()
        if not client_config:
            return None, None

        # Create flow instance using client secrets file
        flow = Flow.from_client_secrets_file(
            client_config,
            scopes=SCOPES,
            redirect_uri=url_for('oauth2callback', _external=True)
        )

        # Use the state from the session
        flow.fetch_token(code=code)

        # Get user email using the access token
        user_email = ''
        try:
            import requests
            headers = {'Authorization': f'Bearer {flow.credentials.token}'}
            response = requests.get('https://www.googleapis.com/oauth2/v2/userinfo', headers=headers)
            if response.status_code == 200:
                user_info = response.json()
                user_email = user_info.get('email', '')
                logger.info(f"Got user email from Google: {user_email}")
            else:
                logger.error(f"Failed to get user info: {response.status_code}")
        except Exception as e:
            logger.error(f"Error getting user info from Google: {str(e)}")

        # Save credentials to token.pickle
        with open('token.pickle', 'wb') as token:
            pickle.dump(flow.credentials, token)

        return flow.credentials, user_email
    except Exception as e:
        logger.error(f"Error finishing auth: {str(e)}")
        return None, None

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