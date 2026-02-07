#!/usr/bin/env python3
"""
Generate and publish Obscure Bit daily edition to Substack.

This script:
1. Generates a markdown file for the Substack newsletter
2. Saves it to docs/substack/ for history
3. Optionally publishes to Substack

Usage:
  python publish_substack.py                  # Generate markdown only (for CI)
  python publish_substack.py --publish        # Generate and publish immediately
  python publish_substack.py --draft          # Generate and save as Substack draft
  python publish_substack.py --edition 1 --draft  # Publish specific edition as draft
  python publish_substack.py --edition 1 --publish --force  # Force republish

Requires environment variables for --publish or --draft:

Option A - Email/Password (may fail with captcha):
- SUBSTACK_EMAIL: Your Substack account email
- SUBSTACK_PASSWORD: Your Substack account password
- SUBSTACK_PUBLICATION_URL: Your publication URL

Option B - Cookie auth (recommended, bypasses captcha):
- SUBSTACK_COOKIES: JSON string of cookies from browser
- OR SUBSTACK_COOKIES_PATH: Path to cookies JSON file
- SUBSTACK_PUBLICATION_URL: Your publication URL

To get cookies (recommended method):
1. Log in to substack.com in your browser
2. Open Developer Tools → Application → Cookies → substack.com
3. Click "Export all as JSON" or copy manually
4. Save to file: ~/.substack_cookies.json
5. Set env: export SUBSTACK_COOKIES_PATH="$HOME/.substack_cookies.json"
"""

import os
import sys
import re
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from substack import Api
from substack.post import Post


def get_edition_number() -> int:
    """Calculate the current edition number based on launch date."""
    launch_date = date(2026, 1, 30)  # Same as in update_landing.py
    today = date.today()
    days_since_launch = (today - launch_date).days
    return days_since_launch + 1


def is_edition_published(edition: int) -> bool:
    """Check if an edition has already been published to Substack."""
    substack_dir = Path("docs/substack")
    if not substack_dir.exists():
        return False
    
    # Look for published marker file
    published_file = substack_dir / f"edition-{edition:03d}-published.txt"
    return published_file.exists()


def mark_edition_published(edition: int):
    """Mark an edition as published to Substack."""
    substack_dir = Path("docs/substack")
    substack_dir.mkdir(parents=True, exist_ok=True)
    
    published_file = substack_dir / f"edition-{edition:03d}-published.txt"
    published_file.write_text(f"Edition #{edition:03d} published on {date.today()}\n")


def get_story_by_edition(edition: int) -> dict:
    """Get story content for a specific edition number."""
    launch_date = date(2026, 1, 30)
    target_date = launch_date + timedelta(days=edition - 1)
    
    stories_dir = Path("docs/bits/posts")
    if not stories_dir.exists():
        return None
    
    # Look for story file matching the target date
    date_prefix = target_date.strftime("%Y-%m-%d")
    matching_files = list(stories_dir.glob(f"{date_prefix}-*.md"))
    
    if not matching_files:
        return None
    
    story_file = matching_files[0]
    content = story_file.read_text()
    return _parse_story_content(content, story_file.name)


def get_latest_story() -> dict:
    """Get the latest story content."""
    stories_dir = Path("docs/bits/posts")
    if not stories_dir.exists():
        return None
    
    story_files = sorted(stories_dir.glob("*.md"), reverse=True)
    if not story_files:
        return None
    
    latest = story_files[0]
    content = latest.read_text()
    return _parse_story_content(content, latest.name)


def _parse_story_content(content: str, filename: str) -> dict:
    """Parse story content from markdown."""
    
    # Parse frontmatter
    lines = content.split("\n")
    in_frontmatter = False
    frontmatter_end = 0
    title = ""
    
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
            else:
                frontmatter_end = i + 1
                break
        elif in_frontmatter and line.startswith("title:"):
            title = line.split(":", 1)[1].strip().strip('"\'')
    
    # Get body (everything after frontmatter and title, excluding share button)
    body_start = content.find("\n", content.find("# ")) + 1
    body = content[body_start:].strip()
    
    # Remove share button HTML block if present (appears at end of story)
    if "<button class=\"share-btn\"" in body:
        body = re.sub(r'\n*---\n*<button class="share-btn".*?</button>\s*$', '', body, flags=re.DOTALL).strip()
    
    # Remove the main title if it exists (usually starts with #)
    if body.startswith("#"):
        body = "\n".join(body.split("\n")[1:]).strip()
    
    return {
        "title": title,
        "body": body,
        "filename": filename,
    }


def get_links_by_edition(edition: int) -> list:
    """Get links for a specific edition number."""
    launch_date = date(2026, 1, 30)
    target_date = launch_date + timedelta(days=edition - 1)
    
    links_dir = Path("docs/links/posts")
    if not links_dir.exists():
        return []
    
    # Look for links file matching the target date
    date_prefix = target_date.strftime("%Y-%m-%d")
    matching_files = list(links_dir.glob(f"{date_prefix}-*.md"))
    
    if not matching_files:
        return []
    
    links_file = matching_files[0]
    content = links_file.read_text()
    return _parse_links_content(content)


def get_latest_links() -> list:
    """Get the latest links."""
    links_dir = Path("docs/links/posts")
    if not links_dir.exists():
        return []
    
    link_files = sorted(links_dir.glob("*.md"), reverse=True)
    if not link_files:
        return []
    
    latest = link_files[0]
    content = latest.read_text()
    return _parse_links_content(content)


def _parse_links_content(content: str) -> list:
    """Parse links from markdown content."""
    # Format: ## 1. Title Here ... <a href="URL">
    links = []
    lines = content.split("\n")
    current_title = None
    
    for line in lines:
        # Match: ## 1. Title or ## Title
        if line.strip().startswith("## "):
            title_match = re.match(r'##\s*(?:\d+\.\s*)?(.+)', line.strip())
            if title_match:
                current_title = title_match.group(1).strip()
        # Match: <a href="URL"
        elif current_title and '<a href="' in line:
            url_match = re.search(r'<a href="([^"]+)"', line)
            if url_match:
                links.append({
                    "title": current_title,
                    "url": url_match.group(1),
                })
                current_title = None
    
    return links


def get_link_descriptions(content: str) -> dict:
    """Extract link descriptions from the links post."""
    descriptions = {}
    lines = content.split("\n")
    current_title = None
    
    for i, line in enumerate(lines):
        if line.strip().startswith("## ["):
            import re
            match = re.match(r'##\s*\[([^\]]+)\]', line.strip())
            if match:
                current_title = match.group(1)
        elif current_title and line.strip() and not line.strip().startswith("#"):
            descriptions[current_title] = line.strip()
            current_title = None
    
    return descriptions


def format_html_content(story: dict, links: list, edition: int) -> str:
    """Format the content as HTML for Substack."""
    today = date.today()
    date_str = today.strftime("%B %d, %Y")
    
    html = f"""
<p><em>Edition #{edition:03d} • {date_str}</em></p>

<hr>

<h2>📖 Today's Bit</h2>

<h3>{story['title']}</h3>

{markdown_to_html(story['body'])}

<hr>

<h2>🔗 Today's Obscure Links</h2>

<p>Curated discoveries from the hidden corners of the web:</p>

<ul>
"""
    
    for link in links[:7]:  # Limit to 7 links
        html += f'<li><a href="{link["url"]}">{link["title"]}</a></li>\n'
    
    html += """</ul>

<hr>

<p><em>Come back tomorrow for more obscure discoveries.</em></p>

<p><a href="https://obscurebit.com">Visit Obscure Bit</a> for the full archive.</p>
"""
    
    return html


def markdown_to_html(markdown: str) -> str:
    """Simple markdown to HTML conversion."""
    import re
    
    html = markdown
    
    # Convert paragraphs (double newlines)
    paragraphs = html.split("\n\n")
    html_paragraphs = []
    
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        
        # Bold
        p = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', p)
        
        # Italic
        p = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', p)
        
        # Links
        p = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', p)
        
        html_paragraphs.append(f"<p>{p}</p>")
    
    return "\n\n".join(html_paragraphs)


def generate_substack_markdown(story: dict, links: list, edition: int) -> tuple[str, str, str]:
    """
    Generate the markdown content for Substack.
    Returns (title, subtitle, markdown_body).
    """
    today = date.today()
    date_str = today.strftime("%B %d, %Y")
    
    title = f"Obscure Bit #{edition:03d}: {story['title']}"
    subtitle = f"Daily discoveries from the hidden corners of the internet • {date_str}"
    
    # Build links section as HTML (Substack API prefers HTML)
    links_html = ""
    for link in links[:7]:
        links_html += f'<p><a href="{link["url"]}">{link["title"]}</a></p>\n'
    
    # Create markdown content
    markdown_body = f"""*Edition #{edition:03d} • {date_str}*

---

## 📖 Today's Bit

### {story['title']}

{story['body']}

---

## 🔗 Today's Obscure Links

Curated discoveries from the hidden corners of the web:

{links_html}

---

*Come back tomorrow for more obscure discoveries.*

[Visit Obscure Bit](https://obscurebit.com) for the full archive.
"""
    
    return title, subtitle, markdown_body


def save_substack_markdown(title: str, subtitle: str, body: str, edition: int) -> Path:
    """Save the Substack markdown to a file for history."""
    today = date.today()
    date_str = today.strftime("%Y-%m-%d")
    
    # Create substack directory
    substack_dir = Path("docs/substack")
    substack_dir.mkdir(parents=True, exist_ok=True)
    
    # Create file with frontmatter
    filename = substack_dir / f"{date_str}-edition-{edition:03d}.md"
    
    content = f"""---
title: "{title}"
subtitle: "{subtitle}"
date: {date_str}
edition: {edition}
---

{body}"""
    
    filename.write_text(content)
    print(f"✓ Saved: {filename}")
    return filename


def build_post_content(api, story: dict, links: list, edition: int) -> Post:
    """Build the Substack post using the library's native content blocks."""
    today = date.today()
    date_str = today.strftime("%B %d, %Y")
    
    user_id = api.get_user_id()
    
    post = Post(
        title=f"Obscure Bit #{edition:03d}: {story['title']}",
        subtitle=f"Daily discoveries from the hidden corners of the internet • {date_str}",
        user_id=user_id,
        audience="everyone",
    )
    
    # Add edition header
    post.add({'type': 'paragraph', 'content': [
        {'content': f"Edition #{edition:03d} • {date_str}", 'marks': [{'type': 'em'}]}
    ]})
    
    # Add horizontal rule
    post.add({'type': 'horizontalRule'})
    
    # Add story section header
    post.add({'type': 'heading', 'level': 2, 'content': "📖 Today's Bit"})
    post.add({'type': 'heading', 'level': 3, 'content': story['title']})
    
    # Add story content as paragraphs
    for paragraph in story['body'].split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            post.add({'type': 'paragraph', 'content': paragraph})
    
    # Add horizontal rule
    post.add({'type': 'horizontalRule'})
    
    # Add links section
    post.add({'type': 'heading', 'level': 2, 'content': "🔗 Today's Obscure Links"})
    post.add({'type': 'paragraph', 'content': "Curated discoveries from the hidden corners of the web:"})
    
    # Add links as proper link blocks
    for link in links[:7]:
        post.add({'type': 'paragraph', 'content': [
            {'content': link['title'], 'marks': [{'type': 'link', 'href': link['url']}]}
        ]})
    
    # Add footer
    post.add({'type': 'horizontalRule'})
    post.add({'type': 'paragraph', 'content': [
        {'content': "Come back tomorrow for more obscure discoveries.", 'marks': [{'type': 'em'}]}
    ]})
    post.add({'type': 'paragraph', 'content': [
        {'content': "Visit Obscure Bit", 'marks': [{'type': 'link', 'href': 'https://obscurebit.com'}]},
        {'content': " for the full archive."}
    ]})
    
    return post


def main():
    """Main entry point."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Generate and publish Obscure Bit to Substack")
    parser.add_argument("--publish", action="store_true", help="Publish immediately to Substack")
    parser.add_argument("--draft", action="store_true", help="Save as Substack draft (for review)")
    parser.add_argument("--edition", type=int, help="Specific edition number to publish (default: latest)")
    parser.add_argument("--force", action="store_true", help="Force republish even if already published")
    args = parser.parse_args()
    
    # Get content for specific edition or latest
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
        print(f"\nEdition #{edition:03d} already published to Substack. Skipping.")
        print("Use --force to republish")
        sys.exit(0)
    
    print()
    
    # Step 1: Generate markdown content (for history)
    print("Generating Substack markdown...")
    title, subtitle, markdown_body = generate_substack_markdown(story, links, edition)
    
    # Step 2: Save to file (always)
    saved_file = save_substack_markdown(title, subtitle, markdown_body, edition)
    
    # Step 3: Publish to Substack (only if --publish or --draft)
    if not args.publish and not args.draft:
        print("\n✅ Markdown generated. Use --publish or --draft to send to Substack.")
        sys.exit(0)
    
    # Check credentials for publishing
    email = os.environ.get("SUBSTACK_EMAIL")
    password = os.environ.get("SUBSTACK_PASSWORD")
    cookies = os.environ.get("SUBSTACK_COOKIES")
    cookies_path = os.environ.get("SUBSTACK_COOKIES_PATH") or str(Path.home() / ".substack_cookies.json")
    cookies_path = os.path.expanduser(cookies_path)
    publication_url = os.environ.get("SUBSTACK_PUBLICATION_URL", "").strip() or "https://obscurebit.substack.com"
    
    # Need either email+password OR cookies, plus publication_url
    has_email_auth = email and password
    has_cookie_auth = cookies or cookies_path
    if (args.publish or args.draft) and not publication_url:
        print("Error: SUBSTACK_PUBLICATION_URL is required.")
        print("  export SUBSTACK_PUBLICATION_URL='https://obscurebit.substack.com'")
        sys.exit(1)
    
    if not has_email_auth and not has_cookie_auth:
        print("\nError: Missing Substack credentials for publishing.")
        print("\nOption A - Email/Password (may fail with captcha):")
        print("  export SUBSTACK_EMAIL='b1ts@obscurebit.com'")
        print("  export SUBSTACK_PASSWORD='your-password'")
        print("\nOption B - Cookie auth (recommended):")
        print("  export SUBSTACK_COOKIES='[{\"name\":\"session\", \"value\":\"...\"}]'")
        print("  # OR save to file:")
        print("  export SUBSTACK_COOKIES_PATH='$HOME/.substack_cookies.json'")
        print("\nTo get cookies:")
        print("  1. Log in to substack.com in your browser")
        print("  2. Open Developer Tools → Application → Cookies → substack.com")
        print("  3. Click 'Export all as JSON' or copy manually")
        print("  4. Save to file: ~/.substack_cookies.json")
        print("  5. Set env: export SUBSTACK_COOKIES_PATH=\"$HOME/.substack_cookies.json\"")
        sys.exit(1)
    
    try:
        # Initialize API with credentials
        print("\nAuthenticating with Substack...")
        if cookies_path:
            # Load cookies from file
            with open(cookies_path, 'r') as f:
                cookie_list = json.load(f)
            # Convert to cookie string format
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookie_list])
            api = Api(
                cookies_string=cookie_str,
                publication_url=publication_url,
            )
        elif cookies:
            # Use cookies from environment variable
            cookie_list = json.loads(cookies)
            # Convert to cookie string format
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookie_list])
            api = Api(
                cookies_string=cookie_str,
                publication_url=publication_url,
            )
        else:
            api = Api(
                email=email,
                password=password,
                publication_url=publication_url,
            )
        print("✓ Authenticated")
        
        # Build post
        print("Building post...")
        post = build_post_content(api, story, links, edition)
        print("✓ Post ready")
        
        # Create draft
        print("Creating draft...")
        draft = api.post_draft(post.get_draft())
        draft_id = draft.get("id")
        print(f"✓ Created draft ID: {draft_id}")
        
        if args.draft:
            print("\n✅ Draft saved! Review at:")
            print(f"   {publication_url}/publish/post/{draft_id}")
        else:
            # Publish immediately
            print("Publishing...")
            api.prepublish_draft(draft_id)
            api.publish_draft(draft_id)
            mark_edition_published(edition)
            print("\n✅ Published to Substack!")
            print(f"   Edition #{edition:03d} marked as published")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
