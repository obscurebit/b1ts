#!/usr/bin/env python3
"""
Substack Publisher using Playwright

This script uses Playwright to authenticate with Substack and publish posts,
bypassing Cloudflare protection by running a real browser.

Usage:
  # First time: Login and save browser state
  python substack_playwright.py --login
  
  # Publish using saved state
  python substack_playwright.py --edition 1 --draft
  python substack_playwright.py --edition 1 --publish
  
  # Export state for GitHub Actions
  python substack_playwright.py --export-state

Environment variables:
  SUBSTACK_EMAIL: Your Substack email
  SUBSTACK_PASSWORD: Your Substack password  
  SUBSTACK_PUBLICATION_URL: Your publication URL (e.g., https://obscurebit.substack.com)
  PLAYWRIGHT_STATE: Base64-encoded browser state (for CI)
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path
from datetime import date, timedelta

# Import content functions from publish_substack
from publish_substack import (
    get_edition_number,
    get_story_by_edition,
    get_links_by_edition,
    get_latest_story,
    get_latest_links,
    is_edition_published,
    mark_edition_published,
    generate_substack_markdown,
    save_substack_markdown,
)

STATE_FILE = Path.home() / ".substack_playwright_state.json"


def get_playwright():
    """Import playwright with helpful error message."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("Error: Playwright not installed.")
        print("Install with: pip install playwright && playwright install chromium")
        sys.exit(1)


def login_and_save_state(email: str, password: str, publication_url: str):
    """Login to Substack and save browser state."""
    sync_playwright = get_playwright()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Show browser for login
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(120000)  # 2 minute timeout
        
        print("Opening Substack login page...")
        page.goto("https://substack.com/sign-in", timeout=120000)
        
        # Wait for page to load (use domcontentloaded instead of networkidle)
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
        
        # Save state
        state = context.storage_state()
        STATE_FILE.write_text(json.dumps(state))
        print(f"\n✓ Browser state saved to {STATE_FILE}")
        
        browser.close()


def export_state_base64():
    """Export browser state as base64 for GitHub secrets."""
    if not STATE_FILE.exists():
        print(f"Error: No state file found at {STATE_FILE}")
        print("Run --login first to create it.")
        sys.exit(1)
    
    state = STATE_FILE.read_text()
    encoded = base64.b64encode(state.encode()).decode()
    
    print("\n=== COPY THIS TO GITHUB SECRET 'PLAYWRIGHT_STATE' ===\n")
    print(encoded)
    print("\n=== END ===\n")
    
    # Also copy to clipboard if possible
    try:
        import subprocess
        subprocess.run(['pbcopy'], input=encoded.encode(), check=True)
        print("✓ Also copied to clipboard!")
    except:
        pass


def load_state():
    """Load browser state from file or environment."""
    # Check for base64-encoded state in environment (GitHub Actions)
    env_state = os.environ.get("PLAYWRIGHT_STATE")
    if env_state:
        try:
            decoded = base64.b64decode(env_state).decode()
            return json.loads(decoded)
        except Exception as e:
            print(f"Error decoding PLAYWRIGHT_STATE: {e}")
            sys.exit(1)
    
    # Check for state file
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    
    print(f"Error: No browser state found.")
    print("Run --login first or set PLAYWRIGHT_STATE environment variable.")
    sys.exit(1)


def publish_to_substack(story: dict, links: list, edition: int, draft: bool = True):
    """Publish post to Substack using Playwright."""
    sync_playwright = get_playwright()
    
    publication_url = os.environ.get("SUBSTACK_PUBLICATION_URL")
    if not publication_url:
        print("Error: SUBSTACK_PUBLICATION_URL not set")
        sys.exit(1)
    
    state = load_state()
    
    today = date.today()
    date_str = today.strftime("%B %d, %Y")
    title = f"Obscure Bit #{edition:03d}: {story['title']}"
    subtitle = f"Daily discoveries from the hidden corners of the internet • {date_str}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=state)
        page = context.new_page()
        page.set_default_timeout(120000)  # 2 minute timeout
        
        print("Opening Substack editor...")
        page.goto(f"{publication_url}/publish/post", timeout=120000)
        page.wait_for_load_state("domcontentloaded")
        
        # Check if we're logged in
        if "sign-in" in page.url.lower():
            print("Error: Not logged in. Run --login to refresh session.")
            browser.close()
            sys.exit(1)
        
        print("Creating new post...")
        
        # Wait for editor to load
        page.wait_for_timeout(2000)
        
        # Fill title
        print("Setting title...")
        title_input = page.query_selector('[data-testid="post-title-input"], input[placeholder*="Title"], .post-title')
        if title_input:
            title_input.fill(title)
        else:
            # Try contenteditable
            page.keyboard.type(title)
        
        page.wait_for_timeout(500)
        
        # Fill subtitle
        print("Setting subtitle...")
        subtitle_input = page.query_selector('[data-testid="post-subtitle-input"], input[placeholder*="subtitle"], .post-subtitle')
        if subtitle_input:
            subtitle_input.fill(subtitle)
        
        page.wait_for_timeout(500)
        
        # Fill body content
        print("Adding content...")
        
        # Build content
        content_lines = [
            f"*Edition #{edition:03d} • {date_str}*",
            "",
            "---",
            "",
            f"## 📖 Today's Bit",
            "",
            f"### {story['title']}",
            "",
            story['body'],
            "",
            "---",
            "",
            "## 🔗 Today's Obscure Links",
            "",
            "Curated discoveries from the hidden corners of the web:",
            "",
        ]
        
        for link in links[:7]:
            content_lines.append(f"[{link['title']}]({link['url']})")
            content_lines.append("")
        
        content_lines.extend([
            "---",
            "",
            "*Come back tomorrow for more obscure discoveries.*",
            "",
            "[Visit Obscure Bit](https://obscurebit.com) for the full archive.",
        ])
        
        content = "\n".join(content_lines)
        
        # Find editor and paste content
        editor = page.query_selector('[contenteditable="true"], .ProseMirror, .editor-content')
        if editor:
            editor.click()
            page.wait_for_timeout(300)
            # Use clipboard to paste markdown
            page.keyboard.type(content, delay=1)
        
        page.wait_for_timeout(1000)
        
        if draft:
            print("Saving as draft...")
            # Look for save/draft button
            save_btn = page.query_selector('button:has-text("Save draft"), button:has-text("Save")')
            if save_btn:
                save_btn.click()
            page.wait_for_timeout(2000)
            print(f"\n✅ Draft saved!")
        else:
            print("Publishing...")
            # Look for publish button
            publish_btn = page.query_selector('button:has-text("Publish"), button:has-text("Continue")')
            if publish_btn:
                publish_btn.click()
            page.wait_for_timeout(2000)
            
            # Confirm publish if needed
            confirm_btn = page.query_selector('button:has-text("Publish now"), button:has-text("Confirm")')
            if confirm_btn:
                confirm_btn.click()
            
            page.wait_for_timeout(3000)
            mark_edition_published(edition)
            print(f"\n✅ Published edition #{edition:03d}!")
        
        # Get the post URL
        current_url = page.url
        print(f"Post URL: {current_url}")
        
        browser.close()
        return True


def main():
    parser = argparse.ArgumentParser(description="Substack Publisher using Playwright")
    parser.add_argument("--login", action="store_true", help="Login and save browser state")
    parser.add_argument("--export-state", action="store_true", help="Export state as base64 for GitHub")
    parser.add_argument("--edition", type=int, help="Edition number to publish")
    parser.add_argument("--draft", action="store_true", help="Save as draft")
    parser.add_argument("--publish", action="store_true", help="Publish immediately")
    parser.add_argument("--force", action="store_true", help="Force republish")
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
        
        login_and_save_state(email, password, publication_url)
        return
    
    if args.export_state:
        export_state_base64()
        return
    
    if not args.draft and not args.publish:
        parser.print_help()
        return
    
    # Get content
    if args.edition:
        edition = args.edition
        story = get_story_by_edition(edition)
        links = get_links_by_edition(edition)
    else:
        edition = get_edition_number()
        story = get_latest_story()
        links = get_latest_links()
    
    if not story:
        print(f"Error: No story found for edition #{edition:03d}")
        sys.exit(1)
    
    if not links:
        print("Warning: No links found")
        links = []
    
    print(f"Edition: #{edition:03d}")
    print(f"Story: {story['title']}")
    print(f"Links: {len(links)} links")
    
    # Check if already published
    if is_edition_published(edition) and not args.force:
        print(f"\nEdition #{edition:03d} already published. Use --force to republish.")
        sys.exit(0)
    
    # Generate and save markdown
    print("\nGenerating markdown...")
    title, subtitle, markdown_body = generate_substack_markdown(story, links, edition)
    save_substack_markdown(title, subtitle, markdown_body, edition)
    
    # Publish
    publish_to_substack(story, links, edition, draft=args.draft)


if __name__ == "__main__":
    main()
