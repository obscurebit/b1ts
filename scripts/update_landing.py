#!/usr/bin/env python3
"""
Update the landing page (home.html) with the latest story and links content.
Run after generate_story.py and generate_links.py.
"""

import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict

# Launch date - edition #001
LAUNCH_DATE = date(2026, 1, 30)

def get_edition_number() -> int:
    """Calculate edition number based on days since launch."""
    today = date.today()
    delta = (today - LAUNCH_DATE).days
    return max(1, delta + 1)


def get_latest_story() -> Optional[Dict]:
    """Find and parse the latest story from bits/posts/."""
    posts_dir = Path("docs/bits/posts")
    if not posts_dir.exists():
        return None
    
    # Find most recent story file
    story_files = sorted(posts_dir.glob("*.md"), reverse=True)
    if not story_files:
        return None
    
    latest = story_files[0]
    content = latest.read_text()
    
    # Parse frontmatter
    title = ""
    if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
        title = match.group(1)
    
    # Extract first paragraph after the title as excerpt
    lines = content.split("\n")
    excerpt = ""
    in_content = False
    for line in lines:
        if line.startswith("# "):
            in_content = True
            continue
        if in_content and line.strip() and not line.startswith("---"):
            excerpt = line.strip()[:200]
            if len(line.strip()) > 200:
                excerpt += "..."
            break
    
    # Build URL path from filename
    slug = latest.stem  # e.g., "2026-01-30-the-quantum-callback"
    url_path = f"bits/posts/{slug}/"
    
    return {
        "title": title,
        "excerpt": excerpt,
        "url": url_path,
        "date": latest.stem[:10],
    }


def get_latest_links() -> tuple[List[Dict], int]:
    """Find and parse the latest links from links/posts/. Returns (links, total_count)."""
    posts_dir = Path("docs/links/posts")
    if not posts_dir.exists():
        return [], 0
    
    # Find most recent links file
    link_files = sorted(posts_dir.glob("*.md"), reverse=True)
    if not link_files:
        return [], 0
    
    latest = link_files[0]
    content = latest.read_text()
    
    links = []
    
    # Parse link sections (## N. Title format)
    sections = re.split(r'^## \d+\.\s+', content, flags=re.MULTILINE)[1:]
    total_count = len(sections)
    
    for section in sections[:3]:  # Get first 3 links
        lines = section.strip().split("\n")
        title = lines[0].strip() if lines else "Untitled"
        
        # Find URL
        url = "#"
        if match := re.search(r'href="([^"]+)"', section):
            url = match.group(1)
        
        # Get description (first non-empty line after title)
        desc = ""
        for line in lines[1:]:
            line = line.strip()
            if line and not line.startswith("*") and not line.startswith("<") and not line.startswith("---"):
                desc = line[:100]
                if len(line) > 100:
                    desc += "..."
                break
        
        links.append({"title": title, "desc": desc, "url": url})
    
    return links, total_count


def update_home_html(story: Optional[Dict], links: List[Dict], total_links: int, edition: int):
    """Update the home.html template with latest content."""
    home_path = Path("overrides/home.html")
    if not home_path.exists():
        print("Error: overrides/home.html not found")
        return False
    
    content = home_path.read_text()
    
    # Update edition number
    content = re.sub(
        r'Edition #\d+',
        f'Edition #{edition:03d}',
        content
    )
    
    # Update story section if we have a story
    if story:
        # Update story URL
        content = re.sub(
            r"href=\"\{\{ 'bits/posts/[^']+' \| url \}\}\"",
            f"href=\"{{{{ '{story['url']}' | url }}}}\"",
            content
        )
        
        # Update story title
        content = re.sub(
            r'(<h2 class="ob-today__story-title">)[^<]+(</h2>)',
            f"\\g<1>{story['title']}\\g<2>",
            content
        )
        
        # Update story excerpt
        content = re.sub(
            r'(<p class="ob-today__story-excerpt">)\s*[^<]+\s*(</p>)',
            f"\\g<1>\n        {story['excerpt']}\n      \\g<2>",
            content,
            flags=re.DOTALL
        )
    
    # Update links section if we have links
    if links:
        # Build new links HTML
        links_html = ""
        for i, link in enumerate(links[:3], 1):
            featured = ' ob-link--featured' if i == 1 else ''
            links_html += f'''
      <a href="{link['url']}" target="_blank" rel="noopener" class="ob-link{featured}">
        <span class="ob-link__number">{i:02d}</span>
        <div class="ob-link__content">
          <h3 class="ob-link__title">{link['title']}</h3>
          <p class="ob-link__desc">{link['desc']}</p>
        </div>
        <span class="ob-link__arrow">↗</span>
      </a>
      '''
        
        # Add "view all" link
        remaining = max(0, total_links - 3)
        links_html += f'''
      <a href="{{{{ 'links/' | url }}}}" class="ob-link ob-link--more">
        <span class="ob-link__more-text">View all links</span>
        <span class="ob-link__more-count">+{remaining} more today</span>
      </a>
    '''
        
        # Replace links grid content
        content = re.sub(
            r'(<div class="ob-links__grid">).+?(</div>\s*</div>\s*</section>\s*<!-- Footer)',
            f'\\g<1>{links_html}</div>\n  </div>\n</section>\n\n<!-- Footer',
            content,
            flags=re.DOTALL
        )
    
    home_path.write_text(content)
    print(f"Updated home.html with Edition #{edition:03d}")
    return True


def update_bits_index():
    """Update the bits index page with all stories."""
    bits_index = Path("docs/bits/index.md")
    if not bits_index.exists():
        print("Warning: bits/index.md not found")
        return False
    
    posts_dir = Path("docs/bits/posts")
    if not posts_dir.exists():
        return False
    
    # Get all story files, sorted by date (newest first)
    story_files = sorted(posts_dir.glob("*.md"), reverse=True)
    
    # Build archive list HTML
    archive_html = ""
    for story_file in story_files:
        content = story_file.read_text()
        
        # Parse frontmatter
        title = ""
        date_str = ""
        if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            title = match.group(1)
        if match := re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE):
            date_str = match.group(1)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%B %d, %Y")
            # Calculate edition number from date
            post_date = date_obj.date()
            edition_num = (post_date - LAUNCH_DATE).days + 1
        
        # Extract first paragraph as excerpt
        excerpt = ""
        # Split content and find the actual story text after frontmatter and title
        parts = content.split("---", 2)  # Split on frontmatter delimiters
        if len(parts) >= 3:
            # Get content after frontmatter
            story_content = parts[2]
            lines = story_content.split("\n")
            past_title = False
            for line in lines:
                if line.startswith("# "):
                    past_title = True
                    continue
                # Get first non-empty paragraph after title
                if past_title and line.strip() and not line.startswith("<") and not line.startswith("##"):
                    excerpt = line.strip()[:150]
                    if len(line.strip()) > 150:
                        excerpt += "..."
                    break
        
        slug = story_file.stem
        
        archive_html += f'''  <a href="posts/{slug}/" class="archive-item">
    <div class="archive-item__number">{edition_num:03d}</div>
    <div class="archive-item__content">
      <span class="archive-item__date">{date_formatted}</span>
      <h3 class="archive-item__title">{title}</h3>
      <p class="archive-item__excerpt">{excerpt}</p>
    </div>
    <span class="archive-item__category">Story</span>
    <span class="archive-item__arrow">→</span>
  </a>
'''
    
    # Read current content
    content = bits_index.read_text()
    
    # Replace archive list - match from opening tag to the next closing div at the same level
    pattern = r'(<div class="archive-list">)(.*?)(\n</div>)'
    content = re.sub(
        pattern,
        f'\\g<1>\n{archive_html}\\g<3>',
        content,
        flags=re.DOTALL
    )
    
    bits_index.write_text(content)
    print(f"Updated bits/index.md with {len(story_files)} stories")
    return True


def update_links_index():
    """Update the links index page with all link posts."""
    links_index = Path("docs/links/index.md")
    if not links_index.exists():
        print("Warning: links/index.md not found")
        return False
    
    posts_dir = Path("docs/links/posts")
    if not posts_dir.exists():
        return False
    
    # Get all link files, sorted by date (newest first)
    link_files = sorted(posts_dir.glob("*.md"), reverse=True)
    
    # Build archive list HTML
    archive_html = ""
    for link_file in link_files:
        content = link_file.read_text()
        
        # Parse frontmatter
        title = ""
        date_str = ""
        if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            title = match.group(1)
        if match := re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE):
            date_str = match.group(1)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%B %d, %Y")
            # Calculate edition number from date
            post_date = date_obj.date()
            edition_num = (post_date - LAUNCH_DATE).days + 1
        
        # Count links in the post
        link_count = len(re.findall(r'^## \d+\.', content, re.MULTILINE))
        
        slug = link_file.stem
        
        archive_html += f'''  <a href="posts/{slug}/" class="archive-item archive-item--links">
    <div class="archive-item__number">{edition_num:03d}</div>
    <div class="archive-item__content">
      <span class="archive-item__date">{date_formatted}</span>
      <h3 class="archive-item__title">Daily Discoveries</h3>
      <p class="archive-item__excerpt">Curated obscure links from the hidden corners of the web...</p>
    </div>
    <span class="archive-item__category">{link_count} Links</span>
    <span class="archive-item__arrow">→</span>
  </a>
'''
    
    # Read current content
    content = links_index.read_text()
    
    # Replace archive list - match from opening tag to the next closing div at the same level
    pattern = r'(<div class="archive-list">)(.*?)(\n</div>)'
    content = re.sub(
        pattern,
        f'\\g<1>\n{archive_html}\\g<3>',
        content,
        flags=re.DOTALL
    )
    
    links_index.write_text(content)
    print(f"Updated links/index.md with {len(link_files)} link posts")
    return True


def create_edition_snapshot(edition: int, story: Optional[Dict], links: List[Dict]):
    """Create a snapshot of today's edition for the archive."""
    today = date.today()
    date_str = today.strftime("%Y-%m-%d")
    
    # Create editions/posts directory
    editions_dir = Path("docs/editions/posts")
    editions_dir.mkdir(parents=True, exist_ok=True)
    
    # Create edition file
    edition_file = editions_dir / f"{date_str}-edition-{edition:03d}.md"
    
    # Build content
    story_section = ""
    if story:
        # Extract just the slug from the story URL path
        story_slug = story['url'].split('/')[-2] if story['url'].endswith('/') else story['url'].split('/')[-1]
        story_section = f"""
## Today's Bit

**{story['title']}**

{story['excerpt']}

[Read the full story →](../../../bits/posts/{story_slug}/)
"""
    
    links_section = ""
    if links:
        links_list = "\n".join([f"- [{link['title']}]({link['url']})" for link in links[:5]])
        links_section = f"""
## Today's Links

{links_list}

[View all links →](../../../links/posts/{date_str}-daily-links/)
"""
    
    content = f"""---
title: "Edition #{edition:03d}"
description: "Obscure Bit - {today.strftime('%B %d, %Y')}"
date: {date_str}
---

# Edition #{edition:03d}
## {today.strftime('%B %d, %Y')}

{story_section}
{links_section}
"""
    
    edition_file.write_text(content)
    print(f"Created edition snapshot: {edition_file}")
    return edition_file


def update_editions_index():
    """Update the editions archive page with all past editions."""
    editions_index = Path("docs/editions.md")
    if not editions_index.exists():
        print("Warning: editions.md not found")
        return False
    
    editions_dir = Path("docs/editions/posts")
    if not editions_dir.exists():
        return False
    
    # Get all edition files, sorted by date (newest first)
    edition_files = sorted(editions_dir.glob("*.md"), reverse=True)
    
    # Build archive list HTML
    archive_html = ""
    for edition_file in edition_files:
        content = edition_file.read_text()
        
        # Parse frontmatter
        title = ""
        date_str = ""
        if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            title = match.group(1)
        if match := re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE):
            date_str = match.group(1)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%B %d, %Y")
            edition_num = (date_obj.date() - LAUNCH_DATE).days + 1
        
        slug = edition_file.stem
        
        archive_html += f'''  <a href="posts/{slug}/" class="archive-item">
    <div class="archive-item__number">{edition_num:03d}</div>
    <div class="archive-item__content">
      <span class="archive-item__date">{date_formatted}</span>
      <h3 class="archive-item__title">{title}</h3>
      <p class="archive-item__excerpt">Daily curated story and links from this edition</p>
    </div>
    <span class="archive-item__category">Edition</span>
    <span class="archive-item__arrow">→</span>
  </a>
'''
    
    # Read current content
    content = editions_index.read_text()
    
    # Replace archive list - match from opening tag to the next closing div at the same level
    pattern = r'(<div class="archive-list">)(.*?)(\n</div>)'
    content = re.sub(
        pattern,
        f'\\g<1>\n{archive_html}\\g<3>',
        content,
        flags=re.DOTALL
    )
    
    editions_index.write_text(content)
    print(f"Updated editions.md with {len(edition_files)} editions")
    return True


def main():
    print("Updating landing page with latest content...")
    
    edition = get_edition_number()
    print(f"Edition number: {edition:03d}")
    
    story = get_latest_story()
    if story:
        print(f"Latest story: {story['title']}")
    else:
        print("No story found")
    
    links, total_links = get_latest_links()
    print(f"Found {total_links} links")
    
    if update_home_html(story, links, total_links, edition):
        print("Success! Landing page updated.")
    else:
        print("Failed to update landing page.")
    
    # Create edition snapshot
    print("\nCreating edition snapshot...")
    create_edition_snapshot(edition, story, links)
    
    # Update archive pages
    print("\nUpdating archive pages...")
    update_bits_index()
    update_links_index()
    update_editions_index()


if __name__ == "__main__":
    main()
