#!/usr/bin/env python3
"""
Substack Cookie Helper using Playwright

This script uses Playwright to authenticate with Substack and extract cookies
for use with the publish_substack.py script. This bypasses Cloudflare protection
by running a real browser.

Usage:
  # Login and save cookies for publish_substack.py
  python substack_playwright.py --login
  
  # Export cookies as JSON string for GitHub Actions
  python substack_playwright.py --export-cookies

Environment variables:
  SUBSTACK_EMAIL: Your Substack email
  SUBSTACK_PASSWORD: Your Substack password  
  SUBSTACK_PUBLICATION_URL: Your publication URL (e.g., https://obscurebit.substack.com)
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path


def get_playwright():
    """Import playwright with helpful error message."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("Error: Playwright not installed.")
        print("Install with: pip install playwright && playwright install chromium")
        sys.exit(1)


def login_and_save_cookies(email: str, password: str, publication_url: str):
    """Login to Substack and save cookies."""
    sync_playwright = get_playwright()
    cookies_file = Path.home() / ".substack_cookies.json"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Show browser for login
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(120000)  # 2 minute timeout
        
        print("Opening Substack login page...")
        page.goto("https://substack.com/sign-in", timeout=120000)
        
        # Wait for page to load
        page.wait_for_load_state("domcontentloaded")
        
        # Fill email
        print("Entering email...")
        page.fill('input[name="email"]', email)
        
        # Click continue/sign in
        page.click('button[type="submit"]')
        
        # Wait for password field or magic link prompt
        page.wait_for_timeout(2000)
        
        # Try to find password field
        password_field = page.query_selector('input[type="password"]')
        if password_field:
            print("Entering password...")
            password_field.fill(password)
            page.click('button[type="submit"]')
        else:
            print("\nPassword field not found. You may need to:")
            print("1. Check your email for a magic link")
            print("2. Complete any captcha")
            print("3. Press Enter here when logged in...")
            input()
        
        # Wait for successful login
        print("Waiting for login to complete...")
        page.wait_for_timeout(3000)
        
        # Navigate to publication to ensure cookies are set
        print(f"Navigating to {publication_url}...")
        page.goto(publication_url)
        page.wait_for_load_state("networkidle")
        
        # Extract cookies
        cookies = context.cookies()
        
        # Save cookies as JSON
        cookies_file.write_text(json.dumps(cookies, indent=2))
        print(f"\n✓ Cookies saved to {cookies_file}")
        print(f"   Set env: export SUBSTACK_COOKIES_PATH=\"$HOME/.substack_cookies.json\"")
        
        browser.close()


def export_cookies_base64():
    """Export cookies as base64 for GitHub secrets."""
    cookies_file = Path.home() / ".substack_cookies.json"
    
    if not cookies_file.exists():
        print(f"Error: No cookies file found at {cookies_file}")
        print("Run --login first to create it.")
        sys.exit(1)
    
    cookies = cookies_file.read_text()
    encoded = base64.b64encode(cookies.encode()).decode()
    
    print("\n=== COPY THIS TO GITHUB SECRET 'SUBSTACK_COOKIES' ===\n")
    print(encoded)
    print("\n=== END ===\n")
    
    # Also copy to clipboard if possible
    try:
        import subprocess
        subprocess.run(['pbcopy'], input=encoded.encode(), check=True)
        print("✓ Also copied to clipboard!")
    except:
        pass


def main():
    parser = argparse.ArgumentParser(description="Substack Cookie Helper using Playwright")
    parser.add_argument("--login", action="store_true", help="Login and save cookies")
    parser.add_argument("--export-cookies", action="store_true", help="Export cookies as base64 for GitHub")
    args = parser.parse_args()
    
    if args.login:
        email = os.environ.get("SUBSTACK_EMAIL")
        password = os.environ.get("SUBSTACK_PASSWORD")
        publication_url = os.environ.get("SUBSTACK_PUBLICATION_URL")
        
        if not email:
            email = input("Substack email: ")
        if not password:
            password = input("Substack password: ")
        if not publication_url:
            publication_url = input("Publication URL: ")
        
        login_and_save_cookies(email, password, publication_url)
        return
    
    if args.export_cookies:
        export_cookies_base64()
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()
