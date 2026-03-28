"""
WMB-100K v2.0 Scorer

Two scoring modes:
1. Semantic (main): GPT-4o-mini judges if returned memories contain
   the correct information to answer the question
2. All systems scored by same LLM judges — no keyword-only mode

For each question:
- Send question + required_memories + returned memories to LLM judge (gold_answer NOT shown to judge)
- Judge: "Do the returned memories contain the information needed?"
- CORRECT or WRONG only, no partial credit
- FM: must return nothing
"""

import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")

JUDGE_PROMPT = """You are a benchmark scorer for a memory retrieval system.

Your job: determine if the RETURNED MEMORIES contain the specific information described in REQUIRED MEMORIES.

CRITICAL RULES:
- ONLY evaluate based on the returned memories below. Do NOT use your own knowledge.
- If the returned memories are empty, answer WRONG.
- If the returned memories are irrelevant to the question, answer WRONG.
- CORRECT: The returned memories contain the specific facts listed in required memories.
- WRONG: The returned memories do NOT contain the required information.
- Be strict. The specific facts must be PRESENT IN THE RETURNED MEMORIES, not in your training data.

Question: {question}
Required Memories: {required_memories}
Returned Memories: {memories}

Answer with ONLY one word: CORRECT or WRONG"""


def _call_openai(prompt, model, api_key):
    """Call OpenAI-compatible API."""
    import urllib.request
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 5,
        "temperature": 0
    }).encode('utf-8')
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return "CORRECT" in result["choices"][0]["message"]["content"].strip().upper()
        except:
            if attempt < 2: time.sleep(2)
    return False


def _call_anthropic(prompt, api_key):
    """Call Anthropic Claude Haiku."""
    import urllib.request
    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 5,
        "messages": [{"role": "user", "content": prompt}]
    }).encode('utf-8')
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return "CORRECT" in result["content"][0]["text"].strip().upper()
        except:
            if attempt < 2: time.sleep(2)
    return False


def _call_gemini(prompt, api_key):
    """Call Google Gemini Flash."""
    import urllib.request
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 5, "temperature": 0}
    }).encode('utf-8')
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        data=body,
        headers={"Content-Type": "application/json"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                text = result["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
                return "CORRECT" in text
        except:
            if attempt < 2: time.sleep(2)
    return False


def judge_with_llm(question, required_memories, memories, api_key, official=False):
    """Judge with 1 LLM (Quick) or 3 LLMs majority vote (Official)."""
    mem_text = "\n".join(memories) if memories else "(empty - no memories returned)"
    req_text = ", ".join(required_memories) if isinstance(required_memories, list) else str(required_memories)
    prompt = JUDGE_PROMPT.format(
        question=question,
        required_memories=req_text,
        memories=mem_text[:3000]
    )

    if not official:
        # Quick mode: GPT-4o-mini only
        return _call_openai(prompt, "gpt-4o-mini", api_key)

    # Official mode: 3-LLM majority vote
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key = os.environ.get("GOOGLE_API_KEY", "")

    votes = []
    votes.append(_call_openai(prompt, "gpt-4o-mini", api_key))

    if anthropic_key:
        votes.append(_call_anthropic(prompt, anthropic_key))
    else:
        print("  WARNING: ANTHROPIC_API_KEY not set, skipping Claude judge")
        votes.append(False)

    if gemini_key:
        votes.append(_call_gemini(prompt, gemini_key))
    else:
        print("  WARNING: GOOGLE_API_KEY not set, skipping Gemini judge")
        votes.append(False)

    # Majority: 2/3 must agree
    return sum(votes) >= 2




def score(answers_file, system_name, use_llm=True, is_official=False):
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if use_llm and not openai_key:
        print("ERROR: OPENAI_API_KEY required for LLM judge.")
        sys.exit(1)

    with open(os.path.join(DATASETS_DIR, 'all_questions.json'), encoding='utf-8') as f:
        questions = json.load(f)
    q_map = {q['id']: q for q in questions}

    with open(answers_file, encoding='utf-8') as f:
        answers = json.load(f)

    by_type = {}
    part_a_correct = 0
    part_a_total = 0
    part_b_correct = 0
    part_b_total = 0
    fm_probes = 0
    fm_false = 0

    total_q = len(answers)
    for i, ans in enumerate(answers):
        q = q_map.get(ans['question_id'])
        if not q:
            continue
        qtype = q['qtype']
        if qtype not in by_type:
            by_type[qtype] = {'correct': 0, 'total': 0}
        by_type[qtype]['total'] += 1

        is_doc = '.DOC.' in q['id']
        memories = ans.get('memories_returned', [])
        response = ans.get('system_response', '')

        if qtype == 'FalseMemory':
            fm_probes += 1
            if response == 'NO_RESULT' or not memories:
                by_type[qtype]['correct'] += 1
            else:
                fm_false += 1
            continue

        # Empty memories = automatic WRONG (no need to call judge)
        if not memories or response == 'NO_RESULT':
            is_correct = False
        elif use_llm:
            is_correct = judge_with_llm(
                q['text'], q.get('required_memories', []), memories, openai_key, official=is_official
            )
        else:
            print("ERROR: LLM judge required. Use OPENAI_API_KEY.")
            is_correct = False

        if is_correct:
            if is_doc:
                part_a_correct += 1
            else:
                part_b_correct += 1
            by_type[qtype]['correct'] += 1

        if is_doc:
            part_a_total += 1
        else:
            part_b_total += 1

        # Progress
        if (i + 1) % 100 == 0:
            print(f"  Scored {i+1}/{total_q}...")

    # Speed penalty
    speed_penalty = 0.0
    latencies = []
    for ans in answers:
        lat = ans.get('latency_ms', 0)
        latencies.append(lat)
        if lat > 1000:
            speed_penalty += 0.1
        elif lat > 500:
            speed_penalty += 0.05
        elif lat > 300:
            speed_penalty += 0.01

    latencies.sort()
    p50 = latencies[len(latencies)//2] if latencies else 0
    p95 = latencies[int(len(latencies)*0.95)] if latencies else 0

    # Calculate scores — Part B is main score, Part A reported separately
    part_a_score = (part_a_correct / max(part_a_total, 1)) * 100 if part_a_total > 0 else None
    part_b_raw = (part_b_correct / max(part_b_total, 1)) * 100
    fm_penalty = fm_false * 0.25
    total = part_b_raw - fm_penalty - speed_penalty  # no 0 clamping — actual score shown

    if is_official:
        mode = "Official (3-LLM majority: GPT-4o-mini + Claude Haiku + Gemini Flash)"
        judges_used = ["gpt-4o-mini", "claude-haiku-4-5", "gemini-flash"]
    elif use_llm:
        mode = "Quick (GPT-4o-mini)"
        judges_used = ["gpt-4o-mini"]
    else:
        mode = "LLM Judge required"
        judges_used = []
    print(f"\n=== WMB-100K v2.1 Score: {system_name} ===")
    print(f"Scoring mode: {mode}")
    print()
    if part_a_score is not None:
        print(f"Part A (optional): {part_a_correct}/{part_a_total} ({part_a_correct*100//max(part_a_total,1)}%) = {part_a_score:.1f}/100")
    else:
        print(f"Part A (optional): N/A (no document ingestion)")
    print(f"Part B (main): {part_b_correct}/{part_b_total} ({part_b_correct*100//max(part_b_total,1)}%) = {part_b_raw:.1f}/100")
    print(f"FM: {fm_probes} probes, {fm_false} false positives = -{fm_penalty:.1f}")
    print(f"Speed: p50={p50}ms, p95={p95}ms, penalty = -{speed_penalty:.1f}")
    print(f"Score: {part_b_raw:.1f} - {fm_penalty:.1f} - {speed_penalty:.1f} = {total:.1f}/100")
    print()
    print("S-Level Accuracy:")
    for t in ['S1Situational', 'S2MultiMemory', 'S3CrossCategory', 'S4Temporal', 'S5Adversarial', 'S6Contradiction', 'S7ReasoningChain', 'FalseMemory']:
        d = by_type.get(t, {'correct': 0, 'total': 0})
        pct = d['correct'] * 100 // max(d['total'], 1)
        print(f"  {t}: {d['correct']}/{d['total']} ({pct}%)")


    # Save result
    result = {
        "system_name": system_name,
        "wmb_version": "v2.1",
        "scoring_mode": mode,
        "judges_used": judges_used,
        "part_a": {"correct": part_a_correct, "total": part_a_total, "score": round(part_a_score, 1) if part_a_score is not None else None, "note": "optional, not in main score"},
        "part_b": {"correct": part_b_correct, "total": part_b_total, "score": round(part_b_raw, 1)},
        "fm": {"probes": fm_probes, "false_positives": fm_false, "penalty": round(fm_penalty, 1)},
        "speed": {"p50_ms": p50, "p95_ms": p95, "penalty": round(speed_penalty, 1)},
        "total": round(total, 1),
        "s_accuracy": {
            t: {"correct": by_type.get(t, {}).get('correct', 0), "total": by_type.get(t, {}).get('total', 0)}
            for t in ['S1Situational', 'S2MultiMemory', 'S3CrossCategory', 'S4Temporal', 'S5Adversarial', 'S6Contradiction', 'S7ReasoningChain', 'FalseMemory']
        }
    }

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    os.makedirs(results_dir, exist_ok=True)
    result_file = os.path.join(results_dir, f"{system_name.lower().replace(' ', '_').replace('(','').replace(')','')}_result.json")
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResult saved: {result_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python score.py <answers.json> <system_name> [--official]")
        print("  Default: LLM judge (requires OPENAI_API_KEY)")
        print("  --official: Use 3-LLM majority vote (GPT-4o-mini + Claude Haiku + Gemini Flash)")
        sys.exit(1)

    use_llm = True  # LLM judge always required
    is_official = "--official" in sys.argv
    score(sys.argv[1], sys.argv[2], use_llm=use_llm, is_official=is_official)
