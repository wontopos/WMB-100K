"""WMB-100K V2 test adapter for Hindsight (vectorize-io/hindsight)."""
import json, os, sys, time
sys.stdout.reconfigure(line_buffering=True)

from hindsight_client import Hindsight

datasets = os.path.join(os.path.dirname(__file__), '..', 'datasets')

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"

    h = Hindsight(base_url='http://localhost:8888')

    # Load questions
    with open(os.path.join(datasets, 'all_questions.json'), encoding='utf-8') as f:
        all_qs = json.load(f)

    # Part B questions only (conversation)
    part_b_qs = [q for q in all_qs if '.DOC.' not in q['id']]

    categories = ['daily_life','relationships','work_career','health_fitness',
                  'travel_places','media_taste','finance_goals','education_skills',
                  'pets_hobbies','beliefs_values']

    if mode == "quick":
        categories = categories[:3]

    all_answers = []

    for cat in categories:
        print(f"\n--- {cat} ---")
        jsonl_path = os.path.join(datasets, f'{cat}.jsonl')
        if not os.path.exists(jsonl_path):
            print(f"  Skip: {jsonl_path} not found")
            continue

        with open(jsonl_path, encoding='utf-8') as f:
            turns = [json.loads(line) for line in f]

        bank_id = f'wmb-{cat}'

        # Ingest all turns
        print(f"  Ingesting {len(turns)} turns (full)...")
        ingested = 0
        batch_text = ""
        batch_size = 0

        for i, turn in enumerate(turns):
            speaker = turn.get('speaker', 'user')
            text = turn.get('text', '').strip()
            if not text:
                continue

            batch_text += f"{speaker}: {text}\n"
            batch_size += 1

            # Send every 20 turns as a batch
            if batch_size >= 20 or i == len(turns) - 1:
                try:
                    h.retain(bank_id=bank_id, content=batch_text)
                    ingested += batch_size
                except Exception as e:
                    print(f"    Retain error: {e}")
                batch_text = ""
                batch_size = 0

                if ingested % 1000 == 0 and ingested > 0:
                    print(f"    Ingested: {ingested}/{len(turns)}")

                time.sleep(0.1)

        print(f"  Ingested: {ingested}/{len(turns)}")

        if ingested == 0:
            print("  No data ingested, skipping questions")
            continue

        # Wait for processing
        time.sleep(5)

        # Query questions for this category
        cat_qs = [q for q in part_b_qs if q.get('category') == cat]
        print(f"  Querying {len(cat_qs)} questions...")

        for q in cat_qs:
            start = time.time()
            try:
                results = h.recall(bank_id=bank_id, query=q['text'])
                memories = [r.text for r in results if r.text]
                response = ' '.join(memories) if memories else 'NO_RESULT'
            except Exception as e:
                response = 'NO_RESULT'
                memories = []

            latency = int((time.time() - start) * 1000)

            all_answers.append({
                'question_id': q['id'],
                'system_response': response if memories else 'NO_RESULT',
                'memories_returned': memories,
                'latency_ms': latency
            })

        print(f"  Done: {len(cat_qs)} questions answered")

    # S3 Cross-category questions
    s3_qs = [q for q in all_qs if q['qtype'] == 'S3CrossCategory']
    if s3_qs:
        print(f"\n--- S3 Cross-Category ({len(s3_qs)} questions) ---")
        for q in s3_qs:
            bank1 = f'wmb-{q["category"]}'
            bank2 = f'wmb-{q.get("category2", q["category"])}'
            start = time.time()
            try:
                r1 = h.recall(bank_id=bank1, query=q['text'])
                r2 = h.recall(bank_id=bank2, query=q['text'])
                memories = list(set([r.text for r in r1 if r.text] + [r.text for r in r2 if r.text]))
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
    out_path = os.path.join(datasets, 'answers_hindsight.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_answers, f, indent=2, ensure_ascii=False)

    latencies = sorted([a['latency_ms'] for a in all_answers]) if all_answers else [0]
    no_result = sum(1 for a in all_answers if a['system_response'] == 'NO_RESULT')

    print(f"\nHindsight test complete. {len(all_answers)} answers -> {out_path}")
    print(f"  Latency: p50={latencies[len(latencies)//2]}ms  p95={latencies[int(len(latencies)*0.95)]}ms")
    print(f"  No result: {no_result}/{len(all_answers)} ({no_result*100//max(len(all_answers),1)}%)")

if __name__ == '__main__':
    main()
