# Obscure Bit (b1ts)

A fully automated website that curates obscure, fascinating internet content and delivers daily AI-generated sci-fi stories. Powered by MkDocs Material and GitHub Pages.

## Features

- **Obscure Links**: Daily curated discoveries from hidden corners of the web
- **Daily Bits**: AI-generated short stories exploring sci-fi, mysteries, and speculative concepts
- **Zero Cost**: Static hosting via GitHub Pages
- **Fully Automated**: GitHub Actions generates and publishes content daily

## Setup

### 1. Clone and Configure

```bash
git clone https://github.com/yourusername/b1ts.git
cd b1ts
```

### 2. Set GitHub Secrets

Add these secrets to your repository (Settings → Secrets and variables → Actions):

| Secret | Description |
|--------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (or compatible provider) |
| `OPENAI_API_BASE` | API base URL (default: `https://api.openai.com/v1`) |
| `OPENAI_MODEL` | Model to use (default: `gpt-4o-mini`) |

### 3. Enable GitHub Pages

1. Go to Settings → Pages
2. Set Source to "GitHub Actions"

### 4. Update Site URL

Edit `mkdocs.yml` and update `site_url` to match your GitHub Pages URL.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Serve locally
mkdocs serve

# Build site
mkdocs build
```

## Manual Content Generation

You can manually trigger content generation:

1. Go to Actions → "Generate Daily Content"
2. Click "Run workflow"
3. Select which content to generate

## Project Structure

```
b1ts/
├── docs/
│   ├── index.md              # Homepage
│   ├── about.md              # About page
│   ├── bits/                 # Daily stories
│   │   ├── index.md
│   │   └── posts/            # Story markdown files
│   ├── links/                # Curated links
│   │   ├── index.md
│   │   └── posts/            # Link collection files
│   ├── stylesheets/          # Custom CSS
│   └── javascripts/          # Custom JS
├── scripts/
│   ├── generate_story.py     # Story generation script
│   └── generate_links.py     # Links generation script
├── .github/workflows/
│   ├── deploy.yml            # Site deployment
│   └── generate-content.yml  # Daily content generation
├── mkdocs.yml                # MkDocs configuration
└── requirements.txt          # Python dependencies
```

## License

MIT