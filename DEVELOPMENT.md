# Development Guide

Technical documentation for developers working on Obscure Bit.

## Quick Start

```bash
# Clone and install
git clone https://github.com/obscurebit/b1ts.git
cd b1ts
pip install -r requirements.txt
```

## Local Development

### Serve Locally

```bash
# Start development server with live reload
python3 -m mkdocs serve

# Or if mkdocs is in PATH
mkdocs serve
```

Site available at: **http://127.0.0.1:8000**

Changes to files in `docs/` and `overrides/` will auto-reload.

### Build Site

```bash
# Build static site to site/ directory
python3 -m mkdocs build

# Preview built site (no live reload)
python3 -m http.server 8000 --directory site
```

### Common Issues

**`mkdocs: command not found`**
```bash
# Use python module syntax instead
python3 -m mkdocs serve
```

**Missing dependencies**
```bash
pip install mkdocs-material
```

## Environment Setup

### Required Environment Variables

```bash
export OPENAI_API_KEY="your-nvidia-nim-api-key"
export OPENAI_API_BASE="https://integrate.api.nvidia.com/v1"
export OPENAI_MODEL="nvidia/llama-3.3-nemotron-super-49b-v1.5"
export SERPAPI_KEY="optional-serpapi-key"              # Enables resilient Google results
export CONTEXTUALWEB_API_KEY="optional-rapidapi-key"  # Backup search provider
```

### GitHub Secrets (for CI)

| Secret | Description |
|--------|-------------|
| `OPENAI_API_KEY` | NVIDIA NIM API key |
| `OPENAI_API_BASE` | API endpoint (optional) |
| `OPENAI_MODEL` | Model name (optional) |
| `SERPAPI_KEY` | Optional SerpAPI key for reliable Google results |
| `CONTEXTUALWEB_API_KEY` | Optional RapidAPI key for ContextualWeb backup |

## Scripts

### Content Generation

```bash
# Full daily run (story + links + landing)
python scripts/run_daily.py

# Generate a new story
python scripts/generate_story.py

# Generate new links
python scripts/generate_links.py

# Update landing pages and archives
python scripts/update_landing.py
```

### Substack Publishing

Substack uses Cloudflare protection that blocks automated requests. We use a two-script approach:

#### 1. Cookie Extraction (One-time setup)

```bash
# Install Playwright (one-time)
pip3 install playwright
python3 -m playwright install chromium

# Login and extract cookies (opens browser)
python3 scripts/substack_playwright.py --login

# Export cookies for GitHub Actions (optional)
python3 scripts/substack_playwright.py --export-cookies
```

Cookies are saved to `~/.substack_cookies.json`.

#### 2. Publishing with API

```bash
# Set environment variables
export SUBSTACK_PUBLICATION_URL="https://obscurebit.substack.com"
export SUBSTACK_COOKIES_PATH="$HOME/.substack_cookies.json"

# Create draft for edition
python3 scripts/publish_substack.py --edition 3 --draft

# Publish directly
python3 scripts/publish_substack.py --edition 3 --publish

# Force republish
python3 scripts/publish_substack.py --edition 3 --publish --force
```

#### Alternative: Manual Cookie Export

1. Log in to substack.com in your browser
2. Open Developer Tools → Application → Cookies → substack.com
3. Click "Export all as JSON" or copy manually
4. Save to file: `~/.substack_cookies.json`
5. Set env: `export SUBSTACK_COOKIES_PATH="$HOME/.substack_cookies.json"`

## Project Structure

```
b1ts/
├── .github/workflows/
│   ├── deploy.yml              # GitHub Pages deployment
│   └── generate-content.yml    # Daily content generation (6 AM UTC)
├── docs/
│   ├── bits/posts/             # Daily stories (YYYY-MM-DD-slug.md)
│   ├── links/posts/            # Daily links
│   ├── editions/posts/         # Daily edition snapshots
│   ├── substack/               # Newsletter drafts & markers
│   ├── stylesheets/            # Custom CSS
│   └── javascripts/            # Custom JS
├── scripts/
│   ├── generate_story.py       # AI story generation
│   ├── generate_links.py       # Links generation w/ LLM research + multi-source search
│   ├── update_landing.py       # Landing page updater
│   ├── publish_substack.py     # Substack publishing via API
│   └── substack_playwright.py  # Cookie extraction helper
├── prompts/
│   ├── story_system.md         # Story generation system prompt
│   ├── links_system.md         # Links generation system prompt
│   └── themes.yaml             # Unified themes for stories + links
├── overrides/
│   ├── home.html               # Custom homepage template
│   └── main.html               # Base template override
├── mkdocs.yml                  # MkDocs configuration
└── requirements.txt            # Python dependencies
```

## Workflows

### Daily Content Generation

Runs daily at 6 AM UTC via `.github/workflows/generate-content.yml`:

1. Generate story → `docs/bits/posts/`
2. Generate links → `docs/links/posts/`
3. Update landing pages and archives
4. Commit and push → triggers GitHub Pages deploy

#### Manual Orchestration

Use `scripts/run_daily.py` to run all three steps locally with a single command:

```bash
python scripts/run_daily.py
```

**Options**

```bash
# Provide explicit theme JSON (string or path)
python scripts/run_daily.py --theme-json '{"name": "quantum mysteries", "story": "decoder cults", "links": "analog cryptography"}'
python scripts/run_daily.py --theme-json path/to/custom-theme.json

# Pick a specific date from themes.yaml (uses overrides or rotation)
python scripts/run_daily.py --date 2026-02-14

# Skip specific steps if needed
python scripts/run_daily.py --skip-story      # links + landing only
python scripts/run_daily.py --skip-links      # story + landing only
python scripts/run_daily.py --skip-landing    # story + links only

# Pass overrides directly to individual scripts
python scripts/generate_links.py --theme-json '{"name": "lost utilities", "story": "haunted telecom", "links": "abandoned power grids"}'
python scripts/generate_story.py --theme-json custom-theme.json
python scripts/update_landing.py --theme-json custom-theme.json

# Provide optional search API keys for resilient link generation
export SERPAPI_KEY="..."
export CONTEXTUALWEB_API_KEY="..."
```

When `--theme-json` is omitted, all scripts fall back to loading `prompts/themes.yaml` (with date overrides). Setting the `THEME_JSON` environment variable has the same effect as passing `--theme-json`.

### Manual Trigger

Actions → "Generate Daily Content" → "Run workflow"

Options:
- Generate story only
- Generate links only
- Generate both

## Edition System

Editions are numbered from launch date (2026-01-30):
- Edition #001 = Jan 30, 2026
- Edition #002 = Jan 31, 2026
- etc.

The `get_edition_number()` function in scripts calculates this.

## Unified Theming System

All daily content shares a cohesive theme through `prompts/themes.yaml`:

### Theme Structure
```yaml
themes:
  - name: "quantum mysteries"
    story: "quantum computing paradoxes"
    links: "quantum physics papers"
  - name: "biological computing"
    story: "DNA-based data storage"
    links: "synthetic biology research"
```

### Theme Selection
- 18 rotating themes (day of year % 18)
- Date-specific overrides for special editions
- Theme included in frontmatter of all content

### Implementation
- `generate_story.py` uses theme's `story` direction
- `generate_links.py` uses theme's `links` direction
- Theme displayed on landing page and archive pages
- Edition snapshots include theme metadata

## Substack Integration

### Architecture

We use a two-script approach to bypass Cloudflare protection:

1. **`substack_playwright.py`** - Extracts cookies via browser automation
2. **`publish_substack.py`** - Uses those cookies for clean API publishing

### Cookie Authentication

The system supports two cookie methods:

**File-based (recommended for local):**
```bash
export SUBSTACK_COOKIES_PATH="$HOME/.substack_cookies.json"
```

**Environment variable (for CI):**
```bash
export SUBSTACK_COOKIES='[{"name":"session", "value":"..."}]'
```

### Publishing Flow

1. Extract cookies once with Playwright (bypasses Cloudflare)
2. Use cookies with Substack API (clean, reliable)
3. API creates draft → prepublish → publish
4. Marker file prevents duplicate publishing

### Published Markers

After publishing, a marker file is created:
```
docs/substack/edition-003-published.txt
```

This prevents duplicate publishing. Use `--force` to override.

## Tech Stack

- **Site**: MkDocs Material
- **AI**: NVIDIA NIM API (Llama 3.3 Nemotron)
- **Hosting**: GitHub Pages
- **CI**: GitHub Actions
- **Substack**: Playwright + API (cookie-based auth)

## See Also

- [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) - Architecture diagrams and flows
