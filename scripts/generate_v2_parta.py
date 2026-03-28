"""Generate V2 situational questions for Part A (documents)."""
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
documents = os.path.join(os.path.dirname(__file__), '..', 'documents')

# Load existing questions - remove old Part A
with open(os.path.join(datasets, 'all_questions.json'), encoding='utf-8') as f:
    all_qs = json.load(f)

# Remove old Part A (DOC) questions
old_count = len(all_qs)
all_qs = [q for q in all_qs if '.DOC.' not in q['id']]
print(f"Removed {old_count - len(all_qs)} old Part A questions")

domains = ['daily_life','economics','history','law','literature',
           'medicine','philosophy','psychology','science','technology']

new_qs = []

for domain in domains:
    doc_path = os.path.join(documents, f'{domain}.txt')
    with open(doc_path, encoding='utf-8') as f:
        doc_text = f.read()
    
    # Take chunks for context
    chunks = []
    words = doc_text.split()
    for i in range(0, min(len(words), 5000), 500):
        chunk = ' '.join(words[i:i+500])
        chunks.append(chunk)
    
    chunk_sample = '\n---\n'.join(chunks[:6])  # ~3000 words sample
    
    prompt = f"""You are generating situational questions for an AI memory benchmark.
The system stores large documents and must retrieve relevant information for real-world situations.

Domain: {domain.replace('_',' ')}
Document excerpts:
{chunk_sample}

Generate 50 situational questions (S1-S7 mix) based on this document content.

Question types:
- S1 (20): Single fact needed for a situation. "If someone wanted to X, what should they know about Y?"
- S2 (10): Multiple facts needed. "Considering both X and Y from the document, what would be the best approach?"
- S3 (5): Cross-domain application. "How does this document's info about X relate to a real-world situation about Y?"
- S4 (5): Temporal. "How has X changed over time according to the document?"
- S5 (5): Adversarial. Present a wrong claim from the document, system must retrieve correct info.
- S6 (3): Contradiction. "The document mentions both X and Y which seem contradictory. What's the full picture?"
- S7 (2): Reasoning chain. Needs 3+ facts combined.

Format as JSON array:
[{{
  "qtype": "S1Situational",
  "question": "...",
  "gold_answer": "The document states that... (include the specific fact)",
  "required_memories": ["fact 1 from document"]
}}]

Rules:
- ALL questions in English
- gold_answer must contain specific information FROM the document
- Questions should be practical/situational, not just "what does the document say about X?"
- Return ONLY valid JSON array, no markdown"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        if text.startswith('```'): text = text.split('\n',1)[1].rsplit('```',1)[0]
        items = json.loads(text)
        
        for i, item in enumerate(items):
            qtype = item.get("qtype", "S1Situational")
            q = {
                "id": f"{domain}.DOC.{qtype}.{i+1:03d}",
                "category": domain,
                "qtype": qtype,
                "text": item["question"],
                "gold_answer": item["gold_answer"],
                "required_memories": item.get("required_memories", []),
                "points": 0.1,
                "false_penalty": 0.0
            }
            new_qs.append(q)
        print(f"  {domain}: {len(items)} Part A questions")
    except Exception as e:
        print(f"  {domain}: ERROR - {e}")
    time.sleep(2)

# Add Part A FM questions (10 per domain)
print("\nGenerating Part A FM...")
for domain in domains:
    for i in range(10):
        q = {
            "id": f"{domain}.DOC.FM.{i+1:03d}",
            "category": domain,
            "qtype": "FalseMemory",
            "text": f"According to the {domain.replace('_',' ')} documents, what specific details are provided about [fictional topic {domain}_{i+1}]?",
            "gold_answer": "This information is not in the documents.",
            "required_memories": [],
            "points": 0.0,
            "false_penalty": 0.25
        }
        new_qs.append(q)
    print(f"  {domain}: 10 FM questions")

all_qs.extend(new_qs)

with open(os.path.join(datasets, 'all_questions.json'), 'w', encoding='utf-8') as f:
    json.dump(all_qs, f, indent=2, ensure_ascii=False)

# Final summary
by_type = {}
part_a = 0
part_b = 0
for q in all_qs:
    t = q['qtype']
    by_type[t] = by_type.get(t, 0) + 1
    if '.DOC.' in q['id']:
        part_a += 1
    else:
        part_b += 1

print(f"\n=== Final Summary ===")
print(f"Total: {len(all_qs)} questions")
print(f"Part A: {part_a}")
print(f"Part B: {part_b}")
for t, c in sorted(by_type.items()):
    print(f"  {t}: {c}")
