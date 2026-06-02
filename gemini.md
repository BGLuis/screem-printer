# Gemini Context & Contribution

This project was built from scratch through a pair-programming session with **Antigravity**, an advanced agentic coding assistant powered by Gemini 3.1 Pro.

## Project Evolution

1. **Initial Concept**: The user requested a Python script using Playwright to crawl a website and take screenshots in different resolutions to verify responsiveness.
2. **Configuration Extraction**: Hardcoded resolutions were extracted into a flexible `config.json` file.
3. **CLI & UX**: An interactive mode and CLI arguments were implemented using `argparse`.
4. **Expanded Scope**: The config was enriched with 14 different viewport sizes (covering various mobile, tablet, and desktop devices).
5. **Rate Limiting**: Configurable delays were added to prevent server overloading and Cloudflare blocking.
6. **Parallelism**: The entire crawling logic was refactored into an asynchronous Producer-Consumer pattern (`asyncio.Queue`) to allow concurrent multi-page processing.
7. **SPA Fixes**: Hash routing rules were updated to properly crawl Single Page Applications (React, Vue, Angular).
8. **Organized Output**: The directory structure was inverted so each page gets its own folder, making analysis much easier.
9. **Backups**: Auto-backup logic was added using timestamped folders to prevent data loss across executions.

*Generated entirely via natural language prompts.*
