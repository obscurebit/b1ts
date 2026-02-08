#!/usr/bin/env python3
"""
Generate a daily AI story for Obscure Bit.
Uses OpenAI-compatible API endpoints.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from openai import OpenAI

# Configuration
API_BASE = os.environ.get("OPENAI_API_BASE", "https://integrate.api.nvidia.com/v1")
API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = os.environ.get("OPENAI_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1.5")

# Paths to prompt files
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "story_system.md"
THEMES_FILE = PROMPTS_DIR / "themes.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the daily Obscure Bit story")
    parser.add_argument("--theme-json", help="JSON string or path to JSON file specifying today's theme")
    return parser.parse_args()


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
        print(f"Using theme override: {data.get('name', 'custom')}")
        return data
    except Exception as e:
        print(f"⚠️  Failed to parse theme override: {e}")
        return None


def load_system_prompt() -> str:
    """Load the system prompt from external file."""
    if not SYSTEM_PROMPT_FILE.exists():
        print(f"Error: System prompt file not found at {SYSTEM_PROMPT_FILE}")
        sys.exit(1)
    return SYSTEM_PROMPT_FILE.read_text().strip()


def load_themes() -> dict:
    """Load unified themes configuration from YAML file."""
    if not THEMES_FILE.exists():
        print(f"Error: Themes file not found at {THEMES_FILE}")
        sys.exit(1)
    return yaml.safe_load(THEMES_FILE.read_text()) or {}


def get_daily_theme() -> dict:
    """Get today's theme (story + links directions)."""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    day_of_year = today.timetuple().tm_yday
    
    config = load_themes()
    
    # Check for date-specific override
    overrides = config.get("overrides", {})
    if date_str in overrides:
        theme = overrides[date_str]
        print(f"Using theme override for {date_str}: {theme.get('name', 'custom')}")
        return theme
    
    # Use rotating themes
    themes = config.get("themes", [])
    if not themes:
        print("Error: No themes found in themes.yaml")
        sys.exit(1)
    
    theme = themes[day_of_year % len(themes)]
    print(f"Using theme: {theme.get('name', 'unknown')}")
    return theme


def build_story_prompt(theme: dict) -> str:
    """Generate a unique prompt for today's story based on theme."""
    story_direction = theme.get("story", theme.get("name", "mysterious technology"))
    return f"""Write a short sci-fi story exploring: {story_direction}

Make it feel like discovering a hidden gem - something readers wouldn't find anywhere else. 
The story should feel complete but leave readers thinking."""


def generate_story(theme: dict) -> tuple[str, str, str]:
    """Generate a story using the OpenAI-compatible API."""
    if not API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    client = OpenAI(
        api_key=API_KEY,
        base_url=API_BASE,
    )
    
    system_prompt = load_system_prompt()
    user_prompt = build_story_prompt(theme)
    
    print(f"System prompt loaded from: {SYSTEM_PROMPT_FILE}")
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.6,
        top_p=0.95,
        max_tokens=4096,
    )
    
    content = response.choices[0].message.content.strip()
    
    # Strip <think>...</think> reasoning blocks (used by some models like Nemotron)
    if "<think>" in content and "</think>" in content:
        think_end = content.find("</think>")
        content = content[think_end + len("</think>"):].strip()
    
    # Remove markdown code block fences if present
    if content.startswith("```"):
        # Find the closing fence
        lines = content.split("\n")
        # Skip opening fence line
        if lines[0].strip() == "```":
            lines = lines[1:]
        # Remove closing fence if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    
    # Parse title and story
    lines = content.split("\n", 2)
    title = lines[0].strip().lstrip("#").strip()
    story = lines[2].strip() if len(lines) > 2 else content
    
    theme_name = theme.get("name", "unknown")
    
    return title, story, theme_name


def save_story(title: str, story: str, theme_name: str) -> Path:
    """Save the story as a markdown file in the bits/posts directory."""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    
    # Create slug from title
    slug = title.lower()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split()[:6])
    
    # Ensure posts directory exists
    posts_dir = Path("docs/bits/posts")
    posts_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename
    filename = f"{date_str}-{slug}.md"
    filepath = posts_dir / filename
    
    # Get git commit hash
    import subprocess
    try:
        commit_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
        commit_url = f"https://github.com/obscurebit/b1ts/commit/{commit_hash}"
    except:
        commit_hash = "unknown"
        commit_url = "#"
    
    # Create markdown file
    frontmatter = f"""---
date: {date_str}
title: "{title}"
description: "A daily AI-generated story exploring speculative fiction"
author: "{API_BASE} / {MODEL}"
theme: "{theme_name}"
---

"""
    content = f"""{frontmatter}# {title}

{story}

---

<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 2rem;">
  <button class="share-btn" data-url="{{% raw %}}{{{{ page.canonical_url }}}}{{% endraw %}}" data-title="{title}">
    Share this story
  </button>
  <a href="{commit_url}" target="_blank" rel="noopener" style="font-size: 0.75rem; color: var(--md-default-fg-color--light); text-decoration: none; font-family: monospace;">
    gen:{commit_hash}
  </a>
</div>
"""
    
    filepath.write_text(content)
    print(f"Story saved to: {filepath}")
    return filepath


def main():
    args = parse_args()
    theme_override = load_theme_override(args.theme_json)
    theme = theme_override or get_daily_theme()
    print("Generating daily story...")
    print(f"Using API base: {API_BASE}")
    print(f"Using model: {MODEL}")
    print(f"Theme: {theme.get('name', 'unknown')}")
    
    title, story, theme_name = generate_story(theme)
    print(f"Generated story: {title}")
    
    filepath = save_story(title, story, theme_name)
    print(f"Success! Story saved to {filepath}")


if __name__ == "__main__":
    main()
