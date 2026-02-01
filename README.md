# Obscure Bit

A daily publication featuring AI-generated sci-fi stories and curated links from the hidden corners of the web.

🌐 **[obscurebit.com](https://obscurebit.com)**

## What Is This?

Every day at 6 AM UTC, Obscure Bit automatically generates:

- **Daily Bits** — Short sci-fi stories exploring mysteries, speculative concepts, and the unknown
- **Obscure Links** — Curated discoveries from weird, wonderful, and forgotten corners of the web
- **Daily Editions** — Newsletter-style snapshots combining both

## How It Works

```
GitHub Actions (6 AM UTC)
    ↓
AI generates story + links (NVIDIA NIM)
    ↓
Site updates automatically (GitHub Pages)
    ↓
Optional: Publish to Substack (local only)
```

Content is fully automated. The site rebuilds and deploys itself daily.

## Quick Start

```bash
git clone https://github.com/obscurebit/b1ts.git
cd b1ts
pip install -r requirements.txt
mkdocs serve
```

## For Developers

See **[DEVELOPMENT.md](DEVELOPMENT.md)** for:
- Environment setup and secrets
- Script usage and workflows
- Substack publishing (local only due to Cloudflare)
- Project structure

See **[SYSTEM_DESIGN.md](SYSTEM_DESIGN.md)** for:
- Architecture diagrams
- Data flow and action flows
- Error handling

## Tech Stack

- **Site**: MkDocs Material
- **AI**: NVIDIA NIM API
- **Hosting**: GitHub Pages
- **CI/CD**: GitHub Actions

## License

MIT