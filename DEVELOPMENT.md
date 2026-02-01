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
```

### GitHub Secrets (for CI)

| Secret | Description |
|--------|-------------|
| `OPENAI_API_KEY` | NVIDIA NIM API key |
| `OPENAI_API_BASE` | API endpoint (optional) |
| `OPENAI_MODEL` | Model name (optional) |

## Scripts

### Content Generation

```bash
# Generate a new story
python scripts/generate_story.py

# Generate new links
python scripts/generate_links.py

# Update landing pages and archives
python scripts/update_landing.py
```

### Substack Publishing (Local Only)

Substack uses Cloudflare protection that blocks GitHub Actions datacenter IPs. Publishing must be done locally.

```bash
# One-time setup
pip3 install playwright
python3 -m playwright install chromium

# Login to Substack (opens browser, saves session)
python3 scripts/substack_playwright.py --login

# Create draft for edition
python3 scripts/substack_playwright.py --edition 3 --draft

# Publish directly
python3 scripts/substack_playwright.py --edition 3 --publish

# Force republish
python3 scripts/substack_playwright.py --edition 3 --publish --force
```

Browser state is saved to `~/.playwright_state.json`.

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
│   ├── generate_links.py       # AI links generation
│   ├── update_landing.py       # Landing page updater
│   └── substack_playwright.py  # Substack publishing (local only)
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

## Substack Integration

### Why Local Only?

Cloudflare blocks GitHub Actions IPs. We tested:
- API calls with cookies → 403 blocked
- Playwright browser automation → Challenge never passes
- 60+ second waits → Still blocked

### How It Works

1. Run `--login` locally to authenticate via browser
2. Session saved to `~/.playwright_state.json`
3. Run `--edition N --draft` to create drafts
4. Playwright opens headless browser, types content, auto-saves

### Published Markers

After publishing, a marker file is created:
```
docs/substack/edition-003-published.txt
```

This prevents duplicate publishing.

## Tech Stack

- **Site**: MkDocs Material
- **AI**: NVIDIA NIM API (Llama 3.3 Nemotron)
- **Hosting**: GitHub Pages
- **CI**: GitHub Actions
- **Substack**: Playwright (local only)

## See Also

- [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) - Architecture diagrams and flows
