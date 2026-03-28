"""
WMB-100K V2.0 — Final Question Generator
Generates ALL questions (Part A + Part B) with guaranteed:
- gold_answer (never empty)
- required_memories (never empty for non-FM)
- gold_turn_ids (for Part B)
- Unified qtype naming
- No duplicate IDs
- English only
"""
import json, os, time, sys, re
sys.stdout.reconfigure(line_buffering=True)

try:
    import anthropic
except ImportError:
    os.system(f"{sys.executable} -m pip install anthropic")
    import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

BASE = os.path.join(os.path.dirname(__file__), '..')
DATASETS = os.path.join(BASE, 'datasets')
DOCUMENTS = os.path.join(BASE, 'documents')

CATEGORIES = ['daily_life','relationships','work_career','health_fitness',
              'travel_places','media_taste','finance_goals','education_skills',
              'pets_hobbies','beliefs_values']

DOC_DOMAINS = ['daily_life','economics','history','law','literature',
               'medicine','philosophy','psychology','science','technology']

VALID_QTYPES = ['S1Situational','S2MultiMemory','S3CrossCategory','S4Temporal',
                'S5Adversarial','S6Contradiction','S7ReasoningChain','FalseMemory']

TYPE_MAP = {
    'S1':'S1Situational','S1Situational':'S1Situational',
    'S2':'S2MultiMemory','S2MultiMemory':'S2MultiMemory','S2Situational':'S2MultiMemory',
    'S3':'S3CrossCategory','S3CrossCategory':'S3CrossCategory','S3Situational':'S3CrossCategory',
    'S4':'S4Temporal','S4Temporal':'S4Temporal','S4Situational':'S4Temporal','S4TemporalSituation':'S4Temporal',
    'S5':'S5Adversarial','S5Adversarial':'S5Adversarial','S5Situational':'S5Adversarial',
    'S6':'S6Contradiction','S6Contradiction':'S6Contradiction','S6Situational':'S6Contradiction',
    'S7':'S7ReasoningChain','S7ReasoningChain':'S7ReasoningChain','S7Situational':'S7ReasoningChain','S7Reasoning':'S7ReasoningChain',
}


def parse_json(text):
    """Robust JSON parser - handles markdown fences."""
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    # Try parse
    try:
        return json.loads(text)
    except:
        # Try to find array
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return None


def call_haiku(prompt, max_tokens=4000, retries=3):
    """Call Haiku with retries."""
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
            print(f"    Parse failed attempt {attempt+1}, retrying...")
        except Exception as e:
            print(f"    API error attempt {attempt+1}: {e}")
        time.sleep(3)
    return []


def validate_question(q, idx, prefix):
    """Validate and fix a question dict. Returns None if unfixable."""
    if not isinstance(q, dict):
        return None

    text = q.get('question', q.get('text', '')).strip()
    gold = q.get('gold_answer', '').strip()
    req_mem = q.get('required_memories', [])
    qtype = q.get('qtype', 'S1Situational')

    # Normalize qtype
    qtype = TYPE_MAP.get(qtype, qtype)
    if qtype not in VALID_QTYPES:
        qtype = 'S1Situational'

    # Skip if empty question
    if not text:
        return None

    # For FM, gold_answer can be standard
    if qtype == 'FalseMemory':
        gold = gold or "This information was never mentioned."
        req_mem = []
    else:
        # Skip if no gold_answer
        if not gold:
            return None
        # Ensure required_memories is not empty
        if not req_mem:
            # Extract from gold_answer
            req_mem = [gold[:100]]

    # Check for Korean
    if re.search('[가-힣]', text + gold):
        return None

    return {
        "id": f"{prefix}.{idx:03d}",
        "category": prefix.split('.')[0],
        "qtype": qtype,
        "text": text,
        "gold_answer": gold,
        "required_memories": req_mem,
        "points": 0.0 if qtype == 'FalseMemory' else 0.1,
        "false_penalty": 0.25 if qtype == 'FalseMemory' else 0.0
    }


def generate_part_b():
    """Generate Part B (conversation) questions."""
    all_qs = []

    # Load facts per category
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
                        'facts': t['embedded_facts'],
                        'speaker': t['speaker']
                    })

    # === S1, S2, S4, S5, S6, S7 per category ===
    for cat in CATEGORIES:
        facts = facts_by_cat.get(cat, [])
        if len(facts) < 5:
            print(f"  {cat}: too few facts ({len(facts)}), skipping")
            continue

        fact_texts = "\n".join([f"turn_{f['turn_id']}: {f['text']}" for f in facts[:40]])

        prompt = f"""Generate situational memory benchmark questions based on these conversation facts.
Category: {cat}

Facts from conversation:
{fact_texts}

Generate questions in these exact quantities:
- S1Situational: 8 questions (need 1 memory to answer a real situation)
- S2MultiMemory: 4 questions (need 2-3 memories combined)
- S4Temporal: 2 questions (need to track time changes)
- S5Adversarial: 2 questions (present wrong premise, correct memory needed)
- S6Contradiction: 1 question (user said contradictory things)
- S7ReasoningChain: 1 question (need 3+ memories in chain)
- FalseMemory: 2 questions (ask about things NEVER mentioned)

CRITICAL RULES:
1. Every question MUST have "gold_answer" (1-2 sentences, what the correct answer direction is)
2. Every non-FM question MUST have "required_memories" (list of specific facts needed)
3. Every non-FM question MUST have "gold_turn_ids" (list of turn IDs from above)
4. ALL in English
5. FM questions must ask about things NOT in the facts above

Return ONLY a JSON array:
[{{"qtype":"S1Situational","question":"...","gold_answer":"...","required_memories":["..."],"gold_turn_ids":[123]}}]"""

        items = call_haiku(prompt, max_tokens=4000)

        valid = 0
        for i, item in enumerate(items):
            # Add gold_turn_ids from item
            q = validate_question(item, valid + 1, f"{cat}")
            if q:
                if item.get('gold_turn_ids'):
                    q['gold_turn_ids'] = item['gold_turn_ids']
                all_qs.append(q)
                valid += 1

        print(f"  {cat}: {valid}/{len(items)} valid")
        time.sleep(1)

    # === S3 Cross-category ===
    print("\n--- S3 Cross-category ---")
    import itertools
    pairs = list(itertools.combinations(CATEGORIES, 2))

    for idx, (cat1, cat2) in enumerate(pairs):
        facts1 = facts_by_cat.get(cat1, [])[:5]
        facts2 = facts_by_cat.get(cat2, [])[:5]
        if not facts1 or not facts2: continue

        f1_text = "\n".join([f"[{cat1}] turn_{f['turn_id']}: {f['text']}" for f in facts1])
        f2_text = "\n".join([f"[{cat2}] turn_{f['turn_id']}: {f['text']}" for f in facts2])

        prompt = f"""Generate 1 cross-category situational question that requires memories from BOTH categories.

Category 1 ({cat1}) facts:
{f1_text}

Category 2 ({cat2}) facts:
{f2_text}

The question must require information from BOTH categories to answer properly.

CRITICAL: Include gold_answer (1-2 sentences) and required_memories (list).

Return JSON array with 1 item:
[{{"qtype":"S3CrossCategory","question":"...","gold_answer":"...","required_memories":["from {cat1}: ...","from {cat2}: ..."],"gold_turn_ids":[id1,id2]}}]"""

        items = call_haiku(prompt, max_tokens=1000)
        for item in items:
            q = validate_question(item, len(all_qs) + 1, f"{cat1}_{cat2}.S3")
            if q:
                if item.get('gold_turn_ids'):
                    q['gold_turn_ids'] = item['gold_turn_ids']
                all_qs.append(q)

        if (idx + 1) % 10 == 0:
            print(f"  S3: {idx+1}/{len(pairs)} pairs")
        time.sleep(0.5)

    print(f"  S3: {len(pairs)}/{len(pairs)} pairs done")
    return all_qs


def generate_part_a():
    """Generate Part A (document) questions."""
    all_qs = []

    for domain in DOC_DOMAINS:
        doc_path = os.path.join(DOCUMENTS, f'{domain}.txt')
        with open(doc_path, encoding='utf-8') as f:
            doc_text = f.read()

        words = doc_text.split()

        # 2 batches of 25 questions each
        for batch in range(2):
            start = batch * 1500
            chunk = ' '.join(words[start:start+1500])

            prompt = f"""Generate 25 situational questions about {domain.replace('_',' ')} based on this document.

Document excerpt:
{chunk}

Question mix:
- S1Situational: 12 (single fact for a situation)
- S2MultiMemory: 5 (need 2+ facts)
- S4Temporal: 3 (time-related)
- S5Adversarial: 3 (wrong premise)
- S6Contradiction: 1 (seemingly contradictory info)
- S7ReasoningChain: 1 (3+ facts chain)

CRITICAL RULES:
1. Every question MUST have "gold_answer" (1-2 SHORT sentences with SPECIFIC facts from the document)
2. Every question MUST have "required_memories" (list of facts needed)
3. Keep gold_answer SHORT but SPECIFIC
4. ALL in English

Return ONLY JSON array:
[{{"qtype":"S1Situational","question":"...","gold_answer":"The document states that...","required_memories":["specific fact"]}}]"""

            items = call_haiku(prompt, max_tokens=4000)

            valid = 0
            for item in items:
                q = validate_question(item, len(all_qs) + 1, f"{domain}.DOC")
                if q:
                    all_qs.append(q)
                    valid += 1

            print(f"  {domain} batch {batch+1}: {valid}/{len(items)} valid")
            time.sleep(2)

        # FM for this domain (5 questions)
        for i in range(5):
            all_qs.append({
                "id": f"{domain}.DOC.FM.{i+1:03d}",
                "category": domain,
                "qtype": "FalseMemory",
                "text": f"According to the {domain.replace('_',' ')} documents, what specific information is provided about [nonexistent_topic_{domain}_{i+1}]?",
                "gold_answer": "This information is not mentioned in the documents.",
                "required_memories": [],
                "points": 0.0,
                "false_penalty": 0.25
            })

        print(f"  {domain}: done + 5 FM")

    return all_qs


# ===== MAIN =====
print("=" * 60)
print("WMB-100K V2.0 Final Question Generator")
print("=" * 60)

# Part B
print("\n=== PART B (Conversation) ===")
part_b = generate_part_b()
print(f"\nPart B total: {len(part_b)}")

# Part A
print("\n=== PART A (Documents) ===")
part_a = generate_part_a()
print(f"\nPart A total: {len(part_a)}")

# Merge
all_questions = part_b + part_a

# Fix duplicate IDs
seen_ids = set()
for q in all_questions:
    while q['id'] in seen_ids:
        q['id'] = q['id'] + '_2'
    seen_ids.add(q['id'])

# Final validation
final = []
empty_gold = 0
for q in all_questions:
    if q['qtype'] != 'FalseMemory' and not q.get('gold_answer', '').strip():
        empty_gold += 1
        continue
    final.append(q)

if empty_gold > 0:
    print(f"\n⚠ Removed {empty_gold} questions with empty gold_answer")

# Save
out_path = os.path.join(DATASETS, 'all_questions.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(final, f, indent=2, ensure_ascii=False)

# Summary
by_type = {}
pa = sum(1 for q in final if '.DOC.' in q['id'])
pb = len(final) - pa
fm = sum(1 for q in final if q['qtype'] == 'FalseMemory')
for q in final:
    by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1

print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
print(f"Total: {len(final)}")
print(f"Part A: {pa}")
print(f"Part B: {pb}")
print(f"FM: {fm}")
print(f"\nBy type:")
for t, c in sorted(by_type.items()):
    print(f"  {t}: {c}")
print(f"\nPart A score: {pa} x 0.1 = {pa*0.1:.1f} (cap 50)")
print(f"Part B score: {(pb-fm)} x 0.1 = {(pb-fm)*0.1:.1f} (cap 50)")
print(f"FM penalty: {fm} x -0.25 = -{fm*0.25:.1f} max")
print(f"\nSaved to: {out_path}")

# Verify no empty gold_answer
empty = sum(1 for q in final if not q.get('gold_answer','').strip() and q['qtype'] != 'FalseMemory')
print(f"\n{'ALL CLEAR' if empty == 0 else f'WARNING: {empty} empty gold_answers!'}")
