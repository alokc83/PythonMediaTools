import sys
import os
import pickle
import requests
from bs4 import BeautifulSoup
import urllib.parse

SESSION_FILE = "blinkist_session.pkl"
LOGIN_URL = "https://www.blinkist.com/en/nc/login"

def save_session(session, filename=SESSION_FILE):
    with open(filename, 'wb') as f:
        pickle.dump(session.cookies, f)
    print("Session saved to", filename)

def load_session(filename=SESSION_FILE):
    session = requests.Session()
    try:
        with open(filename, 'rb') as f:
            cookies = pickle.load(f)
            session.cookies.update(cookies)
        print("Session loaded from", filename)
    except Exception as e:
        print("Could not load session:", e)
    return session

def is_session_valid(session):
    # Try to access a page that requires login.
    r = session.get("https://www.blinkist.com/en/nc/my-account")
    return r.status_code == 200

def login_blinkist(email, password):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.blinkist.com/"
    }
    # Get the login page to retrieve any hidden fields (like CSRF tokens)
    r = session.get(LOGIN_URL, headers=headers)
    if r.status_code != 200:
        print("Failed to load login page, status code:", r.status_code)
        sys.exit(1)
    soup = BeautifulSoup(r.text, 'html.parser')
    # Example: Extract a CSRF token if present; adjust the field name as needed.
    csrf_token = ''
    csrf_input = soup.find("input", {"name": "csrf_token"})
    if csrf_input:
        csrf_token = csrf_input.get("value", "")
    print("CSRF token found:", csrf_token)
    
    payload = {
        "email": email,
        "password": password,
        "csrf_token": csrf_token,
        # Include any other fields required by the login form
    }
    post_response = session.post(LOGIN_URL, data=payload, headers=headers)
    print("POST response status code:", post_response.status_code)
    
    # Check if login was successful by verifying that we are no longer on the login page.
    if post_response.url != LOGIN_URL:
        print("Login appears to be successful!")
        return session
    else:
        print("Login may have failed. Please check your credentials and required form fields.")
        sys.exit(1)

def main():
    # First try to load an existing session.
    if os.path.exists(SESSION_FILE):
        session = load_session()
        if not is_session_valid(session):
            print("Loaded session is not valid, need to login again.")
            os.remove(SESSION_FILE)
            session = None
    else:
        session = None
    
    if session is None:
        email = input("Enter your Blinkist email: ").strip()
        password = input("Enter your Blinkist password: ").strip()
        session = login_blinkist(email, password)
        save_session(session)
    
    # Now you can use 'session' for subsequent requests without logging in again.
    # For example, get the account page:
    account_page = session.get("https://www.blinkist.com/en/nc/my-account")
    if account_page.status_code == 200:
        print("Successfully accessed your Blinkist account page!")
    else:
        print("Failed to access your Blinkist account page, status code:", account_page.status_code)

if __name__ == "__main__":
    main()
