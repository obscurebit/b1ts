#!/usr/bin/env python3
"""
Generate a daily AI story for Obscure Bit.
Uses OpenAI-compatible API endpoints.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from openai import OpenAI

# Configuration
API_BASE = os.environ.get("OPENAI_API_BASE", "https://integrate.api.nvidia.com/v1")
API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = os.environ.get("OPENAI_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1.5")

# Paths to prompt files
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "story_system.md"
SEED_PROMPTS_FILE = PROMPTS_DIR / "seed_prompts.yaml"


def load_system_prompt() -> str:
    """Load the system prompt from external file."""
    if not SYSTEM_PROMPT_FILE.exists():
        print(f"Error: System prompt file not found at {SYSTEM_PROMPT_FILE}")
        sys.exit(1)
    return SYSTEM_PROMPT_FILE.read_text().strip()


def load_seed_config() -> dict:
    """Load seed prompts configuration from YAML file."""
    if not SEED_PROMPTS_FILE.exists():
        print(f"Error: Seed prompts file not found at {SEED_PROMPTS_FILE}")
        sys.exit(1)
    return yaml.safe_load(SEED_PROMPTS_FILE.read_text()) or {}


def get_story_prompt() -> str:
    """Generate a unique prompt for today's story."""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    day_of_year = today.timetuple().tm_yday
    
    config = load_seed_config()
    
    # Check for date-specific seed prompt
    seeds = config.get("seeds", {})
    if date_str in seeds:
        seed_prompt = seeds[date_str]
        print(f"Using seed prompt for {date_str}")
        return f"""{seed_prompt}

Make it feel like discovering a hidden gem - something readers wouldn't find anywhere else.
The story should feel complete but leave readers thinking."""
    
    # Use default themes from config
    default_themes = config.get("default_themes", [])
    if not default_themes:
        print("Error: No default_themes found in seed prompts configuration")
        sys.exit(1)
    
    theme = default_themes[day_of_year % len(default_themes)]
    
    return f"""Write a short sci-fi story exploring the theme of: {theme}

Make it feel like discovering a hidden gem - something readers wouldn't find anywhere else. 
The story should feel complete but leave readers thinking."""


def generate_story() -> tuple[str, str]:
    """Generate a story using the OpenAI-compatible API."""
    if not API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    client = OpenAI(
        api_key=API_KEY,
        base_url=API_BASE,
    )
    
    system_prompt = load_system_prompt()
    user_prompt = get_story_prompt()
    
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
    
    # Parse title and story
    lines = content.split("\n", 2)
    title = lines[0].strip().lstrip("#").strip()
    story = lines[2].strip() if len(lines) > 2 else content
    
    return title, story


def save_story(title: str, story: str) -> Path:
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
    
    # Create markdown file
    frontmatter = f"""---
date: {date_str}
title: "{title}"
description: "A daily AI-generated story exploring speculative fiction"
author: "{API_BASE} / {MODEL}"
---

"""
    content = f"""{frontmatter}# {title}

{story}

---

<button class="share-btn" data-url="{{% raw %}}{{{{ page.canonical_url }}}}{{% endraw %}}" data-title="{title}">
  Share this story
</button>
"""
    
    filepath.write_text(content)
    print(f"Story saved to: {filepath}")
    return filepath


def main():
    print("Generating daily story...")
    print(f"Using API base: {API_BASE}")
    print(f"Using model: {MODEL}")
    
    title, story = generate_story()
    print(f"Generated story: {title}")
    
    filepath = save_story(title, story)
    print(f"Success! Story saved to {filepath}")


if __name__ == "__main__":
    main()
