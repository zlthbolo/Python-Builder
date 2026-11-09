# Campus Community Finder

Arabic public web search for student communities on Telegram, WhatsApp, Discord, Reddit, Facebook, Instagram, X, Threads, Snapchat, TikTok, YouTube and forums. Search results are only indexed public candidates, not verified membership, engagement, or private chat content.

Run: `pip install -r requirements.txt && python app.py`. On Render, deploy the Dockerfile at the repository root using branch `campus-community-finder-deploy` and free plan. Queries use DDGS, and upstream throttling may produce partial results. Deep mode generates 28 search requests; this is not exhaustive search over millions of private messages.
