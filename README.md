# WMB-100K — Wontopos Memory Benchmark v2.1

**An enterprise-scale situational benchmark for AI memory systems — 4.3M tokens, 2,708 questions.**

Store 4.3M tokens (2.3M documents + 105K conversation turns), then prove your memory system can retrieve the right information for real-world situations.

---

## What WMB-100K Tests

WMB-100K measures: **can your memory system retrieve the right information for real situations?**

- **Not** LLM reasoning ability
- **Not** response generation quality
- **Only** situational retrieval accuracy + false memory defense

Memory systems don't answer questions — they provide information to LLMs. WMB-100K tests whether the memory system returned the right memories for the situation. The LLM interpretation is out of scope.

> **Important:** Pure retrieval systems (e.g., WME) store and retrieve memories only. They do not interpret or reason about them. To use retrieved memories in production, connect your memory system with an LLM or a personality layer (e.g., WPE) that interprets the memories for the situation. Systems that internally use LLMs (e.g., Hindsight, Mem0) process memories before returning them, which may affect both accuracy and speed.

---

## What Changed in V2

| | V1 | V2 |
|---|---|---|
| Questions | Fact lookup ("What time does the user wake up?") | Situational ("Should we schedule a morning meeting?") |
| Scoring | Keyword matching | GPT-4o-mini semantic judge |
| Focus | Did you find the fact? | Did you bring the right memories for the situation? |

---

## Scale

| Benchmark | Turns | Tokens | Questions | False Memory Test |
|-----------|-------|--------|-----------|-------------------|
| LOCOMO ([Maharana et al., 2024](https://arxiv.org/abs/2402.14839)) | 600 | ~50K | ~1,500 | No |
| LongMemEval ([Wu et al., 2024](https://arxiv.org/abs/2407.15490)) | ~1,000 | ~100K | 500 | No |
| **WMB-100K** | **105,591** | **4.3M** | **2,708** | **Yes (400)** |

| Part | Data | Tokens |
|------|------|--------|
| Part A | 10 document domains (Wikipedia, public domain) | 2.3M |
| Part B | 10 conversation categories (~10K turns each) | ~2.0M |
| **Total** | **Store all 4.3M tokens to answer all questions** | **~4.3M** |

---

## How It Works

### Phase 1: Ingestion
Feed your memory system all data: 2.3M tokens of documents (10 domains) + 105,591 turns of conversation (10 categories).

### Phase 2: Query
Ask 2,708 situational questions. Your system returns relevant memories.

### Phase 3: Score
LLM judges evaluate whether returned memories contain the information needed for each situation. Quick mode uses 1 judge, Official mode uses 3 judges with majority vote.

---

## Question Types

### S1 — Scored (determines your final score)

Single-memory situational questions. One relevant memory needed to address the situation.

- Part A S1: 1,000 questions (documents)
- Part B S1: 1,000 questions (conversation)

Example: *"A friend invites the user to an early breakfast at 7am. What should they know about the user's morning routine?"*

### S2-S7 — Analysis (accuracy % reported separately, not scored)

| Type | Description | Memories Needed | Difficulty |
|------|-------------|-----------------|------------|
| **S2** Multi-Memory | Combine 2-3 memories | 2-3 | ★★ |
| **S3** Cross-Category | Connect different domains | 2-3 | ★★★ |
| **S4** Temporal | Track changes over time | 2+ | ★★★ |
| **S5** Adversarial | Wrong premise, retrieve correct memory | 1-2 | ★★★★ |
| **S6** Contradiction | User said conflicting things, retrieve both | 2+ | ★★★★ |
| **S7** Reasoning Chain | 3+ memories needed in sequence | 3+ | ★★★★★ |

S2-S7 use the same judge (Quick or Official mode) with CORRECT/WRONG binary scoring, reported as accuracy percentages.

### FM — False Memory (penalty)

400 questions about things never mentioned. Correct response: return nothing.

---

## Scoring

```
Part B:  1,000 S1 questions × 0.1 = 100 points max

Score = Part B - FM Penalty - Speed Penalty = 100 max

FM Penalty: each false positive × -0.25 (200 Part B probes, max -50)
Speed Penalty: applied per question based on response latency
Scores can go negative (no 0 clamping). Actual scores are always shown.

Part A (optional): 1,000 S1 document questions. Reported separately for systems
that support document ingestion. Not included in the main score.
```

### Two Scoring Modes

| | Quick Mode | Official Mode |
|---|---|---|
| **Judge** | GPT-4o-mini (1 LLM) | 3 LLMs majority vote |
| **LLMs used** | GPT-4o-mini only | GPT-4o-mini + Claude Haiku + Gemini Flash |
| **Passing rule** | 1/1 CORRECT | **2/3 CORRECT** (majority) |
| **Cost** | ~$0.36 | ~$1.16 |
| **Use case** | Self-testing, development | Leaderboard submission |
| **Label** | "Self-tested" | "Verified" |

Official mode prevents bias toward any single LLM's judgment. A question is CORRECT only if **at least 2 out of 3 judges agree**.

### Judge Prompt

Each question includes `required_memories` — the specific information the system must return.

```
Judge Input:
  Question: "Should we schedule a morning meeting with the user?"
  Required: ["user wakes up at 7:15", "user is not a morning person"]
  Returned: [what your system returned]

Judge Output: CORRECT or WRONG
```

The exact judge prompt is in [`scripts/score.py`](scripts/score.py). Temperature: 0. No partial credit.

> **Fairness note:** The judge receives only the question, required_memories, and returned memories. The `gold_answer` field is **never shown to the judge** to prevent anchoring bias.

### Speed Penalty

Response latency matters in production. A system that takes 60 seconds to recall a memory is unusable regardless of accuracy.

| Response Time | Penalty per Question |
|---------------|---------------------|
| 0 - 300ms | 0 (no penalty) |
| 300ms - 500ms | -0.01 |
| 500ms - 1,000ms | -0.05 |
| 1,000ms+ | -0.1 |

Speed is measured per recall/search call, not including ingestion time.

### FM Penalty Ratio (-0.25 vs +0.1)

The 2.5x penalty reflects that false memories are more harmful than missing memories. A missing memory means "I don't know" — inconvenient but safe. A false memory means confidently returning wrong information — potentially dangerous in production (wrong medical history, wrong legal details, wrong user preferences).

### Grades

| Score | Grade |
|-------|-------|
| 90-100 | Exceptional |
| 80-89 | Excellent |
| 70-79 | Good |
| 60-69 | Fair |
| 50-59 | Below Average |
| 0-49 | Failing |

---

## Results

### WMB-100K v2.1

| System | Part B (/100) | FM Penalty | Speed Penalty | Score (/100) | Grade | p50 | p95 | Judge |
|--------|--------------|------------|---------------|-------------|-------|-----|-----|-------|
| *No results yet* | — | — | — | — | — | — | — | — |

**S2-S7 Accuracy:**

| System | S2 | S3 | S4 | S5 | S6 | S7 |
|--------|-----|-----|-----|-----|-----|-----|
| *No results yet* | — | — | — | — | — | — |

Results will be published when Official mode (3-LLM majority vote) testing is complete. Submit your own results via [GitHub Issues](https://github.com/Irina1920/WMB-100K/issues).


### WME Detailed Results

WME is a retrieval-only system — it stores and retrieves memories without any LLM. Results vary by evaluation method:

| Configuration | Score | Evaluation | Why |
|---------------|-------|------------|-----|
| **WME (Official)** | — | 3-LLM majority (GPT-4o-mini + Claude Haiku + Gemini Flash) | Official scored result. Same standard as all other systems. |
| **WME + WPE (Official)** | — | 3-LLM majority (GPT-4o-mini + Claude Haiku + Gemini Flash) | Full pipeline: WME retrieves, WPE interprets. Official scored. |

- **WME Official**: Scored by the same 3-LLM majority vote as every other system. No special treatment.
- **WME + WPE Official**: Full pipeline scored by the same 3-LLM majority vote. WME retrieves, WPE interprets.

> WME alone is the engine. WPE is the brain. Together, they form the complete system.

> **Note on V1 results:** In V1 testing with keyword matching, Mem0 retrieved 84 correct memories out of 2,224 questions (3.8%) and LangChain retrieved 527 (23.7%). However, both scored 0.0 net because FM penalty (-100) exceeded raw points. The 0.0 score reflects net-after-penalty, not zero retrieval. V2 results with semantic scoring may differ.

### Why WMB-100K Exists

Existing benchmarks (LOCOMO, LongMemEval) have a fundamental problem: **every vendor scores themselves using different evaluation methods**, then claims #1.

- LOCOMO's official scoring (Token-Overlap F1) gives GPT-4 full context only **32.1%**
- Yet vendors self-report 60-90% using their own evaluation methods
- Different scoring criteria make cross-vendor comparison meaningless

WMB-100K solves this with **fixed judges that everyone must use**:

| Mode | Judges | Rule |
|------|--------|------|
| Quick | GPT-4o-mini | 1/1 CORRECT |
| **Official** | **GPT-4o-mini + Claude Haiku 4.5 + Gemini 2.0 Flash** | **2/3 majority** |

No self-scoring. No custom evaluation. Same 3 models judge everyone equally.

### Cross-Benchmark Reference

> **Note:** These scores are **not directly comparable**. Each benchmark uses different evaluation methods, datasets, and scoring criteria. Vendors self-report using their own methods.

| System | LOCOMO (600 turns) | LongMemEval (1K turns) | WMB-100K (100K turns) |
|--------|-------------|------------------|-----------------|
| Full Context (GPT-4) | 32.1% (official F1) | — | $1,638+ per run |
| Mem0 | 66.9% (self-reported) | 49.0% (self-reported) | Testing |
| Supermemory | #1 (self-reported) | 81.6% (self-reported) | Not tested |
| Hindsight | — | 91.4% (self-reported) | Incomplete |
| OpenAI Memory | 52.9% | — | Not tested |

### Cost of Full Context Approach

| Model | Estimated cost per run |
|-------|----------------------|
| GPT-4o-mini | ~$98 |
| GPT-4o | ~$1,638 |
| Claude Sonnet | ~$1,967 |
| Claude Opus | ~$9,835 |

Estimates based on per-question context loading at March 2026 pricing.

### Submit Your Results

To add your system to the leaderboard, open a [GitHub Issue](https://github.com/Irina1920/WMB-100K/issues) with your `result.json` file. We will verify and add it.

---

## Data

### Synthetic Conversation Data

Conversation data (Part B) was generated using **Claude Haiku** (Anthropic). Each category contains ~10K turns of synthetic dialogue with ~100 facts naturally embedded in noise. The data is synthetic — not real user conversations.

Known limitations of synthetic data:
- Conversations may be more structured than real human dialogue
- Fact distribution may be more uniform than organic conversations
- Emotional/social dynamics may be simplified

### Document Data (Part A)

Document data is sourced from **Wikipedia** (public domain, Creative Commons). 10 domains, ~230K tokens each.

### Data Schema

**Question format** (`all_questions.json`):
```json
{
  "id": "daily_life.S1.001",
  "category": "daily_life",
  "qtype": "S1Situational",
  "text": "A friend invites the user to breakfast at 7am. What should they know?",
  "gold_answer": "The user wakes up at 7:15 and is not a morning person.",
  "required_memories": ["user wakes up at 7:15", "user is not a morning person"],
  "gold_turn_ids": [120, 453],
  "points": 0.1,
  "false_penalty": 0.0
}
```

**Conversation turn format** (`{category}.jsonl`):
```json
{
  "turn_id": 120,
  "speaker": "user",
  "text": "I usually wake up around 7:15, barely making it on time...",
  "embedded_facts": ["daily_life.004"]
}
```

### 10 Conversation Categories

| # | Category | Topics | Facts |
|---|----------|--------|-------|
| 1 | `daily_life` | Routines, meals, habits | 100 |
| 2 | `relationships` | Family, friends, partner | 100 |
| 3 | `work_career` | Projects, salary, promotion | 100 |
| 4 | `health_fitness` | Exercise, injuries, diet | 100 |
| 5 | `travel_places` | Trips, restaurants, moving | 100 |
| 6 | `media_taste` | Movies, books, music, games | 100 |
| 7 | `finance_goals` | Savings, loans, investments | 100 |
| 8 | `pets_hobbies` | Photography, climbing, cat | 100 |
| 9 | `education_skills` | Languages, courses, certs | 100 |
| 10 | `beliefs_values` | Philosophy, politics, goals | 100 |

### 10 Document Domains

| # | Domain | Source | Tokens |
|---|--------|--------|--------|
| 1-10 | Daily Life, Economics, History, Law, Literature, Medicine, Philosophy, Psychology, Science, Technology | Wikipedia | ~230K each |

---

## Quick Start

### Requirements

- Python 3.10+
- `pip install openai anthropic`
- OpenAI API key (for scoring — Quick ~$0.36, Official ~$1.16)
- Your memory system with store/search interface

### Run

```bash
# 1. Clone
git clone https://github.com/Irina1920/WMB-100K
cd WMB-100K

# 2. Install dependencies
pip install openai anthropic

# 3. Write an adapter (see scripts/test_mem0.py for example)

# 4. Run your adapter
export OPENAI_API_KEY=sk-...
python scripts/your_adapter.py full

# 5. Score (Quick mode — 1 judge, ~$0.36)
python scripts/score.py datasets/answers.json "YourSystem"

# 5b. Score (Official mode — 3 judges majority vote, ~$1.16)
python scripts/score.py datasets/answers.json "YourSystem" --official
```

### Adapter Template

```python
def store(user_id: str, content: str) -> None:
    """Store a memory."""
    your_system.add(content, user_id=user_id)

def search(user_id: str, query: str) -> list[str]:
    """Search memories, return relevant text."""
    results = your_system.search(query, user_id=user_id)
    return [r["text"] for r in results]
```

See [`scripts/test_mem0.py`](scripts/test_mem0.py) and [`scripts/test_langchain.py`](scripts/test_langchain.py) for working examples.

---

## Limitations

- **Synthetic conversations**: Generated by Claude Haiku, not real user data. Real conversations are messier, more ambiguous, and less structured.
- **English only**: All questions and data are in English. Performance on other languages is untested.
- **Two systems tested**: Only Mem0 and LangChain FAISS have been tested so far. Results may not generalize to all memory systems.
- **LLM judge variability**: Different LLMs produce different scores (up to 10% variance). Official mode uses 3-LLM majority vote to mitigate this. Quick mode uses GPT-4o-mini only.
- **Wikipedia documents**: Part A uses Wikipedia text, which may not represent domain-specific enterprise documents.
- **FM question design**: False memory probes are synthetically generated and may not cover all realistic hallucination patterns.
- **Vendor-created benchmark**: WMB-100K was created by Wontopos, which also develops WME (a memory system tested on this benchmark). While the benchmark uses independent LLM judges and all data/code is open source for verification, users should be aware of this relationship. We encourage independent reproduction and welcome third-party audits.

---

## Cost to Run

| Step | Quick Mode | Official Mode |
|------|------------|---------------|
| Dataset (included in repo) | $0 | $0 |
| Scoring | ~$0.36 (1 judge) | ~$1.16 (3 judges) |
| Your system's ingestion costs | Varies | Varies |

---

## Citation

```bibtex
@misc{wmb100k2026,
  title={WMB-100K v2.1: A 100,000-Turn Situational Benchmark for AI Memory Systems},
  author={Wontopos},
  year={2026},
  url={https://github.com/Irina1920/WMB-100K}
}
```

---

## License

Apache 2.0 — Dataset, benchmark tool, and scoring system are free to use.

---

## Fairness

We are committed to making WMB-100K a fair and unbiased benchmark. If you find any issues with the scoring methodology, question design, data quality, or anything that could affect fairness, please let us know immediately.

- Open a [GitHub Issue](https://github.com/Irina1920/WMB-100K/issues)
- Or email: official@wontopos.com

We will investigate and fix any reported issues promptly. A benchmark is only valuable if it is trusted.

---

## Contact

Maintained by [Wontopos](https://wontopos.com).

| | |
|---|---|
| General | official@wontopos.com |
| CEO | sunwoo.ceo@wontopos.com |
| Marketing | xcx135@wontopos.com |
| Frontend | LoseWoo@wontopos.com |
