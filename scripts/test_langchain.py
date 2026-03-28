"""
WMB-100K × LangChain (FAISS + OpenAI Embeddings) Test
"""

import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    cats = ["daily_life", "work_career", "relationships"] if mode == "quick" else get_all_cats()

    print("=== WMB-100K × LangChain (FAISS) Test ===")
    print(f"  Mode: {mode}")
    print(f"  Categories: {len(cats)}")
    print(f"  Embedder: OpenAI text-embedding-3-small")
    print(f"  Vector Store: FAISS (in-memory)")
    print()

    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = None
    all_answers = []

    # Load V2 questions
    with open(os.path.join(DATASETS_DIR, "all_questions.json"), encoding='utf-8') as f:
        all_questions = json.load(f)

    # Phase 1: Ingest all conversation data
    for cat in cats:
        print(f"--- {cat} (ingesting) ---")

        dataset_file = os.path.join(DATASETS_DIR, f"{cat}.jsonl")
        all_turns = []
        with open(dataset_file, encoding='utf-8') as f:
            for line in f:
                all_turns.append(json.loads(line))

        texts = []
        metadatas = []
        for t in all_turns:
            texts.append(f"{t['speaker']}: {t['text']}")
            metadatas.append({"turn_id": t["turn_id"], "category": cat})

        print(f"  Ingesting {len(texts)} turns (full)...")

        if vectorstore is None:
            vectorstore = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
        else:
            new_vs = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
            vectorstore.merge_from(new_vs)

        print(f"  Ingested: {len(texts)}/{len(texts)}")

    # Phase 2: Query all V2 questions (Part B only - conversation)
    part_b_questions = [q for q in all_questions if '.DOC.' not in q['id']]
    print(f"\n--- Querying {len(part_b_questions)} Part B questions ---")

    for q in part_b_questions:
        start = time.time()
        try:
            docs = vectorstore.similarity_search(q["text"], k=5)
            memories = [doc.page_content for doc in docs]
            response = " | ".join(memories) if memories else "NO_RESULT"
        except Exception as e:
            memories = []
            response = "NO_RESULT"

        latency = int((time.time() - start) * 1000)

        all_answers.append({
            "question_id": q["id"],
            "question": q["text"],
            "gold_answer": q.get("gold_answer", ""),
            "required_memories": q.get("required_memories", []),
            "system_response": response,
            "memories_returned": memories,
            "latency_ms": latency
        })

    print(f"  Done: {len(part_b_questions)} questions answered")
    print()

    out_file = os.path.join(DATASETS_DIR, "answers_langchain.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_answers, f, ensure_ascii=False, indent=2)

    latencies = [a["latency_ms"] for a in all_answers]
    latencies.sort()
    p50 = latencies[len(latencies)//2] if latencies else 0
    p95 = latencies[int(len(latencies)*0.95)] if latencies else 0
    no_result = sum(1 for a in all_answers if a["system_response"] == "NO_RESULT")

    print(f"✅ LangChain test complete. {len(all_answers)} answers → {out_file}")
    print(f"  Latency: p50={p50}ms  p95={p95}ms")
    print(f"  No result: {no_result}/{len(all_answers)} ({no_result*100//max(len(all_answers),1)}%)")


def get_all_cats():
    cats = []
    for f in os.listdir(DATASETS_DIR):
        if f.endswith(".jsonl"):
            cats.append(f.replace(".jsonl", ""))
    return sorted(cats)


if __name__ == "__main__":
    main()
