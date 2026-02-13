#!/usr/bin/env python3
"""
Generate a daily AI story for Obscure Bit.
Uses OpenAI-compatible API endpoints.
"""

import os
import sys
import json
import random
import hashlib
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
STYLE_MODIFIERS_FILE = PROMPTS_DIR / "style_modifiers.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the daily Obscure Bit story")
    parser.add_argument("--theme-json", help="JSON string or path to JSON file specifying today's theme")
    parser.add_argument("--date", help="Override date (YYYY-MM-DD) for backfill generation")
    return parser.parse_args()


def resolve_date(date_override: Optional[str] = None) -> datetime:
    """Return the target date, either from an override string or today."""
    if date_override:
        return datetime.strptime(date_override, "%Y-%m-%d")
    return datetime.now()


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


def load_style_modifiers() -> dict:
    """Load style modifier pools from YAML file."""
    if not STYLE_MODIFIERS_FILE.exists():
        print(f"Warning: Style modifiers file not found at {STYLE_MODIFIERS_FILE}")
        return {}
    return yaml.safe_load(STYLE_MODIFIERS_FILE.read_text()) or {}


def get_daily_seed(target_date: Optional[datetime] = None) -> int:
    """Generate a deterministic-but-unique seed from a date.
    
    Uses a hash so the same date always produces the same story constraints,
    but different dates produce wildly different selections.
    """
    dt = target_date or datetime.now()
    date_str = dt.strftime("%Y-%m-%d")
    return int(hashlib.sha256(date_str.encode()).hexdigest(), 16)


def select_style_modifiers(target_date: Optional[datetime] = None) -> dict:
    """Pick one random option from each style dimension, seeded by date."""
    modifiers = load_style_modifiers()
    if not modifiers:
        return {}
    
    rng = random.Random(get_daily_seed(target_date))
    
    selected = {}
    for key in ["pov", "tone", "era", "setting", "structure", "conflict", "opening", "genre", "wildcard"]:
        options = modifiers.get(key, [])
        if options:
            selected[key] = rng.choice(options)
    
    # Select a banned word set
    banned_sets = modifiers.get("banned_word_sets", [])
    if banned_sets:
        selected["banned_words"] = rng.choice(banned_sets)
    
    return selected


def build_story_prompt(theme: dict, target_date: Optional[datetime] = None) -> tuple[str, str]:
    """Generate a unique prompt for today's story based on theme + randomized style modifiers.
    
    Returns (prompt_text, genre_label) so genre can be stored in frontmatter.
    """
    story_direction = theme.get("story", theme.get("name", "mysterious technology"))
    style = select_style_modifiers(target_date)
    
    parts = [f"Write a short speculative fiction story exploring: {story_direction}"]
    parts.append("")
    
    if style:
        parts.append("TODAY'S CONSTRAINTS (follow these strictly):")
        if "pov" in style:
            parts.append(f"- Point of view: {style['pov']}")
        if "tone" in style:
            parts.append(f"- Tone: {style['tone']}")
        if "era" in style:
            parts.append(f"- Setting era: {style['era']}")
        if "setting" in style:
            parts.append(f"- Setting location: {style['setting']}")
        if "structure" in style:
            parts.append(f"- Narrative structure: {style['structure']}")
        if "conflict" in style:
            parts.append(f"- Central conflict: {style['conflict']}")
        if "opening" in style:
            parts.append(f"- Opening: {style['opening']}")
        if "genre" in style:
            parts.append(f"- Genre flavor: {style['genre']}")
        if "wildcard" in style:
            parts.append(f"- Wildcard constraint: {style['wildcard']}")
        if "banned_words" in style:
            words = ", ".join(style["banned_words"])
            parts.append(f"- BANNED WORDS (do not use these): {words}")
        parts.append("")
    
    parts.append("Make it feel like discovering a hidden gem—something readers wouldn't find anywhere else.")
    parts.append("The story should feel complete but leave readers thinking.")
    
    prompt = "\n".join(parts)
    genre = style.get("genre", "speculative fiction")
    print(f"Style modifiers: {json.dumps(style, indent=2, default=str)}")
    return prompt, genre


def generate_story(theme: dict, target_date: Optional[datetime] = None) -> tuple[str, str, str, str]:
    """Generate a story using the OpenAI-compatible API.
    
    Returns (title, story, theme_name, genre).
    """
    if not API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    client = OpenAI(
        api_key=API_KEY,
        base_url=API_BASE,
    )
    
    system_prompt = load_system_prompt()
    user_prompt, genre = build_story_prompt(theme, target_date)
    
    print(f"System prompt loaded from: {SYSTEM_PROMPT_FILE}")
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
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
    
    return title, story, theme_name, genre


def save_story(title: str, story: str, theme_name: str, genre: str = "speculative fiction", target_date: Optional[datetime] = None) -> Path:
    """Save the story as a markdown file in the bits/posts directory."""
    today = target_date or datetime.now()
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
        commit_url = f"https://github.com/obscurebit/b1ts/tree/{commit_hash}"
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
genre: "{genre}"
---

"""
    content = f"""{frontmatter}# {title}

{story}

---

<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 2rem;">
  <button class="share-btn" data-url="{{% raw %}}{{{{ page.canonical_url }}}}{{% endraw %}}" data-title="{title}">
    Share this story
  </button>
  <a href="{commit_url}" target="_blank" rel="noopener" class="story-gen-link">
    gen:{commit_hash}
  </a>
</div>
"""
    
    filepath.write_text(content)
    print(f"Story saved to: {filepath}")
    return filepath


def main():
    args = parse_args()
    target_date = resolve_date(args.date) if args.date else None
    theme_override = load_theme_override(args.theme_json)
    theme = theme_override or get_daily_theme()
    date_label = (target_date or datetime.now()).strftime("%Y-%m-%d")
    print(f"Generating story for {date_label}...")
    print(f"Using API base: {API_BASE}")
    print(f"Using model: {MODEL}")
    print(f"Theme: {theme.get('name', 'unknown')}")
    
    title, story, theme_name, genre = generate_story(theme, target_date)
    print(f"Generated story: {title}")
    print(f"Genre: {genre}")
    
    filepath = save_story(title, story, theme_name, genre, target_date)
    print(f"Success! Story saved to {filepath}")


if __name__ == "__main__":
    main()
