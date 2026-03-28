"""Generate S6 (Contradiction) and S7 (Reasoning Chain) questions for WMB-100K V2."""
import json, os, time, sys
sys.stdout.reconfigure(line_buffering=True)

try:
    import anthropic
except ImportError:
    os.system(f"{sys.executable} -m pip install anthropic")
    import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
datasets = os.path.join(os.path.dirname(__file__), '..', 'datasets')

# Load existing questions
with open(os.path.join(datasets, 'all_questions.json'), encoding='utf-8') as f:
    all_qs = json.load(f)

# Load facts from JSONL
facts_by_cat = {}
for fname in sorted(os.listdir(datasets)):
    if not fname.endswith('.jsonl'): continue
    cat = fname.replace('.jsonl','')
    facts_by_cat[cat] = []
    with open(os.path.join(datasets, fname), encoding='utf-8') as f:
        for line in f:
            t = json.loads(line)
            if t.get('embedded_facts'):
                facts_by_cat[cat].append({
                    'turn_id': t['turn_id'],
                    'text': t['text'],
                    'facts': t['embedded_facts'],
                    'speaker': t['speaker']
                })

categories = sorted(facts_by_cat.keys())
new_qs = []

# === S6: Contradiction Detection ===
print("=== Generating S6 (Contradiction) ===")
for cat in categories:
    facts = facts_by_cat[cat]
    if len(facts) < 10: continue
    
    # Build fact text list for Haiku
    fact_texts = []
    for f in facts[:50]:  # limit
        fact_texts.append(f"turn_{f['turn_id']}: {f['text'][:150]}")
    
    prompt = f"""You are generating contradiction detection questions for an AI memory benchmark.

Category: {cat}
Here are real conversation turns containing facts:

{chr(10).join(fact_texts[:30])}

Generate 10 S6 (Contradiction) questions. Each question should:
1. Reference a topic where the user might have said contradictory things over time
2. Ask which is the current/true state
3. The memory system needs to return BOTH turns so the LLM can decide

Format as JSON array:
[{{
  "question": "The user mentioned both X and Y about topic. What's the current situation?",
  "gold_answer": "Brief description of what memories should be retrieved and what the right answer direction is",
  "required_memories": ["memory 1 description", "memory 2 description"],
  "gold_turn_ids": [turn_id1, turn_id2]
}}]

Rules:
- All questions in English
- Questions must be about realistic contradictions (opinions change, situations change)
- gold_turn_ids should reference actual turn IDs from the data above
- Return ONLY the JSON array, no markdown"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        if text.startswith('```'): text = text.split('\n',1)[1].rsplit('```',1)[0]
        items = json.loads(text)
        
        for i, item in enumerate(items):
            q = {
                "id": f"{cat}.S6.{i+1:03d}",
                "category": cat,
                "qtype": "S6Contradiction",
                "text": item["question"],
                "gold_answer": item["gold_answer"],
                "required_memories": item.get("required_memories", []),
                "gold_turn_ids": item.get("gold_turn_ids", []),
                "points": 0.1,
                "false_penalty": 0.0
            }
            new_qs.append(q)
        print(f"  {cat}: {len(items)} S6 questions")
    except Exception as e:
        print(f"  {cat}: ERROR - {e}")
    time.sleep(1)

print(f"S6 total: {len([q for q in new_qs if q['qtype'] == 'S6Contradiction'])}")

# === S7: Reasoning Chain ===
print("\n=== Generating S7 (Reasoning Chain) ===")
for cat in categories:
    facts = facts_by_cat[cat]
    if len(facts) < 10: continue
    
    fact_texts = []
    for f in facts[:50]:
        fact_texts.append(f"turn_{f['turn_id']}: {f['text'][:150]}")
    
    prompt = f"""You are generating reasoning chain questions for an AI memory benchmark.

Category: {cat}
Here are real conversation turns containing facts:

{chr(10).join(fact_texts[:30])}

Generate 10 S7 (Reasoning Chain) questions. Each question should:
1. Require 3+ different memories to answer properly
2. The answer only makes sense when ALL memories are combined
3. Each memory alone is insufficient

Format as JSON array:
[{{
  "question": "Given everything about the user's situation, what would you recommend for X?",
  "gold_answer": "The answer requires combining memory A + memory B + memory C to conclude...",
  "required_memories": ["memory 1", "memory 2", "memory 3"],
  "gold_turn_ids": [turn_id1, turn_id2, turn_id3]
}}]

Rules:
- All questions in English
- Questions must require genuine multi-step reasoning
- No question answerable with just 1-2 memories
- gold_turn_ids should reference actual turn IDs from the data above
- Return ONLY the JSON array, no markdown"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        if text.startswith('```'): text = text.split('\n',1)[1].rsplit('```',1)[0]
        items = json.loads(text)
        
        for i, item in enumerate(items):
            q = {
                "id": f"{cat}.S7.{i+1:03d}",
                "category": cat,
                "qtype": "S7ReasoningChain",
                "text": item["question"],
                "gold_answer": item["gold_answer"],
                "required_memories": item.get("required_memories", []),
                "gold_turn_ids": item.get("gold_turn_ids", []),
                "points": 0.1,
                "false_penalty": 0.0
            }
            new_qs.append(q)
        print(f"  {cat}: {len(items)} S7 questions")
    except Exception as e:
        print(f"  {cat}: ERROR - {e}")
    time.sleep(1)

print(f"S7 total: {len([q for q in new_qs if q['qtype'] == 'S7ReasoningChain'])}")

# Merge with existing
all_qs.extend(new_qs)
with open(os.path.join(datasets, 'all_questions.json'), 'w', encoding='utf-8') as f:
    json.dump(all_qs, f, indent=2, ensure_ascii=False)

# Summary
by_type = {}
for q in all_qs:
    t = q['qtype']
    by_type[t] = by_type.get(t, 0) + 1

print(f"\n=== Final Summary ===")
print(f"Total: {len(all_qs)} questions")
for t, c in sorted(by_type.items()):
    print(f"  {t}: {c}")
