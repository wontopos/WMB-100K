"""
WMB-100K V2.0 — Complete Question Generator
Score: Part A(S1 1000) + Part B(S1 1000) + S2-S7(analysis) + FM(400 penalty)
"""
import json, os, time, sys, re
sys.stdout.reconfigure(line_buffering=True)

try:
    import anthropic
except ImportError:
    os.system(f"{sys.executable} -m pip install anthropic")
    import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
BASE = os.path.join(os.path.dirname(__file__), '..')
DATASETS = os.path.join(BASE, 'datasets')
DOCUMENTS = os.path.join(BASE, 'documents')

CATEGORIES = ['daily_life','relationships','work_career','health_fitness',
              'travel_places','media_taste','finance_goals','education_skills',
              'pets_hobbies','beliefs_values']

DOC_DOMAINS = ['daily_life','economics','history','law','literature',
               'medicine','philosophy','psychology','science','technology']

def parse_json(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    try:
        return json.loads(text)
    except:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []

def call_haiku(prompt, max_tokens=4000, retries=3):
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            items = parse_json(resp.content[0].text)
            if items and isinstance(items, list):
                return items
        except Exception as e:
            print(f"    Retry {attempt+1}: {e}")
        time.sleep(3)
    return []

def validate(item, qid, category, qtype):
    text = item.get('question', item.get('text', '')).strip()
    gold = item.get('gold_answer', '').strip()
    req = item.get('required_memories', [])

    if not text: return None
    if qtype != 'FalseMemory' and not gold: return None
    if re.search('[가-힣]', text + gold): return None

    if qtype == 'FalseMemory':
        gold = gold or "This information was never mentioned."
        req = []
    elif not req:
        req = [gold[:100]]

    return {
        "id": qid, "category": category, "qtype": qtype,
        "text": text, "gold_answer": gold,
        "required_memories": req,
        "gold_turn_ids": item.get('gold_turn_ids', []),
        "points": 0.0 if qtype == 'FalseMemory' else 0.1,
        "false_penalty": 0.25 if qtype == 'FalseMemory' else 0.0
    }

# Load facts
facts_by_cat = {}
for fname in sorted(os.listdir(DATASETS)):
    if not fname.endswith('.jsonl'): continue
    cat = fname.replace('.jsonl', '')
    if cat not in CATEGORIES: continue
    facts_by_cat[cat] = []
    with open(os.path.join(DATASETS, fname), encoding='utf-8') as f:
        for line in f:
            t = json.loads(line)
            if t.get('embedded_facts') and len(t['embedded_facts']) > 0:
                facts_by_cat[cat].append({
                    'turn_id': t['turn_id'],
                    'text': t['text'][:200],
                    'facts': t['embedded_facts']
                })

all_questions = []

print("=" * 60)
print("WMB-100K V2.0 Complete Generator")
print("=" * 60)

# ============================================================
# PART B S1: 1000 questions (100 per category)
# ============================================================
print("\n=== PART B S1 (1000 questions) ===")
for cat in CATEGORIES:
    facts = facts_by_cat.get(cat, [])
    target = 100
    generated = 0

    for batch in range(5):  # 5 batches of 20
        start = batch * 8
        end = min(start + 8, len(facts))
        if start >= len(facts): start = 0; end = 8

        fact_texts = "\n".join([f"turn_{f['turn_id']}: {f['text']}" for f in facts[start:end]])

        prompt = f"""Generate 20 situational questions for AI memory benchmark.
Category: {cat}

User's conversation facts:
{fact_texts}

Each question is a REAL SITUATION where someone needs to use the user's stored memories.
NOT "what does the user like?" but "Given this situation, what should we consider about the user?"

RULES:
1. Each question needs exactly 1 memory to answer
2. "gold_answer" MUST be 1-2 sentences (NEVER empty)
3. "required_memories" MUST list the specific fact needed
4. "gold_turn_ids" MUST reference turn IDs from above
5. ALL English
6. Make questions PRACTICAL and SITUATIONAL

Return JSON array:
[{{"question":"...","gold_answer":"...","required_memories":["..."],"gold_turn_ids":[123]}}]"""

        items = call_haiku(prompt, max_tokens=3000)
        for item in items:
            if generated >= target: break
            q = validate(item, f"{cat}.S1.{generated+1:03d}", cat, "S1Situational")
            if q:
                all_questions.append(q)
                generated += 1
        time.sleep(1)

    print(f"  {cat}: {generated} S1 questions")

# ============================================================
# PART A S1: 1000 questions (100 per domain)
# ============================================================
print("\n=== PART A S1 (1000 questions) ===")
for domain in DOC_DOMAINS:
    with open(os.path.join(DOCUMENTS, f'{domain}.txt'), encoding='utf-8') as f:
        doc_text = f.read()
    words = doc_text.split()
    target = 100
    generated = 0

    for batch in range(5):  # 5 batches of 20
        start = batch * 1000
        chunk = ' '.join(words[start:start+1000])

        prompt = f"""Generate 20 situational questions based on this {domain.replace('_',' ')} document.

Document excerpt:
{chunk}

Each question is a REAL SITUATION where someone needs knowledge from this document.
NOT "what does the document say?" but "If someone needed to deal with X, what should they know?"

RULES:
1. "gold_answer" MUST be 1-2 SHORT sentences with SPECIFIC facts from the document (NEVER empty)
2. "required_memories" MUST list the specific facts needed
3. ALL English
4. Make questions PRACTICAL

Return JSON array:
[{{"question":"...","gold_answer":"The document states that...","required_memories":["specific fact"]}}]"""

        items = call_haiku(prompt, max_tokens=3000)
        for item in items:
            if generated >= target: break
            q = validate(item, f"{domain}.DOC.S1.{generated+1:03d}", domain, "S1Situational")
            if q:
                all_questions.append(q)
                generated += 1
        time.sleep(1)

    print(f"  {domain}: {generated} S1 questions")

# ============================================================
# S2-S7: ~100 each (analysis only)
# ============================================================
print("\n=== S2-S7 (analysis questions) ===")
for cat in CATEGORIES:
    facts = facts_by_cat.get(cat, [])
    fact_texts = "\n".join([f"turn_{f['turn_id']}: {f['text']}" for f in facts[:30]])

    prompt = f"""Generate benchmark questions for category: {cat}

Facts:
{fact_texts}

Generate EXACTLY:
- 10 S2MultiMemory (need 2-3 memories combined)
- 5 S4Temporal (track time changes)
- 5 S5Adversarial (wrong premise, must retrieve correct memory)
- 3 S6Contradiction (contradictory info, retrieve both)
- 2 S7ReasoningChain (need 3+ memories in chain)

RULES:
1. "gold_answer" MUST be filled (1-2 sentences, NEVER empty)
2. "required_memories" MUST list specific facts
3. "qtype" MUST be one of: S2MultiMemory, S4Temporal, S5Adversarial, S6Contradiction, S7ReasoningChain
4. ALL English

Return JSON array:
[{{"qtype":"S2MultiMemory","question":"...","gold_answer":"...","required_memories":["...","..."],"gold_turn_ids":[1,2]}}]"""

    items = call_haiku(prompt, max_tokens=4000)

    type_map = {'S2':'S2MultiMemory','S4':'S4Temporal','S5':'S5Adversarial',
                'S6':'S6Contradiction','S7':'S7ReasoningChain'}

    counts = {}
    for item in items:
        qt = item.get('qtype', 'S2MultiMemory')
        qt = type_map.get(qt, qt)
        if qt not in type_map.values(): qt = 'S2MultiMemory'
        counts[qt] = counts.get(qt, 0) + 1
        q = validate(item, f"{cat}.{qt}.{counts[qt]:03d}", cat, qt)
        if q:
            all_questions.append(q)

    print(f"  {cat}: {sum(counts.values())} questions ({counts})")
    time.sleep(1)

# S3 Cross-category
print("\n--- S3 Cross-category ---")
import itertools
pairs = list(itertools.combinations(CATEGORIES, 2))
for idx, (c1, c2) in enumerate(pairs):
    f1 = facts_by_cat.get(c1, [])[:3]
    f2 = facts_by_cat.get(c2, [])[:3]
    if not f1 or not f2: continue

    f1t = "\n".join([f"[{c1}] turn_{f['turn_id']}: {f['text']}" for f in f1])
    f2t = "\n".join([f"[{c2}] turn_{f['turn_id']}: {f['text']}" for f in f2])

    prompt = f"""Generate 2 cross-category questions needing memories from BOTH categories.

{c1} facts:
{f1t}

{c2} facts:
{f2t}

RULES: gold_answer MUST be filled. required_memories MUST list facts from BOTH categories.

Return JSON array:
[{{"qtype":"S3CrossCategory","question":"...","gold_answer":"...","required_memories":["from {c1}: ...","from {c2}: ..."]}}]"""

    items = call_haiku(prompt, max_tokens=1000)
    for i, item in enumerate(items):
        q = validate(item, f"{c1}_{c2}.S3.{i+1:03d}", c1, "S3CrossCategory")
        if q:
            all_questions.append(q)

    if (idx+1) % 15 == 0:
        print(f"  S3: {idx+1}/{len(pairs)} pairs")
    time.sleep(0.5)

print(f"  S3: {len(pairs)}/{len(pairs)} done")

# ============================================================
# FM: 400 questions
# ============================================================
print("\n=== FM (400 questions) ===")
# Part B FM: 200
for cat in CATEGORIES:
    facts = facts_by_cat.get(cat, [])[:10]
    fact_texts = "\n".join([f"- {f['text'][:100]}" for f in facts])

    prompt = f"""Generate 20 false memory probe questions for category: {cat}

These are the REAL facts about the user:
{fact_texts}

Generate 20 questions about things NEVER mentioned. The questions should sound plausible but the information does NOT exist.

RULES:
1. Questions must ask about specific details that were NEVER mentioned
2. gold_answer = "This was never mentioned."
3. ALL English

Return JSON array:
[{{"question":"What is the user's blood type?","gold_answer":"This was never mentioned."}}]"""

    items = call_haiku(prompt, max_tokens=2000)
    for i, item in enumerate(items):
        q = validate(item, f"{cat}.FM.{i+1:03d}", cat, "FalseMemory")
        if q:
            all_questions.append(q)
    print(f"  {cat}: {len(items)} FM")
    time.sleep(1)

# Part A FM: 200
for domain in DOC_DOMAINS:
    for i in range(20):
        all_questions.append({
            "id": f"{domain}.DOC.FM.{i+1:03d}",
            "category": domain, "qtype": "FalseMemory",
            "text": f"According to the {domain.replace('_',' ')} documents, what specific details are provided about [nonexistent_topic_{i+1}]?",
            "gold_answer": "This information is not in the documents.",
            "required_memories": [], "gold_turn_ids": [],
            "points": 0.0, "false_penalty": 0.25
        })
    print(f"  {domain}: 20 FM (doc)")

# ============================================================
# FINAL
# ============================================================
# Deduplicate IDs
seen = set()
final = []
for q in all_questions:
    while q['id'] in seen:
        q['id'] += '_2'
    seen.add(q['id'])
    final.append(q)

# Remove empty gold_answer (non-FM)
clean = [q for q in final if q['qtype'] == 'FalseMemory' or q.get('gold_answer','').strip()]
removed = len(final) - len(clean)

out = os.path.join(DATASETS, 'all_questions.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(clean, f, indent=2, ensure_ascii=False)

# Summary
by_type = {}
pa = sum(1 for q in clean if '.DOC.' in q['id'])
pb = len(clean) - pa
for q in clean:
    by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1

pa_s1 = sum(1 for q in clean if '.DOC.' in q['id'] and q['qtype'] == 'S1Situational')
pb_s1 = sum(1 for q in clean if '.DOC.' not in q['id'] and q['qtype'] == 'S1Situational')
fm = by_type.get('FalseMemory', 0)

print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
print(f"Total: {len(clean)} (removed {removed} empty)")
print(f"Part A: {pa} (S1: {pa_s1})")
print(f"Part B: {pb} (S1: {pb_s1})")
print(f"\nBy type:")
for t, c in sorted(by_type.items()):
    print(f"  {t}: {c}")
print(f"\nScore structure:")
print(f"  Part A: {pa_s1} S1 x 0.1 = {pa_s1*0.1:.1f} (cap 100)")
print(f"  Part B: {pb_s1} S1 x 0.1 = {pb_s1*0.1:.1f} (cap 100)")
print(f"  Score = A/2 + B/2 - FM")
print(f"  FM: {fm} x -0.25 = -{fm*0.25:.1f} max penalty")
print(f"\nEmpty gold_answer: {removed}")
print("ALL CLEAR" if removed == 0 else f"WARNING: removed {removed}")
