# Obscure Bit

A fully automated daily publication featuring AI-generated sci-fi stories and curated obscure links from the hidden corners of the web. Built with MkDocs Material and powered by NVIDIA NIM API.

🌐 **Live Site**: [obscurebit.com](https://obscurebit.com)

## Features

- **Daily Bits**: AI-generated short stories exploring sci-fi, mysteries, and speculative concepts
- **Obscure Links**: Curated discoveries from the weird, wonderful, and forgotten corners of the web
- **Daily Editions**: Automated snapshots tracking each day's content
- **Zero Cost**: Static hosting via GitHub Pages with custom domain support
- **Fully Automated**: GitHub Actions generates and publishes content daily at 6 AM UTC
- **Modern Design**: Editorial-style layout with sticky headers, smooth animations, and responsive design

## Setup

### 1. Clone and Configure

```bash
git clone https://github.com/obscurebit/b1ts.git
cd b1ts
```

### 2. Set GitHub Secrets

Add these secrets to your repository (Settings → Secrets and variables → Actions):

| Secret | Description | Required |
|--------|-------------|----------|
| `OPENAI_API_KEY` | Your NVIDIA NIM API key | ✅ Yes |
| `OPENAI_API_BASE` | API base URL (default: `https://integrate.api.nvidia.com/v1`) | Optional |
| `OPENAI_MODEL` | Model to use (default: `nvidia/llama-3.3-nemotron-super-49b-v1.5`) | Optional |
| `SUBSTACK_EMAIL` | Your Substack account email | Optional |
| `SUBSTACK_PASSWORD` | Your Substack account password | Optional |
| `SUBSTACK_PUBLICATION_URL` | Your publication URL (e.g., `https://obscurebit.substack.com`) | Optional |

### 3. Enable GitHub Pages

1. Go to Settings → Pages
2. Set Source to "GitHub Actions"
3. (Optional) Add custom domain and configure DNS

### 4. Configure Substack Publishing (Optional)

To automatically publish daily editions to Substack:

1. Create a Substack publication at [substack.com](https://substack.com)
2. Add the three Substack secrets to your GitHub repository (see table above)
3. The daily workflow will automatically publish after content generation

**Note:** Substack doesn't have an official API, so this uses their internal API with your credentials. Your password is stored securely as a GitHub Secret.

### 5. Configure Custom Domain (Optional)

If using a custom domain:

1. Update `site_url` in `mkdocs.yml`
2. Update `docs/CNAME` file with your domain
3. Configure DNS records:
   ```
   A    @    185.199.108.153
   A    @    185.199.109.153
   A    @    185.199.110.153
   A    @    185.199.111.153
   CNAME www  obscurebit.github.io
   ```

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
│   ├── index.md              # Homepage (custom template)
│   ├── about.md              # About page
│   ├── bits/                 # Daily stories
│   │   ├── index.md          # Stories archive
│   │   └── posts/            # Story markdown files
│   ├── links/                # Curated links
│   │   ├── index.md          # Links archive
│   │   └── posts/            # Link collection files
│   ├── editions/             # Daily edition snapshots
│   │   └── posts/            # Edition markdown files
│   ├── editions.md           # Editions archive
│   ├── stylesheets/          # Custom CSS
│   ├── javascripts/          # Custom JS (home, post, extra)
│   └── CNAME                 # Custom domain configuration
├── scripts/
│   ├── generate_story.py     # Story generation script
│   ├── generate_links.py     # Links generation script
│   └── update_landing.py     # Landing page and archive updater
├── prompts/
│   ├── story_system.md       # Story generation system prompt
│   ├── seed_prompts.yaml     # Story seed prompts
│   ├── links_system.md       # Links generation system prompt
│   └── links_seeds.yaml      # Links seed prompts
├── overrides/
│   ├── home.html             # Custom homepage template
│   └── main.html             # Base template override
├── .github/workflows/
│   ├── deploy.yml            # Site deployment to GitHub Pages
│   └── generate-content.yml  # Daily content generation (6 AM UTC)
├── mkdocs.yml                # MkDocs configuration
└── requirements.txt          # Python dependencies
```

## How It Works

1. **Daily at 6 AM UTC**: GitHub Actions workflow triggers
2. **Content Generation**: 
   - `generate_story.py` creates a new AI story using NVIDIA NIM
   - `generate_links.py` curates obscure links with validation
3. **Archive Updates**: `update_landing.py` regenerates:
   - Bits and Links index pages
   - Daily edition snapshot
   - Editions archive page
4. **Deployment**: Changes are committed and site auto-deploys to GitHub Pages

## Tech Stack

- **Static Site Generator**: MkDocs Material
- **AI Provider**: NVIDIA NIM API (Llama 3.3 Nemotron)
- **Hosting**: GitHub Pages
- **CI/CD**: GitHub Actions
- **Language**: Python 3.12

## License

MIT