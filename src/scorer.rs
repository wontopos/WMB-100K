//! WMB-100K v2.1 scoring + report generation.
//! Part B: Conversation memory (100.0 points) — main score
//! Part A: Document knowledge (optional, reported separately)
//! False memory: -0.25 points/each
//! Speed penalty: per-question latency penalty
//! Maximum score: 100.0

use crate::types::*;
use std::collections::HashMap;

const POINT_DIRECT: f64 = 0.1;
const PENALTY_FALSE: f64 = 0.25;
const MAX_SCORE: f64 = 100.0;

pub async fn score(dataset: &str) -> anyhow::Result<()> {
    let answers: Vec<Answer> = load_json(&format!("{}/answers.json", dataset))?;
    let all_q: Vec<Question> = load_json(&format!("{}/all_questions.json", dataset))?;
    let q_map: HashMap<String, &Question> = all_q.iter().map(|q| (q.id.clone(), q)).collect();

    let mut part_a_correct: u32 = 0;
    let mut part_a_total: u32 = 0;
    let mut part_b_correct: u32 = 0;
    let mut part_b_total: u32 = 0;

    let mut fm = FalseMemoryScore { probes: 0, false_positives: 0, penalty: 0.0 };
    let mut by_type: HashMap<String, (u32, u32)> = HashMap::new(); // (correct, total)
    let mut latencies: Vec<u64> = Vec::new();
    let mut speed_penalty: f64 = 0.0;

    for ans in &answers {
        let q = match q_map.get(&ans.question_id) {
            Some(q) => q,
            None => continue,
        };

        latencies.push(ans.latency_ms);

        // Speed penalty per question
        speed_penalty += match ans.latency_ms {
            0..=300 => 0.0,
            301..=500 => 0.01,
            501..=1000 => 0.05,
            _ => 0.1,
        };

        let is_doc = q.id.contains(".DOC.");
        let qtype_str = format!("{:?}", q.qtype);
        let entry = by_type.entry(qtype_str.clone()).or_insert((0, 0));

        match q.qtype {
            QuestionType::FalseMemory => {
                fm.probes += 1;
                if ans.system_response == "NO_RESULT" || ans.memories_returned.is_empty() {
                    // Correct: returned nothing
                } else {
                    fm.false_positives += 1;
                }
            }
            _ => {
                entry.1 += 1;

                // Empty memories = automatic WRONG
                if ans.memories_returned.is_empty() || ans.system_response == "NO_RESULT" {
                    if is_doc { part_a_total += 1; } else { part_b_total += 1; }
                    continue;
                }

                let is_correct = judge_keyword(&ans.memories_returned, &q.gold_answer);

                if is_correct {
                    entry.0 += 1;
                    if is_doc {
                        part_a_correct += 1;
                    } else {
                        part_b_correct += 1;
                    }
                }

                if is_doc { part_a_total += 1; } else { part_b_total += 1; }
            }
        }
    }

    fm.penalty = fm.false_positives as f64 * PENALTY_FALSE;

    let part_b_raw = if part_b_total > 0 {
        part_b_correct as f64 / part_b_total as f64 * 100.0
    } else { 0.0 };

    let total = part_b_raw - fm.penalty - speed_penalty; // no 0 clamping

    let part_a_pct = if part_a_total > 0 {
        Some(part_a_correct as f64 / part_a_total as f64 * 100.0)
    } else { None };

    latencies.sort();
    let lat = calc_latency(&latencies);

    // Output
    println!();
    println!("============================================================");
    println!("  WMB-100K v2.1 Score");
    println!("============================================================");
    println!();
    if let Some(a_pct) = part_a_pct {
        println!("  Part A (optional):  {}/{} ({:.0}%)", part_a_correct, part_a_total, a_pct);
    } else {
        println!("  Part A (optional):  N/A");
    }
    println!("  Part B (main):      {}/{} ({:.1}%)", part_b_correct, part_b_total, part_b_raw);
    println!("  FM Penalty:         -{:.1} ({} false positives / {} probes)", fm.penalty, fm.false_positives, fm.probes);
    println!("  Speed Penalty:      -{:.1}", speed_penalty);
    println!("  ─────────────────────────────────");
    println!("  Score:              {:.1} / 100  [{}]", total, grade(total));
    println!();
    println!("  ── S-Level Accuracy ──");
    for t in &["S1Situational", "S2MultiMemory", "S3CrossCategory", "S4Temporal",
               "S5Adversarial", "S6Contradiction", "S7ReasoningChain", "FalseMemory"] {
        if let Some((c, tot)) = by_type.get(*t) {
            let p = if *tot > 0 { *c as f64 / *tot as f64 * 100.0 } else { 0.0 };
            println!("    {:<20} {}/{} ({:.0}%)", t, c, tot, p);
        }
    }
    // Also show L1-L5 if present (backward compat)
    for t in &["L1Simple", "L2Cross", "L3TimeCross", "L4Comprehensive", "L5MultiReason"] {
        if let Some((c, tot)) = by_type.get(*t) {
            if *tot > 0 {
                let p = *c as f64 / *tot as f64 * 100.0;
                println!("    {:<20} {}/{} ({:.0}%)", t, c, tot, p);
            }
        }
    }
    println!();
    println!("  Speed: p50={}ms  p95={}ms", lat.p50_ms, lat.p95_ms);
    println!();

    // Save result
    let result = WmbResult {
        system_name: "WME".into(),
        version: "2.1".into(),
        timestamp: chrono::Utc::now().to_rfc3339(),
        mode: "benchmark".into(),
        wmb_score: total,
        max_score: MAX_SCORE,
        breakdown: ScoreBreakdown {
            s1_situational: type_score(&by_type, "S1Situational"),
            s2_multi_memory: type_score(&by_type, "S2MultiMemory"),
            s3_cross_category: type_score(&by_type, "S3CrossCategory"),
            s4_temporal: type_score(&by_type, "S4Temporal"),
            s5_adversarial: type_score(&by_type, "S5Adversarial"),
            s6_contradiction: type_score(&by_type, "S6Contradiction"),
            s7_reasoning_chain: type_score(&by_type, "S7ReasoningChain"),
            false_memory: fm.clone(),
        },
        category_scores: HashMap::new(),
        latency: lat,
        meta: Meta {
            total_turns: 0,
            total_questions: answers.len() as u32,
            total_facts: 0,
            seed: 0,
        },
    };

    let result_path = format!("{}/result.json", dataset);
    std::fs::write(&result_path, serde_json::to_string_pretty(&result)?)?;
    println!("  Result saved → {}", result_path);

    Ok(())
}

pub async fn report(dataset: &str) -> anyhow::Result<()> {
    let result: WmbResult = load_json(&format!("{}/result.json", dataset))?;

    let mut md = String::new();
    md.push_str("# WMB-100K v2.1 — Benchmark Report\n\n");
    md.push_str(&format!("**System:** {}\n", result.system_name));
    md.push_str(&format!("**Date:** {}\n", result.timestamp));
    md.push_str(&format!("**Score: {:.1} / {:.1} [{}]**\n\n", result.wmb_score, result.max_score, grade(result.wmb_score)));

    md.push_str("## S-Level Breakdown\n\n");
    md.push_str("| Type | Correct | Total | Accuracy |\n");
    md.push_str("|------|---------|-------|----------|\n");
    let b = &result.breakdown;
    md.push_str(&format!("| S1 Situational | {} | {} | {:.0}% |\n", b.s1_situational.correct, b.s1_situational.total, pct(b.s1_situational.correct, b.s1_situational.total)));
    md.push_str(&format!("| S2 MultiMemory | {} | {} | {:.0}% |\n", b.s2_multi_memory.correct, b.s2_multi_memory.total, pct(b.s2_multi_memory.correct, b.s2_multi_memory.total)));
    md.push_str(&format!("| S3 CrossCategory | {} | {} | {:.0}% |\n", b.s3_cross_category.correct, b.s3_cross_category.total, pct(b.s3_cross_category.correct, b.s3_cross_category.total)));
    md.push_str(&format!("| S4 Temporal | {} | {} | {:.0}% |\n", b.s4_temporal.correct, b.s4_temporal.total, pct(b.s4_temporal.correct, b.s4_temporal.total)));
    md.push_str(&format!("| S5 Adversarial | {} | {} | {:.0}% |\n", b.s5_adversarial.correct, b.s5_adversarial.total, pct(b.s5_adversarial.correct, b.s5_adversarial.total)));
    md.push_str(&format!("| S6 Contradiction | {} | {} | {:.0}% |\n", b.s6_contradiction.correct, b.s6_contradiction.total, pct(b.s6_contradiction.correct, b.s6_contradiction.total)));
    md.push_str(&format!("| S7 ReasoningChain | {} | {} | {:.0}% |\n", b.s7_reasoning_chain.correct, b.s7_reasoning_chain.total, pct(b.s7_reasoning_chain.correct, b.s7_reasoning_chain.total)));
    md.push_str(&format!("| False Memory | {}/{} false positives | | -{:.1} |\n", b.false_memory.false_positives, b.false_memory.probes, b.false_memory.penalty));

    md.push_str("\n## Latency\n\n");
    md.push_str(&format!("- p50: {}ms\n- p95: {}ms\n\n", result.latency.p50_ms, result.latency.p95_ms));

    let report_path = format!("{}/REPORT.md", dataset);
    std::fs::write(&report_path, &md)?;
    println!("  Report saved → {}", report_path);

    Ok(())
}

fn judge_keyword(memories: &[String], gold: &str) -> bool {
    let all_text: String = memories.iter().map(|m| m.to_lowercase()).collect::<Vec<_>>().join(" ");
    let gold_lower = gold.to_lowercase();
    let keywords: Vec<&str> = gold_lower.split_whitespace().filter(|w| w.len() > 4).collect();
    if keywords.is_empty() { return false; }
    let matched = keywords.iter().filter(|k| all_text.contains(*k)).count();
    matched as f64 / keywords.len() as f64 >= 0.4
}

fn type_score(by_type: &HashMap<String, (u32, u32)>, key: &str) -> TypeScore {
    let (c, t) = by_type.get(key).copied().unwrap_or((0, 0));
    TypeScore { correct: c, total: t, points: c as f64 * POINT_DIRECT }
}

fn pct(correct: u32, total: u32) -> f64 {
    if total > 0 { correct as f64 / total as f64 * 100.0 } else { 0.0 }
}

fn calc_latency(sorted: &[u64]) -> LatencyStats {
    if sorted.is_empty() {
        return LatencyStats { p50_ms: 0, p95_ms: 0, p99_ms: 0, mean_ms: 0 };
    }
    LatencyStats {
        p50_ms: sorted[sorted.len() / 2],
        p95_ms: sorted[std::cmp::min((sorted.len() as f64 * 0.95) as usize, sorted.len() - 1)],
        p99_ms: sorted[std::cmp::min((sorted.len() as f64 * 0.99) as usize, sorted.len() - 1)],
        mean_ms: sorted.iter().sum::<u64>() / sorted.len() as u64,
    }
}

fn load_json<T: serde::de::DeserializeOwned>(path: &str) -> anyhow::Result<T> {
    let content = std::fs::read_to_string(path)?;
    Ok(serde_json::from_str(&content)?)
}
