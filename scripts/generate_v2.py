"""
WMB-100K V2.0 Question Generator

Generates situational questions using Claude Haiku API.
S1: Single situational (1 fact, no keywords)
S2: Multi-memory (2-3 facts, same category)
S3: Cross-category (2-4 facts, different categories)
S4: Temporal situation (update chains)
S5: Adversarial (keyword traps)
FM: False memory (unchanged)
"""

import json
import os
import re
import sys
import time
import urllib.request
import random

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')

CATEGORIES_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "categories")
DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def parse_facts_from_rs(filepath):
    """Parse Rust fact definitions into Python dicts."""
    with open(filepath, encoding='utf-8') as f:
        content = f.read()

    facts = []
    # Match: super::fact("id", "category", "content", "natural_text", turn, importance, &["kw1", "kw2"])
    pattern = r'super::fact\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*(\d+),\s*([\d.]+),\s*&\[([^\]]*)\]\)'
    for m in re.finditer(pattern, content):
        keywords = [k.strip().strip('"') for k in m.group(7).split(',') if k.strip()]
        facts.append({
            "id": m.group(1),
            "category": m.group(2),
            "content": m.group(3),
            "natural_text": m.group(4),
            "turn_id": int(m.group(5)),
            "importance": float(m.group(6)),
            "keywords": keywords
        })
    return facts


def load_all_facts():
    """Load facts from all category files."""
    all_facts = {}
    categories = [
        "daily_life", "relationships", "work_career", "health_fitness",
        "travel_places", "media_taste", "finance_goals", "education_skills",
        "pets_hobbies", "beliefs_values"
    ]
    for cat in categories:
        filepath = os.path.join(CATEGORIES_DIR, f"{cat}.rs")
        if os.path.exists(filepath):
            facts = parse_facts_from_rs(filepath)
            all_facts[cat] = facts
            print(f"  {cat}: {len(facts)} facts")
    return all_facts


def call_haiku(prompt, max_retries=3):
    """Call Claude Haiku API."""
    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}]
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    )

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                text = result["content"][0]["text"]
                # Try to extract JSON from response
                json_match = re.search(r'\{[\s\S]*\}', text)
                if json_match:
                    return json.loads(json_match.group())
                return None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"    Haiku error: {e}")
                return None


def generate_s1(facts, category):
    """S1: One fact, situational question without keywords."""
    questions = []
    for i, fact in enumerate(facts):
        kw_list = ", ".join(fact["keywords"])
        prompt = f"""Generate a situational question about a user. Someone who knows this fact would respond differently than someone who doesn't.

FACT: {fact["content"]}
KEYWORDS TO AVOID in question: {kw_list}

The question should describe a real situation (invitation, decision, recommendation) where this fact matters.
Do NOT mention the fact directly. Do NOT use any of the keywords.

Output ONLY valid JSON:
{{"text": "the situational question", "signal": "what the correct response should show awareness of", "context_description": "full description of what must be in the returned memories"}}"""

        result = call_haiku(prompt)
        if result:
            q = {
                "id": f"{category}.S1.{i+1:03d}",
                "category": category,
                "qtype": "S1Situational",
                "text": result.get("text", ""),
                "required_memory_ids": [fact["id"]],
                "context_description": result.get("context_description", result.get("signal", "")),
                "judge_criteria": [
                    {"fact_id": fact["id"], "signal": result.get("signal", ""), "required": True}
                ],
                "min_required_signals": 1
            }
            if q["text"]:
                questions.append(q)

        if (i + 1) % 10 == 0:
            print(f"    S1: {i+1}/{len(facts)}")

    return questions


def generate_s2(facts, category):
    """S2: 2-3 facts from same category, multi-memory situation."""
    questions = []
    # Group facts into clusters of 2-3
    random.seed(42 + hash(category))
    shuffled = facts.copy()
    random.shuffle(shuffled)

    groups = []
    for i in range(0, len(shuffled) - 1, 2):
        group = shuffled[i:i+2] if i + 2 <= len(shuffled) else shuffled[i:]
        if len(group) >= 2:
            groups.append(group)

    for gi, group in enumerate(groups[:40]):  # max 40 per category -> 80 total with idx
        fact_texts = "\n".join([f"- [{f['id']}] {f['content']}" for f in group])
        all_kws = set()
        for f in group:
            all_kws.update(f["keywords"])

        prompt = f"""Generate a situational question that requires awareness of ALL these facts:

{fact_texts}

KEYWORDS TO AVOID: {", ".join(all_kws)}

The question should describe a realistic scenario where someone needs to consider multiple pieces of information about the user simultaneously.

Output ONLY valid JSON:
{{"text": "the question", "context_description": "what the response must show", "criteria": [{{"fact_id": "...", "signal": "...", "required": true}}, ...]}}"""

        result = call_haiku(prompt)
        if result and result.get("text"):
            criteria = result.get("criteria", [])
            if not criteria:
                criteria = [{"fact_id": f["id"], "signal": f["content"][:50], "required": True} for f in group]

            q = {
                "id": f"{category}.S2.{gi+1:03d}",
                "category": category,
                "qtype": "S2MultiMemory",
                "text": result["text"],
                "required_memory_ids": [f["id"] for f in group],
                "context_description": result.get("context_description", ""),
                "judge_criteria": criteria,
                "min_required_signals": 1
            }
            questions.append(q)

        if (gi + 1) % 10 == 0:
            print(f"    S2: {gi+1}/{min(len(groups), 40)}")

    return questions


def generate_s3(all_facts):
    """S3: Cross-category questions (2 facts from different categories)."""
    questions = []
    categories = list(all_facts.keys())

    # Create category pairings
    pairings = []
    for i in range(len(categories)):
        for j in range(i + 1, len(categories)):
            pairings.append((categories[i], categories[j]))

    random.seed(99)
    for pi, (cat1, cat2) in enumerate(pairings):
        facts1 = all_facts[cat1]
        facts2 = all_facts[cat2]

        # Pick 2 random facts per pairing, generate ~13 questions per pairing
        for qi in range(13):
            f1 = random.choice(facts1)
            f2 = random.choice(facts2)

            prompt = f"""Generate a situational question that requires knowing BOTH of these facts about a user:

Fact 1 [{f1["id"]}]: {f1["content"]}
Fact 2 [{f2["id"]}]: {f2["content"]}

The question should describe a situation where both pieces of information matter together.
Do NOT use keywords from either fact directly.

Output ONLY valid JSON:
{{"text": "the question", "context_description": "what the response must show", "signal1": "what fact 1 awareness looks like", "signal2": "what fact 2 awareness looks like"}}"""

            result = call_haiku(prompt)
            if result and result.get("text"):
                q = {
                    "id": f"{cat1}_{cat2}.S3.{pi*13+qi+1:03d}",
                    "category": f"{cat1}+{cat2}",
                    "qtype": "S3CrossCategory",
                    "text": result["text"],
                    "required_memory_ids": [f1["id"], f2["id"]],
                    "context_description": result.get("context_description", ""),
                    "judge_criteria": [
                        {"fact_id": f1["id"], "signal": result.get("signal1", ""), "required": True},
                        {"fact_id": f2["id"], "signal": result.get("signal2", ""), "required": False}
                    ],
                    "min_required_signals": 1
                }
                questions.append(q)

        if (pi + 1) % 5 == 0:
            print(f"    S3: {pi+1}/{len(pairings)} pairings")

    return questions


def generate_s4(facts, category):
    """S4: Temporal questions using update chains."""
    questions = []

    # Find facts that have similar topics (potential update chains)
    # Group by overlapping keywords
    for i, fact in enumerate(facts):
        if fact["importance"] < 0.7:
            continue  # Only high-importance facts likely have updates

        prompt = f"""A user previously stated: "{fact['content']}"
This fact might have changed over time. Generate a situational question where knowing the CURRENT state matters.
If someone gives advice based on OLD information, it would be wrong.

Output ONLY valid JSON:
{{"text": "the question", "context_description": "why current state matters", "signal": "what correct response shows"}}"""

        result = call_haiku(prompt)
        if result and result.get("text"):
            q = {
                "id": f"{category}.S4.{len(questions)+1:03d}",
                "category": category,
                "qtype": "S4TemporalSituation",
                "text": result["text"],
                "required_memory_ids": [fact["id"]],
                "context_description": result.get("context_description", ""),
                "judge_criteria": [
                    {"fact_id": fact["id"], "signal": result.get("signal", ""), "required": True}
                ],
                "min_required_signals": 1
            }
            questions.append(q)

        if len(questions) >= 40:
            break

    print(f"    S4: {len(questions)} generated")
    return questions


def generate_s5(facts, category):
    """S5: Adversarial questions with keyword traps."""
    questions = []

    for i in range(min(20, len(facts) - 1)):
        target = facts[i]
        distractor = facts[(i + 5) % len(facts)]

        prompt = f"""Create an ADVERSARIAL question that tests whether a memory system can avoid keyword traps.

TARGET FACT (should be retrieved): [{target["id"]}] {target["content"]}
DISTRACTOR FACT (shares a keyword but is NOT relevant): [{distractor["id"]}] {distractor["content"]}

Write a question where a naive keyword search would return the DISTRACTOR, but the correct response needs the TARGET.

Output ONLY valid JSON:
{{"text": "the question", "context_description": "why target is right and distractor is wrong", "target_signal": "what correct retrieval shows", "distractor_signal": "what wrong retrieval looks like"}}"""

        result = call_haiku(prompt)
        if result and result.get("text"):
            q = {
                "id": f"{category}.S5.{len(questions)+1:03d}",
                "category": category,
                "qtype": "S5Adversarial",
                "text": result["text"],
                "required_memory_ids": [target["id"]],
                "context_description": result.get("context_description", ""),
                "judge_criteria": [
                    {"fact_id": target["id"], "signal": result.get("target_signal", ""), "required": True}
                ],
                "min_required_signals": 1
            }
            questions.append(q)

    print(f"    S5: {len(questions)} generated (REVIEW NEEDED)")
    return questions


def generate_fm(category):
    """FM: False memory questions (things never mentioned)."""
    fm_topics = [
        "blood type", "shoe size", "favorite color of socks",
        "middle name", "zodiac sign preferences", "favorite number",
        "childhood pet's breed", "high school GPA", "driver's license number",
        "preferred airline", "shoe brand preference", "tattoo locations",
        "swimming ability", "musical instrument played as child",
        "college roommate's name", "birth hospital", "first car model",
        "grandmother's maiden name", "favorite ice cream flavor", "hat size"
    ]

    questions = []
    for i, topic in enumerate(fm_topics):
        q = {
            "id": f"{category}.FM.{i+1:03d}",
            "category": category,
            "qtype": "FalseMemory",
            "text": f"What is the user's {topic}?",
            "required_memory_ids": [],
            "context_description": f"This was NEVER mentioned. System must return NO memories.",
            "judge_criteria": [],
            "min_required_signals": 0
        }
        questions.append(q)
    return questions


def main():
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY required")
        sys.exit(1)

    print("=== WMB-100K V2.0 Question Generator ===\n")

    # Load all facts
    print("Loading facts...")
    all_facts = load_all_facts()
    total_facts = sum(len(v) for v in all_facts.values())
    print(f"Total: {total_facts} facts across {len(all_facts)} categories\n")

    all_questions = []

    # Generate per category: S1, S2, S4, S5, FM
    for cat, facts in all_facts.items():
        print(f"\n--- {cat} ({len(facts)} facts) ---")

        print("  Generating S1 (situational)...")
        s1 = generate_s1(facts, cat)
        all_questions.extend(s1)
        print(f"  S1: {len(s1)} questions")

        print("  Generating S2 (multi-memory)...")
        s2 = generate_s2(facts, cat)
        all_questions.extend(s2)
        print(f"  S2: {len(s2)} questions")

        print("  Generating S4 (temporal)...")
        s4 = generate_s4(facts, cat)
        all_questions.extend(s4)
        print(f"  S4: {len(s4)} questions")

        print("  Generating S5 (adversarial)...")
        s5 = generate_s5(facts, cat)
        all_questions.extend(s5)
        print(f"  S5: {len(s5)} questions")

        print("  Generating FM (false memory)...")
        fm = generate_fm(cat)
        all_questions.extend(fm)
        print(f"  FM: {len(fm)} questions")

    # Generate S3 (cross-category) separately
    print("\n--- Cross-category (S3) ---")
    s3 = generate_s3(all_facts)
    all_questions.extend(s3)
    print(f"  S3: {len(s3)} questions")

    # Save
    output_path = os.path.join(DATASETS_DIR, "all_questions.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_questions, f, indent=2, ensure_ascii=False)

    # Summary
    from collections import Counter
    type_counts = Counter(q["qtype"] for q in all_questions)
    print(f"\n=== Summary ===")
    print(f"Total: {len(all_questions)} questions")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
