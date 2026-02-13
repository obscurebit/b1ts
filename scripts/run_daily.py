#!/usr/bin/env python3
"""Orchestrate the full daily generation flow with a single command."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
THEMES_FILE = PROMPTS_DIR / "themes.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full daily Obscure Bit generation pipeline")
    parser.add_argument("--theme-json", help="JSON string or path to JSON file specifying today's theme")
    parser.add_argument("--date", help="Override date (YYYY-MM-DD) when selecting from themes.yaml")
    parser.add_argument("--skip-story", action="store_true", help="Skip story generation")
    parser.add_argument("--skip-links", action="store_true", help="Skip link generation")
    parser.add_argument("--skip-landing", action="store_true", help="Skip landing + archive updates")
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
        print(f"Using theme override from input: {data.get('name', 'custom')}")
        return data
    except Exception as exc:
        print(f"⚠️  Failed to parse theme override: {exc}")
        return None


def load_themes() -> dict:
    if not THEMES_FILE.exists():
        print(f"Error: themes file not found at {THEMES_FILE}")
        sys.exit(1)
    return yaml.safe_load(THEMES_FILE.read_text()) or {}


def select_theme(date_override: Optional[str] = None) -> dict:
    config = load_themes()
    if date_override:
        try:
            target_date = datetime.strptime(date_override, "%Y-%m-%d")
        except ValueError:
            print("Error: --date must be in YYYY-MM-DD format")
            sys.exit(1)
    else:
        target_date = datetime.now()
    date_str = target_date.strftime("%Y-%m-%d")
    day_of_year = target_date.timetuple().tm_yday

    # Date-specific override
    overrides = config.get("overrides", {})
    if date_str in overrides:
        theme = overrides[date_str]
        print(f"Using theme override for {date_str}: {theme.get('name', 'custom')}")
        return theme

    themes = config.get("themes", [])
    if not themes:
        print("Error: no themes defined in themes.yaml")
        sys.exit(1)

    theme = themes[day_of_year % len(themes)]
    print(f"Using rotating theme for {date_str}: {theme.get('name', 'unknown')}")
    return theme


def run_script(label: str, command: list[str], env: dict) -> None:
    print(f"\n▶ {label}: {' '.join(command)}")
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        print(f"❌ {label} failed (exit code {result.returncode})")
        sys.exit(result.returncode)
    print(f"✅ {label} completed")


def main():
    args = parse_args()

    theme = load_theme_override(args.theme_json)
    if not theme:
        theme = select_theme(args.date)

    theme_json = json.dumps(theme)
    shared_env = os.environ.copy()
    shared_env["THEME_JSON"] = theme_json

    print("\n=== Daily Theme ===")
    print(json.dumps(theme, indent=2))

    scripts_dir = Path(__file__).parent

    # Build optional --date flag for child scripts
    date_args = ["--date", args.date] if args.date else []

    if not args.skip_links:
        run_script(
            "Generate Links",
            [sys.executable, str(scripts_dir / "generate_links.py"), "--theme-json", theme_json] + date_args,
            shared_env,
        )

    if not args.skip_story:
        run_script(
            "Generate Story",
            [sys.executable, str(scripts_dir / "generate_story.py"), "--theme-json", theme_json] + date_args,
            shared_env,
        )

    if not args.skip_landing:
        run_script(
            "Update Landing",
            [sys.executable, str(scripts_dir / "update_landing.py"), "--theme-json", theme_json] + date_args,
            shared_env,
        )

    print("\n🎉 Daily pipeline finished successfully!")


if __name__ == "__main__":
    main()
