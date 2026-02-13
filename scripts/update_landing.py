#!/usr/bin/env python3
"""
Update the landing page (home.html) with the latest story and links content.
Run after generate_story.py and generate_links.py.
"""

import os
import re
import json
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict

# Launch date - edition #001
LAUNCH_DATE = date(2026, 1, 30)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update landing page and archives with latest content")
    parser.add_argument("--theme-json", help="JSON string or path to JSON file specifying today's theme")
    parser.add_argument("--date", help="Override date (YYYY-MM-DD) for backfill edition creation")
    return parser.parse_args()


def resolve_date(date_override: Optional[str] = None) -> date:
    """Return the target date, either from an override string or today."""
    if date_override:
        return datetime.strptime(date_override, "%Y-%m-%d").date()
    return date.today()


def load_theme_override(raw_value: Optional[str]) -> Optional[dict]:
    source = raw_value or os.environ.get("THEME_JSON")
    if not source:
        return None
    try:
        text = source.strip()
        if text.startswith("{"):
            data = json.loads(text)
        else:
            potential = Path(text)
            if potential.exists():
                data = json.loads(potential.read_text())
            else:
                data = json.loads(text)
        return data
    except Exception as e:
        print(f"⚠️  Failed to parse theme override: {e}")
        return None

def get_edition_number(target_date: Optional[date] = None) -> int:
    """Calculate edition number based on days since launch."""
    d = target_date or date.today()
    delta = (d - LAUNCH_DATE).days
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
    theme = ""
    genre = ""
    if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
        title = match.group(1)
    if match := re.search(r'^theme:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
        theme = match.group(1)
    if match := re.search(r'^genre:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
        genre = match.group(1)
    
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
        "theme": theme,
        "genre": genre,
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


def update_home_html(story: Optional[Dict], links: List[Dict], total_links: int, edition: int, theme: Optional[Dict] = None):
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
    
    # Determine theme for category display
    theme_name = None
    if story and story.get('theme'):
        theme_name = story['theme']
    elif theme and theme.get('name'):
        theme_name = theme['name']

    if theme_name:
        content = re.sub(
            r'(<span class="ob-today__category">)[^<]+(</span>)',
            f"\\g<1>{theme_name.title()}\\g<2>",
            content
        )
    
    # Update genre tag (truncate to first phrase before comma)
    genre_label = ""
    if story and story.get('genre'):
        genre_label = story['genre'].split(',')[0].strip()
    if genre_label:
        content = re.sub(
            r'(<span class="ob-today__genre">)[^<]+(</span>)',
            f"\\g<1>{genre_label}\\g<2>",
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
        # Latest links slug = latest file stem
        latest_links = sorted(Path("docs/links/posts").glob("*.md"), reverse=True)
        latest_slug = latest_links[0].stem if latest_links else ""
        cta_href = f"{{{{ 'links/posts/{latest_slug}/' | url }}}}" if latest_slug else "{{ 'links/' | url }}"
        links_html += f'''
      <a href="{cta_href}" class="ob-link ob-link--more">
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
        theme_name = ""
        genre = ""
        if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            title = match.group(1)
        if match := re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE):
            date_str = match.group(1)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%B %d, %Y")
            # Calculate edition number from date
            post_date = date_obj.date()
            edition_num = (post_date - LAUNCH_DATE).days + 1
        if match := re.search(r'^theme:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            theme_name = match.group(1)
        if match := re.search(r'^genre:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            genre = match.group(1)
        
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
        
        genre_short = genre.split(',')[0].strip() if genre else ''
        theme_tag = f'<span class="archive-item__theme">{theme_name.title()}</span>' if theme_name else ''
        genre_tag = f'<span class="archive-item__genre">{genre_short}</span>' if genre_short else ''
        tags_html = ''
        if theme_tag or genre_tag:
            tags_html = f'\n      <div class="archive-item__tags">{theme_tag}{genre_tag}</div>'
        archive_html += f'''  <a href="posts/{slug}/" class="archive-item">
    <div class="archive-item__number">{edition_num:03d}</div>
    <div class="archive-item__content">
      <span class="archive-item__date">{date_formatted}</span>
      <h3 class="archive-item__title">{title}</h3>
      <p class="archive-item__excerpt">{excerpt}</p>{tags_html}
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
        theme = ""
        if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            title = match.group(1)
        if match := re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE):
            date_str = match.group(1)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%B %d, %Y")
            # Calculate edition number from date
            post_date = date_obj.date()
            edition_num = (post_date - LAUNCH_DATE).days + 1
        if match := re.search(r'^theme:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            theme = match.group(1)
        
        # Count links in the post
        link_count = len(re.findall(r'^## \d+\.', content, re.MULTILINE))
        
        slug = link_file.stem
        
        theme_tag = f'<span class="archive-item__theme">{theme.title()}</span>' if theme else ''
        tags_html = ''
        if theme_tag:
            tags_html = f'\n      <div class="archive-item__tags">{theme_tag}</div>'
        archive_html += f'''  <a href="posts/{slug}/" class="archive-item archive-item--links">
    <div class="archive-item__number">{edition_num:03d}</div>
    <div class="archive-item__content">
      <span class="archive-item__date">{date_formatted}</span>{tags_html}
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


def create_edition_snapshot(edition: int, story: Optional[Dict], links: List[Dict], theme: Optional[Dict] = None, target_date: Optional[date] = None):
    """Create a snapshot of an edition for the archive."""
    today = target_date or date.today()
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
    
    # Get theme from story or fallback
    theme_name = 'unknown'
    if story and story.get('theme'):
        theme_name = story['theme']
    elif theme and theme.get('name'):
        theme_name = theme['name']
    
    genre = ''
    if story and story.get('genre'):
        genre = story['genre']
    
    genre_line = f'\ngenre: "{genre}"' if genre else ''
    content = f"""---
title: "Edition #{edition:03d}"
description: "Obscure Bit - {today.strftime('%B %d, %Y')}"
date: {date_str}
theme: "{theme_name}"{genre_line}
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
        theme_name = ""
        genre = ""
        if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            title = match.group(1)
        if match := re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE):
            date_str = match.group(1)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%B %d, %Y")
            edition_num = (date_obj.date() - LAUNCH_DATE).days + 1
        if match := re.search(r'^theme:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            theme_name = match.group(1)
        if match := re.search(r'^genre:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
            genre = match.group(1)

        summary_text = ""
        bit_section = None
        if match := re.search(r"## Today's Bit(.*?)(## Today's Links|\Z)", content, re.S):
            bit_section = match.group(1)
        if bit_section:
            if match := re.search(r"\*\*(.+?)\*\*\s*\n\n(.+?)\n\n", bit_section, re.S):
                paragraph = match.group(2).strip()
            else:
                # Fallback: first non-empty line
                paragraph = ""
                for line in bit_section.splitlines():
                    line = line.strip()
                    if line and not line.startswith("**") and not line.startswith("["):
                        paragraph = line
                        break
            if paragraph:
                clean = re.sub(r"\s+", " ", paragraph)
                summary_text = clean[:160].rstrip()
                if len(clean) > 160:
                    summary_text += "..."

        if theme_name and summary_text:
            excerpt = f"{theme_name.title()} · {summary_text}"
        elif summary_text:
            excerpt = summary_text
        elif theme_name:
            excerpt = f"Theme: {theme_name.title()} — story + curated links."
        else:
            excerpt = "Daily curated story and links from this edition"
        
        slug = edition_file.stem
        
        genre_short = genre.split(',')[0].strip() if genre else ''
        theme_tag = f'<span class="archive-item__theme">{theme_name.title()}</span>' if theme_name else ''
        genre_tag = f'<span class="archive-item__genre">{genre_short}</span>' if genre_short else ''
        tags_html = ''
        if theme_tag or genre_tag:
            tags_html = f'\n      <div class="archive-item__tags">{theme_tag}{genre_tag}</div>'
        archive_html += f'''  <a href="posts/{slug}/" class="archive-item">
    <div class="archive-item__number">{edition_num:03d}</div>
    <div class="archive-item__content">
      <span class="archive-item__date">{date_formatted}</span>
      <h3 class="archive-item__title">{title}</h3>
      <p class="archive-item__excerpt">{excerpt}</p>{tags_html}
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


def get_story_for_date(target_date: date) -> Optional[Dict]:
    """Find and parse the story for a specific date."""
    posts_dir = Path("docs/bits/posts")
    if not posts_dir.exists():
        return None
    
    date_str = target_date.strftime("%Y-%m-%d")
    matches = list(posts_dir.glob(f"{date_str}-*.md"))
    if not matches:
        return None
    
    latest = matches[0]
    content = latest.read_text()
    
    title = ""
    theme = ""
    genre = ""
    if match := re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
        title = match.group(1)
    if match := re.search(r'^theme:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
        theme = match.group(1)
    if match := re.search(r'^genre:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE):
        genre = match.group(1)
    
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
    
    slug = latest.stem
    url_path = f"bits/posts/{slug}/"
    
    return {
        "title": title,
        "excerpt": excerpt,
        "url": url_path,
        "date": date_str,
        "theme": theme,
        "genre": genre,
    }


def get_links_for_date(target_date: date) -> tuple[List[Dict], int]:
    """Find and parse links for a specific date. Returns (links, total_count)."""
    posts_dir = Path("docs/links/posts")
    if not posts_dir.exists():
        return [], 0
    
    date_str = target_date.strftime("%Y-%m-%d")
    filepath = posts_dir / f"{date_str}-daily-links.md"
    if not filepath.exists():
        return [], 0
    
    content = filepath.read_text()
    links = []
    
    sections = re.split(r'^## \d+\.\s+', content, flags=re.MULTILINE)[1:]
    total_count = len(sections)
    
    for section in sections[:3]:
        lines = section.strip().split("\n")
        title = lines[0].strip() if lines else "Untitled"
        
        url = "#"
        if match := re.search(r'href="([^"]+)"', section):
            url = match.group(1)
        
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


def main():
    args = parse_args()
    theme_override = load_theme_override(args.theme_json)
    theme = theme_override or {}
    target_date = resolve_date(args.date) if args.date else None

    if target_date:
        # Backfill mode: create edition for a specific date, then rebuild archives
        print(f"Backfill mode: creating edition for {target_date}...")
        edition = get_edition_number(target_date)
        print(f"Edition number: {edition:03d}")
        
        story = get_story_for_date(target_date)
        if story:
            print(f"Story for {target_date}: {story['title']}")
        else:
            print(f"No story found for {target_date}")
        
        links, total_links = get_links_for_date(target_date)
        print(f"Found {total_links} links for {target_date}")
        
        print("\nCreating edition snapshot...")
        create_edition_snapshot(edition, story, links, theme, target_date)
        
        print("\nUpdating archive pages...")
        update_bits_index()
        update_links_index()
        update_editions_index()
    else:
        # Normal mode: update landing page with latest content
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
        
        if update_home_html(story, links, total_links, edition, theme):
            print("Success! Landing page updated.")
        else:
            print("Failed to update landing page.")
        
        # Create edition snapshot
        print("\nCreating edition snapshot...")
        create_edition_snapshot(edition, story, links, theme)
        
        # Update archive pages
        print("\nUpdating archive pages...")
        update_bits_index()
        update_links_index()
        update_editions_index()


if __name__ == "__main__":
    main()
