"""
WMB-100K Adapter Template
Copy this file and implement store() and search() for your memory system.

Usage:
  python scripts/my_adapter.py full        # All 10 categories
  python scripts/my_adapter.py quick       # First 3 categories only
"""
import json, os, sys, time
sys.stdout.reconfigure(line_buffering=True)

DATASETS = os.path.join(os.path.dirname(__file__), '..', 'datasets')

# ============================================================
# TODO: Implement these two functions for your memory system
# ============================================================

def store(user_id: str, content: str) -> None:
    """Store content into your memory system."""
    raise NotImplementedError("Implement store()")

def search(user_id: str, query: str) -> list[str]:
    """Search memories. Return list of relevant text strings."""
    raise NotImplementedError("Implement search()")

# ============================================================
# Everything below runs automatically. No changes needed.
# ============================================================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"

    with open(os.path.join(DATASETS, 'all_questions.json'), encoding='utf-8') as f:
        all_qs = json.load(f)

    categories = ['daily_life','relationships','work_career','health_fitness',
                  'travel_places','media_taste','finance_goals','education_skills',
                  'pets_hobbies','beliefs_values']

    if mode == "quick":
        categories = categories[:3]

    all_answers = []

    for cat in categories:
        print(f"\n--- {cat} ---")
        path = os.path.join(DATASETS, f'{cat}.jsonl')
        if not os.path.exists(path):
            continue

        with open(path, encoding='utf-8') as f:
            turns = [json.loads(line) for line in f]

        # Ingest all turns
        print(f"  Ingesting {len(turns)} turns...")
        for i, turn in enumerate(turns):
            text = turn.get('text', '').strip()
            if text:
                try:
                    store(cat, f"{turn.get('speaker','user')}: {text}")
                except Exception as e:
                    print(f"  Store error: {e}")
                    break
            if (i + 1) % 2000 == 0:
                print(f"    {i+1}/{len(turns)}")
        print(f"  Ingested: {len(turns)}")

        # Query
        cat_qs = [q for q in all_qs if q.get('category') == cat and '.DOC.' not in q['id']]
        print(f"  Querying {len(cat_qs)} questions...")

        for q in cat_qs:
            start = time.time()
            try:
                memories = search(cat, q['text'])
                response = ' '.join(memories) if memories else 'NO_RESULT'
            except:
                memories = []
                response = 'NO_RESULT'

            all_answers.append({
                'question_id': q['id'],
                'system_response': response if memories else 'NO_RESULT',
                'memories_returned': memories,
                'latency_ms': int((time.time() - start) * 1000)
            })
        print(f"  Done: {len(cat_qs)} answered")

    # S3 Cross-category questions (search both categories)
    s3_qs = [q for q in all_qs if q['qtype'] == 'S3CrossCategory']
    if s3_qs:
        print(f"\n--- S3 Cross-Category ({len(s3_qs)} questions) ---")
        for q in s3_qs:
            start = time.time()
            try:
                mem1 = search(q['category'], q['text'])
                mem2 = search(q.get('category2', q['category']), q['text'])
                memories = list(set(mem1 + mem2))
                response = ' '.join(memories) if memories else 'NO_RESULT'
            except:
                memories = []
                response = 'NO_RESULT'

            all_answers.append({
                'question_id': q['id'],
                'system_response': response if memories else 'NO_RESULT',
                'memories_returned': memories,
                'latency_ms': int((time.time() - start) * 1000)
            })
        print(f"  Done: {len(s3_qs)} answered")

    # Save
    out = os.path.join(DATASETS, 'answers.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(all_answers, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(all_answers)} answers saved to {out}")
    print(f"\nNext step: python scripts/score.py datasets/answers.json \"YourSystem\"")

if __name__ == '__main__':
    main()
