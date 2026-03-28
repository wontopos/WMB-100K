"""
WMB x Mem0 Test
Ingest data into Mem0 open-source -> query -> score
"""

import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')

# Mem0 config (open-source local mode)
os.environ.setdefault("OPENAI_API_KEY", "skip")  # Mem0 defaults to OpenAI

from mem0 import Memory

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")
QUICK_CATS = ["daily_life", "work_career", "relationships"]

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    cats = QUICK_CATS if mode == "quick" else get_all_cats()

    print("=== WMB × Mem0 Test ===")
    print(f"  Mode: {mode}")
    print(f"  Categories: {len(cats)}")
    print()

    # Initialize Mem0 (local, without Qdrant)
    config = {
        "version": "v1.1"
    }

    # Check API key
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if anthropic_key and anthropic_key != "skip":
        config["llm"] = {
            "provider": "anthropic",
            "config": {
                "model": "claude-haiku-4-5-20251001",
                "api_key": anthropic_key,
                "temperature": 0.1,
                # Remove top_p -- Anthropic does not support both temperature and top_p
            }
        }
        openai_key_val = os.environ.get("OPENAI_API_KEY", "")
        if openai_key_val and openai_key_val != "skip":
            config["embedder"] = {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": openai_key_val
                }
            }
            print("  Embedder: OpenAI text-embedding-3-small")
        else:
            config["embedder"] = {
                "provider": "huggingface",
                "config": {
                    "model": "sentence-transformers/all-MiniLM-L6-v2"
                }
            }
            print("  Embedder: HuggingFace (local)")
        print("  LLM: Anthropic Haiku")
    elif openai_key and openai_key != "skip":
        print("  LLM: OpenAI (default)")
    else:
        print("  ⚠ No API key. Mem0 needs OpenAI or Anthropic key.")
        print("  Set OPENAI_API_KEY or ANTHROPIC_API_KEY")
        return

    try:
        m = Memory.from_config(config)
    except Exception as e:
        print(f"  ⚠ Mem0 init failed: {e}")
        print("  Trying default config...")
        m = Memory()

    answers = []

    # Load V2 questions
    with open(os.path.join(DATASETS_DIR, "all_questions.json"), encoding='utf-8') as f:
        all_questions = json.load(f)

    # Phase 1: Ingest all conversation data
    for cat in cats:
        print(f"\n--- {cat} (ingesting) ---")
        user_id = f"wmb_{cat}"

        turns_path = os.path.join(DATASETS_DIR, f"{cat}.jsonl")
        if not os.path.exists(turns_path):
            print(f"  ⚠ No data for {cat}")
            continue

        all_turns = []
        with open(turns_path, encoding='utf-8') as f:
            for line in f:
                all_turns.append(json.loads(line))

        all_contents = [f"{t['speaker']}: {t['text']}" for t in all_turns]

        print(f"  Ingesting {len(all_contents)} turns (full)...")
        ingested = 0
        for content in all_contents:
            try:
                m.add(content, user_id=user_id)
                ingested += 1
            except Exception as e:
                if ingested < 3:
                    print(f"    ⚠ add failed: {e}")
                break
            time.sleep(0.2)

        print(f"  Ingested: {ingested}/{len(all_contents)}")

    # Phase 2: Query all V2 Part B questions
    part_b_questions = [q for q in all_questions if '.DOC.' not in q['id']]
    print(f"\n--- Querying {len(part_b_questions)} Part B questions ---")
    user_id = "wmb_all"

    for q in part_b_questions:
        # Use category-specific user_id for search
        cat = q.get('category', '')
        uid = f"wmb_{cat}" if cat else user_id

        start = time.time()
        try:
            results = m.search(q["text"], user_id=uid)

            # S3 cross-category: also search second category
            if q.get('category2'):
                uid2 = f"wmb_{q['category2']}"
                results2 = m.search(q["text"], user_id=uid2)
                if isinstance(results, dict) and "results" in results:
                    if isinstance(results2, dict) and "results" in results2:
                        results["results"] = results["results"] + results2["results"]
                elif isinstance(results, list) and isinstance(results2, list):
                    results = results + results2
            latency = int((time.time() - start) * 1000)

            memories = []
            result_list = results
            if isinstance(results, dict) and "results" in results:
                result_list = results["results"]
            if isinstance(result_list, list):
                for r in result_list[:5]:
                    if isinstance(r, dict) and "memory" in r:
                        memories.append(r["memory"])
                    elif isinstance(r, dict) and "text" in r:
                        memories.append(r["text"])
                    elif isinstance(r, str):
                        memories.append(r)

            top = memories[0] if memories else "NO_RESULT"

        except Exception as e:
            latency = 0
            top = "ERROR"
            memories = []

        answers.append({
            "question_id": q["id"],
            "question": q["text"],
            "gold_answer": q.get("gold_answer", ""),
            "required_memories": q.get("required_memories", []),
            "system_response": top,
            "memories_returned": memories,
            "latency_ms": latency
        })

        time.sleep(0.2)

    print(f"  Done: {len(part_b_questions)} questions answered")

    # 3. Save
    out_path = os.path.join(DATASETS_DIR, "answers_mem0.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(answers, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Mem0 test complete. {len(answers)} answers → {out_path}")

    # Simple statistics
    if answers:
        lats = [a["latency_ms"] for a in answers if a["latency_ms"] > 0]
        if lats:
            lats.sort()
            print(f"  Latency: p50={lats[len(lats)//2]}ms  p95={lats[int(len(lats)*0.95)]}ms")

        no_result = sum(1 for a in answers if a["system_response"] in ["NO_RESULT", "ERROR"])
        print(f"  No result: {no_result}/{len(answers)} ({no_result*100//len(answers)}%)")


def get_all_cats():
    return ["daily_life", "relationships", "work_career", "health_fitness",
            "travel_places", "media_taste", "finance_goals", "education_skills",
            "pets_hobbies", "beliefs_values"]


if __name__ == "__main__":
    main()
