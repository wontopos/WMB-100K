"""
WMB-100K V2.1 x WME (Wontopos Memory Engine) Test
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")
WME_URL = os.environ.get("WME_URL", "http://localhost:8080")
WME_API_KEY = os.environ.get("WME_API_KEY", "test123")


def store(user_id, content, category="default"):
    import urllib.request
    body = json.dumps({
        "user_id": user_id,
        "content": content,
        "category": category
    }).encode('utf-8')
    req = urllib.request.Request(
        f"{WME_URL}/api/v1/memory/store",
        data=body,
        headers={
            "X-API-Key": WME_API_KEY,
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def search(user_id, query):
    import urllib.request
    body = json.dumps({
        "user_id": user_id,
        "query": query,
        "top_k": 10
    }).encode('utf-8')
    req = urllib.request.Request(
        f"{WME_URL}/api/v1/memory/search",
        data=body,
        headers={
            "X-API-Key": WME_API_KEY,
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e), "memories": []}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    cats = ["daily_life", "relationships", "work_career"] if mode == "quick" else get_all_cats()

    print("=== WMB-100K V2.1 x WME Test ===")
    print(f"  Mode: {mode}")
    print(f"  Categories: {len(cats)}")
    print(f"  WME URL: {WME_URL}")
    print()

    with open(os.path.join(DATASETS_DIR, "all_questions.json"), encoding='utf-8') as f:
        all_questions = json.load(f)

    all_answers = []

    # Phase 1: Ingest all turns (full)
    for cat in cats:
        print(f"--- {cat} (ingesting) ---")
        turns_path = os.path.join(DATASETS_DIR, f"{cat}.jsonl")
        if not os.path.exists(turns_path):
            print(f"  SKIP: not found")
            continue

        with open(turns_path, encoding='utf-8') as f:
            turns = [json.loads(line) for line in f]

        user_id = f"wmb_{cat}"
        print(f"  Ingesting {len(turns)} turns (full)...")
        ingested = 0

        for i, turn in enumerate(turns):
            text = turn.get('text', '').strip()
            if not text:
                continue
            result = store(user_id, f"{turn['speaker']}: {text}", category=cat)
            if result and "error" not in str(result).lower():
                ingested += 1
            if (i + 1) % 2000 == 0:
                print(f"    {i+1}/{len(turns)}")

        print(f"  Ingested: {ingested}/{len(turns)}")

    # Phase 2: Query Part B questions
    part_b_qs = [q for q in all_questions if '.DOC.' not in q['id'] and q['qtype'] != 'S3CrossCategory']
    print(f"\n--- Querying {len(part_b_qs)} Part B questions ---")

    for q in part_b_qs:
        cat = q.get('category', '')
        uid = f"wmb_{cat}"

        start = time.time()
        result = search(uid, q["text"])
        latency = int((time.time() - start) * 1000)

        memories = []
        if result and "memories" in result:
            memories = [m.get("content", "") for m in result["memories"]]

        all_answers.append({
            "question_id": q["id"],
            "system_response": memories[0] if memories else "NO_RESULT",
            "memories_returned": memories,
            "latency_ms": latency
        })

    # Phase 3: S3 Cross-category questions
    s3_qs = [q for q in all_questions if q['qtype'] == 'S3CrossCategory']
    if s3_qs:
        print(f"\n--- S3 Cross-Category ({len(s3_qs)} questions) ---")
        for q in s3_qs:
            uid1 = f"wmb_{q['category']}"
            uid2 = f"wmb_{q.get('category2', q['category'])}"

            start = time.time()
            result1 = search(uid1, q["text"])
            result2 = search(uid2, q["text"])
            latency = int((time.time() - start) * 1000)

            memories = []
            for r in [result1, result2]:
                if r and "memories" in r:
                    memories.extend([m.get("content", "") for m in r["memories"]])
            memories = list(set(memories))

            all_answers.append({
                "question_id": q["id"],
                "system_response": ' '.join(memories) if memories else "NO_RESULT",
                "memories_returned": memories,
                "latency_ms": latency
            })
        print(f"  Done: {len(s3_qs)} answered")

    # Save
    out_path = os.path.join(DATASETS_DIR, "answers_wme.json")
    with open(out_path, "w", encoding='utf-8') as f:
        json.dump(all_answers, f, indent=2, ensure_ascii=False)

    lats = sorted([a["latency_ms"] for a in all_answers]) if all_answers else [0]
    no_result = sum(1 for a in all_answers if a["system_response"] == "NO_RESULT")

    print(f"\nWME test complete. {len(all_answers)} answers -> {out_path}")
    print(f"  Latency: p50={lats[len(lats)//2]}ms  p95={lats[int(len(lats)*0.95)]}ms")
    print(f"  No result: {no_result}/{len(all_answers)} ({no_result*100//max(len(all_answers),1)}%)")


def get_all_cats():
    return ["daily_life", "relationships", "work_career", "health_fitness",
            "travel_places", "media_taste", "finance_goals", "education_skills",
            "pets_hobbies", "beliefs_values"]


if __name__ == "__main__":
    main()
