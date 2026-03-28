"""
WMB 2M document collector.
Fetches Wikipedia articles per category to build ~2M tokens of content.
Cost: $0 (public API)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

# Fix Windows console encoding issues
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "documents")

# Wikipedia article list per category
CATEGORIES = {
    "science": [
        "Physics", "Quantum_mechanics", "General_relativity", "Thermodynamics",
        "Electromagnetism", "Classical_mechanics", "Optics", "Nuclear_physics",
        "Chemistry", "Organic_chemistry", "Inorganic_chemistry", "Biochemistry",
        "Periodic_table", "Chemical_bond", "Acid–base_reaction",
        "Biology", "Cell_(biology)", "DNA", "Evolution", "Genetics",
        "Photosynthesis", "Ecology", "Microbiology", "Neuroscience",
        "Astronomy", "Solar_System", "Black_hole", "Big_Bang",
        "Mathematics", "Calculus", "Linear_algebra", "Probability_theory",
        "Statistics", "Number_theory", "Topology",
    ],
    "history": [
        "World_War_I", "World_War_II", "Cold_War", "French_Revolution",
        "American_Revolution", "Industrial_Revolution", "Renaissance",
        "Ancient_Rome", "Ancient_Greece", "Ancient_Egypt", "Roman_Empire",
        "Byzantine_Empire", "Ottoman_Empire", "Mongol_Empire",
        "History_of_China", "History_of_Japan", "History_of_Korea",
        "Age_of_Enlightenment", "Scientific_Revolution",
        "Colonialism", "Imperialism", "Decolonization",
        "Civil_rights_movement", "Space_Race", "Fall_of_the_Berlin_Wall",
        "United_Nations", "European_Union", "NATO",
    ],
    "law": [
        "Law", "Constitutional_law", "Criminal_law", "Civil_law_(common_law)",
        "International_law", "Human_rights", "Contract", "Tort",
        "Property_law", "Patent", "Copyright", "Trademark",
        "Environmental_law", "Labor_law", "Tax_law", "Corporate_law",
        "Judicial_review", "Due_process", "Habeas_corpus",
        "Supreme_Court_of_the_United_States", "European_Court_of_Human_Rights",
        "Magna_Carta", "Universal_Declaration_of_Human_Rights",
        "Geneva_Conventions", "International_Criminal_Court",
    ],
    "literature": [
        "Novel", "Poetry", "Drama", "Short_story",
        "William_Shakespeare", "Leo_Tolstoy", "Fyodor_Dostoevsky",
        "Jane_Austen", "Charles_Dickens", "Mark_Twain",
        "Franz_Kafka", "Gabriel_García_Márquez", "Haruki_Murakami",
        "Homer", "Iliad", "Odyssey", "Divine_Comedy",
        "Don_Quixote", "War_and_Peace", "Crime_and_Punishment",
        "One_Hundred_Years_of_Solitude", "The_Great_Gatsby",
        "To_Kill_a_Mockingbird", "1984_(novel)", "Brave_New_World",
        "Literary_criticism", "Modernist_literature", "Postmodern_literature",
    ],
    "medicine": [
        "Medicine", "Human_body", "Cardiovascular_system", "Nervous_system",
        "Immune_system", "Respiratory_system", "Digestive_system",
        "Diabetes", "Cancer", "Hypertension", "Asthma", "Alzheimer%27s_disease",
        "Antibiotic", "Vaccine", "Pharmacology", "Surgery",
        "Mental_health", "Depression_(mood)", "Anxiety_disorder", "ADHD",
        "Public_health", "Epidemiology", "COVID-19_pandemic",
        "Nutrition", "Exercise_physiology", "Sleep",
    ],
    "technology": [
        "Computer_science", "Algorithm", "Data_structure", "Database",
        "Operating_system", "Computer_network", "Internet",
        "Artificial_intelligence", "Machine_learning", "Deep_learning",
        "Neural_network", "Natural_language_processing",
        "Programming_language", "Python_(programming_language)", "Rust_(programming_language)",
        "JavaScript", "SQL", "HTTP", "API",
        "Cloud_computing", "Distributed_computing", "Encryption",
        "Blockchain", "Quantum_computing", "Robotics",
        "Software_engineering", "Version_control", "DevOps",
    ],
    "psychology": [
        "Psychology", "Cognitive_psychology", "Behavioral_psychology",
        "Developmental_psychology", "Social_psychology", "Clinical_psychology",
        "Sigmund_Freud", "Carl_Jung", "B._F._Skinner", "Abraham_Maslow",
        "Consciousness", "Memory", "Emotion", "Motivation",
        "Personality_psychology", "Big_Five_personality_traits",
        "Intelligence", "IQ", "Emotional_intelligence",
        "Cognitive_bias", "Confirmation_bias", "Dunning–Kruger_effect",
        "Stanford_prison_experiment", "Milgram_experiment",
        "Psychotherapy", "Cognitive_behavioral_therapy",
    ],
    "economics": [
        "Economics", "Microeconomics", "Macroeconomics", "Behavioral_economics",
        "Supply_and_demand", "Market_(economics)", "Monopoly",
        "Inflation", "Gross_domestic_product", "Unemployment",
        "Central_bank", "Federal_Reserve", "Monetary_policy", "Fiscal_policy",
        "International_trade", "Globalization", "World_Trade_Organization",
        "Stock_market", "Bond_(finance)", "Cryptocurrency",
        "Adam_Smith", "John_Maynard_Keynes", "Milton_Friedman",
        "Game_theory", "Nash_equilibrium", "Pareto_efficiency",
    ],
    "philosophy": [
        "Philosophy", "Metaphysics", "Epistemology", "Ethics",
        "Logic", "Aesthetics", "Political_philosophy",
        "Socrates", "Plato", "Aristotle", "Immanuel_Kant",
        "Friedrich_Nietzsche", "Jean-Paul_Sartre", "Simone_de_Beauvoir",
        "Existentialism", "Utilitarianism", "Deontological_ethics",
        "Stoicism", "Buddhism", "Confucianism", "Taoism",
        "Philosophy_of_mind", "Free_will", "Consciousness",
        "Social_contract", "Justice", "Liberty",
    ],
    "daily_life": [
        "Cooking", "Recipe", "Nutrition", "Diet_(nutrition)",
        "Coffee", "Tea", "Bread", "Fermentation",
        "Housekeeping", "Interior_design", "Gardening",
        "Pet", "Cat", "Dog", "Aquarium",
        "Hobby", "Photography", "Cycling", "Hiking", "Yoga",
        "Travel", "Tourism", "Backpacking_(travel)",
        "Personal_finance", "Budgeting", "Minimalism",
        "Sleep_hygiene", "Meditation", "Mindfulness",
    ],
}

def fetch_wikipedia(title):
    """Fetch Wikipedia article text (free API)"""
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WMB-Benchmark/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("extract", "")
    except Exception as e:
        print(f"    ⚠ Failed: {title} ({e})")
        return ""


def fetch_wikipedia_full(title):
    """Fetch full Wikipedia article text"""
    url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=extracts&explaintext=1&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WMB-Benchmark/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                return page.get("extract", "")
    except Exception as e:
        print(f"    ⚠ Failed full: {title} ({e})")
        return ""
    return ""


def estimate_tokens(text):
    """Rough token count estimate"""
    return len(text) // 4  # ~4 chars/token for English


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    target_tokens = 2_000_000  # 2M tokens per category target

    for cat, titles in CATEGORIES.items():
        print(f"\n=== {cat} ===")
        out_path = os.path.join(OUTPUT_DIR, f"{cat}.txt")

        # Skip if already exists
        if os.path.exists(out_path):
            existing = open(out_path, encoding="utf-8").read()
            tokens = estimate_tokens(existing)
            if tokens >= target_tokens * 0.8:
                print(f"  Already exists: ~{tokens:,} tokens. Skipping.")
                continue

        content = []
        total_tokens = 0

        for title in titles:
            if total_tokens >= target_tokens:
                break

            print(f"  Fetching: {title}...")
            text = fetch_wikipedia_full(title)
            if not text:
                text = fetch_wikipedia(title)

            if text:
                section = f"\n{'='*60}\n{title.replace('_', ' ')}\n{'='*60}\n\n{text}\n"
                content.append(section)
                total_tokens += estimate_tokens(section)
                print(f"    +{estimate_tokens(section):,} tokens (total: {total_tokens:,})")

            time.sleep(0.5)  # Rate limit prevention

        # If under 2M, fetch more detailed versions (repeated fetch)
        if total_tokens < target_tokens:
            print(f"  Need more content: {total_tokens:,}/{target_tokens:,}")
            print(f"  (Tip: Add more Wikipedia titles to reach 2M)")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("".join(content))

        print(f"  Saved: {out_path} (~{total_tokens:,} tokens)")

    print("\n✅ Document collection complete.")
    print(f"   Output: {OUTPUT_DIR}/")

    # Total token count report
    total = 0
    for cat in CATEGORIES:
        path = os.path.join(OUTPUT_DIR, f"{cat}.txt")
        if os.path.exists(path):
            tokens = estimate_tokens(open(path, encoding="utf-8").read())
            total += tokens
            print(f"   {cat}: ~{tokens:,} tokens")
    print(f"   Total: ~{total:,} tokens")


if __name__ == "__main__":
    main()
