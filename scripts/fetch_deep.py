"""
WMB 2M document supplemental crawler.
Follows Wikipedia links from existing documents to fill up to 2M tokens.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "documents")
TARGET_TOKENS = 2_000_000


def fetch_wikipedia_full(title):
    url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=extracts&explaintext=1&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WMB-Benchmark/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                return page.get("extract", "")
    except:
        return ""
    return ""


def fetch_links(title, limit=50):
    """Fetch internal links from a Wikipedia article"""
    url = (f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}"
           f"&prop=links&pllimit={limit}&plnamespace=0&format=json")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WMB-Benchmark/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            pages = data.get("query", {}).get("pages", {})
            links = []
            for page in pages.values():
                for link in page.get("links", []):
                    links.append(link["title"].replace(" ", "_"))
            return links
    except:
        return []


def estimate_tokens(text):
    return len(text) // 4


# Seed documents per category (key documents from fetch_docs.py)
SEEDS = {
    "science": ["Physics", "Chemistry", "Biology", "Astronomy", "Mathematics"],
    "history": ["World_War_II", "Roman_Empire", "Industrial_Revolution", "Cold_War", "Ancient_Greece"],
    "law": ["Law", "Constitutional_law", "Criminal_law", "Human_rights", "International_law"],
    "literature": ["Novel", "William_Shakespeare", "Leo_Tolstoy", "Poetry", "Literary_criticism"],
    "medicine": ["Medicine", "Human_body", "Cancer", "Immune_system", "Pharmacology"],
    "technology": ["Computer_science", "Artificial_intelligence", "Programming_language", "Internet", "Cloud_computing"],
    "psychology": ["Psychology", "Cognitive_psychology", "Memory", "Consciousness", "Personality_psychology"],
    "economics": ["Economics", "Macroeconomics", "Stock_market", "International_trade", "Game_theory"],
    "philosophy": ["Philosophy", "Ethics", "Epistemology", "Existentialism", "Logic"],
    "daily_life": ["Cooking", "Photography", "Travel", "Pet", "Meditation"],
}


def main():
    for cat, seeds in SEEDS.items():
        out_path = os.path.join(OUTPUT_DIR, f"{cat}.txt")

        existing = ""
        if os.path.exists(out_path):
            existing = open(out_path, encoding="utf-8").read()

        current_tokens = estimate_tokens(existing)

        if current_tokens >= TARGET_TOKENS * 0.9:
            print(f"[{cat}] Already at {current_tokens:,} tokens. Done.")
            continue

        print(f"\n[{cat}] {current_tokens:,}/{TARGET_TOKENS:,} tokens. Fetching more...")

        content = [existing]
        fetched_titles = set()

        # Extract titles from existing documents (deduplication)
        for line in existing.split('\n'):
            if line.startswith('=' * 10):
                continue
            if line.strip() and not line.startswith('='):
                pass

        # Follow links from seed documents
        for seed in seeds:
            if current_tokens >= TARGET_TOKENS:
                break

            links = fetch_links(seed, limit=50)
            print(f"  Seed '{seed}' → {len(links)} links")

            for link in links:
                if current_tokens >= TARGET_TOKENS:
                    break
                if link in fetched_titles:
                    continue

                fetched_titles.add(link)
                text = fetch_wikipedia_full(link)

                if not text or len(text) < 500:
                    continue

                tokens = estimate_tokens(text)
                section = f"\n{'='*60}\n{link.replace('_', ' ')}\n{'='*60}\n\n{text}\n"
                content.append(section)
                current_tokens += tokens

                if current_tokens % 100000 < tokens:
                    print(f"    {current_tokens:,}/{TARGET_TOKENS:,} tokens")

                time.sleep(0.3)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("".join(content))

        print(f"  [{cat}] Saved: {current_tokens:,} tokens")

    # Final report
    print("\n" + "=" * 50)
    print("Final Report:")
    total = 0
    for cat in SEEDS:
        path = os.path.join(OUTPUT_DIR, f"{cat}.txt")
        if os.path.exists(path):
            tokens = estimate_tokens(open(path, encoding="utf-8").read())
            total += tokens
            status = "✓" if tokens >= TARGET_TOKENS * 0.8 else "✗"
            print(f"  {status} {cat}: {tokens:,} tokens ({tokens*100//TARGET_TOKENS}%)")
    print(f"  Total: {total:,} tokens")


if __name__ == "__main__":
    main()
