//! WMB-100K dataset generation: natural conversation generation via Haiku, fact insertion, question generation.

use crate::categories;
use crate::types::*;
use rand::Rng;
use std::collections::HashMap;

const BATCH_SIZE: u32 = 50; // Call Haiku 50 turns at a time

pub async fn generate(quick: bool, output_dir: &str) -> anyhow::Result<()> {
    std::fs::create_dir_all(output_dir)?;

    let cats = if quick { QUICK_CATEGORIES } else { ALL_CATEGORIES };
    let turns_count = if quick { QUICK_TURNS } else { FULL_TURNS };

    let api_key = std::env::var("ANTHROPIC_API_KEY").ok();
    let use_haiku = api_key.is_some();

    println!("=== WMB-100K Dataset Generation ===");
    println!("  Mode: {}", if quick { "quick" } else { "full" });
    println!("  Engine: {}", if use_haiku { "Haiku 4.5" } else { "synthetic (no API key)" });
    println!("  Categories: {}", cats.len());
    println!("  Turns per category: {}", turns_count);
    println!();

    let http = reqwest::Client::new();

    // Generate 10 categories in parallel (Tier 4: 4,000 requests/min)
    let mut handles = Vec::new();

    for cat in cats {
        let cat = cat.to_string();
        let api_key = api_key.clone();
        let http = http.clone();
        let output_dir = output_dir.to_string();

        let handle = tokio::spawn(async move {
            println!("  [{}] Starting...", cat);

            let facts = categories::get_facts(&cat);
            let false_probes = categories::get_false_probes(&cat);

            // Skip if already completed
            let turns_path = format!("{}/{}.jsonl", output_dir, cat);
            let expected_lines = if turns_count <= QUICK_TURNS { QUICK_TURNS } else { FULL_TURNS };
            if let Ok(content) = std::fs::read_to_string(&turns_path) {
                let lines = content.lines().count() as u32;
                if lines >= expected_lines {
                    println!("  [{}] Already complete ({} turns), skipping", cat, lines);
                    let mut questions = generate_questions(&cat, &facts);
                    questions.extend(false_probes);
                    return Ok::<(String, Vec<Question>), anyhow::Error>((cat, questions));
                }
            }

            let turns = if let Some(ref key) = api_key {
                generate_with_haiku(&cat, &facts, turns_count, key, &http).await?
            } else {
                generate_synthetic(&cat, &facts, turns_count)
            };

            save_jsonl(&turns, &turns_path)?;

            let mut questions = generate_questions(&cat, &facts);
            questions.extend(false_probes);
            let q_path = format!("{}/{}_questions.json", output_dir, cat);
            save_json(&questions, &q_path)?;

            println!("  [{}] Done: {} turns, {} questions", cat, turns.len(), questions.len());

            Ok((cat, questions))
        });

        handles.push(handle);
    }

    // Collect results
    let mut all_questions: Vec<Question> = Vec::new();
    for handle in handles {
        match handle.await {
            Ok(Ok((_cat, questions))) => {
                all_questions.extend(questions);
            }
            Ok(Err(e)) => {
                eprintln!("  ⚠ Category failed: {}", e);
            }
            Err(e) => {
                eprintln!("  ⚠ Task panicked: {}", e);
            }
        }
    }

    let all_q_path = format!("{}/all_questions.json", output_dir);
    save_json(&all_questions, &all_q_path)?;

    let meta = serde_json::json!({
        "version": "1.0.0",
        "mode": if quick { "quick" } else { "full" },
        "engine": if use_haiku { "haiku-4.5" } else { "synthetic" },
        "categories": cats,
        "turns_per_category": turns_count,
        "total_turns": cats.len() as u32 * turns_count,
        "total_questions": all_questions.len(),
        "total_facts": cats.iter().map(|c| categories::get_facts(c).len()).sum::<usize>(),
        "generated_at": chrono::Utc::now().to_rfc3339(),
    });
    std::fs::write(format!("{}/meta.json", output_dir), serde_json::to_string_pretty(&meta)?)?;

    println!("\n✅ Dataset complete: {} questions, {} turns",
        all_questions.len(), cats.len() as u32 * turns_count);
    Ok(())
}

/// Generate natural conversation using Haiku.
async fn generate_with_haiku(
    cat: &str,
    facts: &[Fact],
    total: u32,
    api_key: &str,
    http: &reqwest::Client,
) -> anyhow::Result<Vec<Turn>> {
    let mut turns = Vec::new();
    let mut fact_map: HashMap<u32, Vec<&Fact>> = HashMap::new();

    for f in facts {
        let turn = if total < FULL_TURNS {
            ((f.target_turn as f64 * total as f64 / FULL_TURNS as f64) as u32).max(1)
        } else {
            f.target_turn
        };
        fact_map.entry(turn).or_default().push(f);
    }

    let category_desc = category_description(cat);
    let mut current_turn = 1u32;

    while current_turn <= total {
        // Check for turns with facts in this batch
        let batch_end = (current_turn + BATCH_SIZE - 1).min(total);
        let mut batch_facts: Vec<(&Fact, u32)> = Vec::new();
        for t in current_turn..=batch_end {
            if let Some(fl) = fact_map.get(&t) {
                for f in fl {
                    batch_facts.push((f, t));
                }
            }
        }

        // Generate conversation via Haiku
        let batch_turns = call_haiku_batch(
            cat, &category_desc, current_turn, batch_end, &batch_facts,
            &turns, api_key, http
        ).await?;

        turns.extend(batch_turns);
        current_turn = batch_end + 1;

        // Progress update
        if current_turn % 200 == 1 || current_turn > total {
            println!("    {}/{} turns", turns.len(), total);
        }
    }

    Ok(turns)
}

async fn call_haiku_batch(
    cat: &str,
    cat_desc: &str,
    from: u32,
    to: u32,
    facts: &[(&Fact, u32)],
    prev_turns: &[Turn],
    api_key: &str,
    http: &reqwest::Client,
) -> anyhow::Result<Vec<Turn>> {
    let count = to - from + 1;

    // Use last 5 turns as context
    let context: String = prev_turns.iter().rev().take(5).rev()
        .map(|t| format!("{}: {}", t.speaker, t.text))
        .collect::<Vec<_>>()
        .join("\n");

    // Fact insertion instructions
    let fact_instructions = if facts.is_empty() {
        String::new()
    } else {
        let mut s = String::from("\n\nIMPORTANT: Naturally weave these facts into the conversation at the specified turns:\n");
        for (f, turn) in facts {
            s.push_str(&format!("  Turn {}: \"{}\" (say it naturally, don't state it as a fact)\n", turn, f.natural_text));
        }
        s
    };

    let system = format!(
        "You generate realistic casual conversations between a user and an AI assistant.\n\
         Topic area: {} ({})\n\
         Generate exactly {} turns of natural dialogue.\n\
         Each turn is one message from either 'user' or 'assistant'.\n\
         Make the conversation feel real — include small talk, reactions, follow-ups.\n\
         Alternate between user and assistant. Start with user.\n\
         Output ONLY a JSON array: [{{\"speaker\":\"user\",\"text\":\"...\"}}, ...]\n\
         No markdown, no explanation, just the JSON array.{}",
        cat, cat_desc, count, fact_instructions
    );

    let user_msg = if context.is_empty() {
        "Start a new conversation.".to_string()
    } else {
        format!("Continue from:\n{}\n\nGenerate the next {} turns.", context, count)
    };

    let body = serde_json::json!({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4096,
        "temperature": 0.8,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}]
    });

    // Retry logic
    let mut last_err = String::new();
    for attempt in 0..3u32 {
        if attempt > 0 {
            tokio::time::sleep(std::time::Duration::from_secs(2u64.pow(attempt))).await;
        }

        let resp = http.post("https://api.anthropic.com/v1/messages")
            .header("x-api-key", api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .await;

        match resp {
            Ok(r) if r.status().is_success() => {
                let resp_body: serde_json::Value = r.json().await?;
                let text = resp_body["content"][0]["text"].as_str().unwrap_or("[]");

                // JSON parsing (remove markdown wrapping)
                let clean = text.trim()
                    .trim_start_matches("```json")
                    .trim_start_matches("```")
                    .trim_end_matches("```")
                    .trim();

                let batch: Vec<serde_json::Value> = serde_json::from_str(clean)
                    .unwrap_or_else(|_| Vec::new());

                let mut result = Vec::new();
                for (i, item) in batch.iter().enumerate() {
                    let turn_id = from + i as u32;
                    let speaker = item["speaker"].as_str().unwrap_or("user").to_string();
                    let text = item["text"].as_str().unwrap_or("").to_string();

                    // Check if this turn has facts
                    let embedded: Vec<String> = facts.iter()
                        .filter(|(_, ft)| *ft == turn_id)
                        .map(|(f, _)| f.id.clone())
                        .collect();

                    let fact_type = if !embedded.is_empty() {
                        Some("initial".into())
                    } else {
                        None
                    };

                    result.push(Turn {
                        turn_id,
                        category: cat.into(),
                        speaker,
                        text,
                        embedded_facts: embedded,
                        fact_type,
                    });
                }

                // Fill remaining turns with padding
                while result.len() < count as usize {
                    let t = from + result.len() as u32;
                    result.push(Turn {
                        turn_id: t,
                        category: cat.into(),
                        speaker: if result.len() % 2 == 0 { "user" } else { "assistant" }.into(),
                        text: "Hmm, yeah.".into(),
                        embedded_facts: vec![],
                        fact_type: None,
                    });
                }

                return Ok(result);
            }
            Ok(r) => {
                let status = r.status();
                let body = r.text().await.unwrap_or_default();
                last_err = format!("{}: {}", status, &body[..body.len().min(200)]);
                if status.as_u16() == 429 {
                    tokio::time::sleep(std::time::Duration::from_secs(5)).await;
                }
            }
            Err(e) => {
                last_err = e.to_string();
            }
        }
    }

    // Fall back to synthetic after 3 failures
    eprintln!("    ⚠ Haiku failed for turns {}-{}: {}. Using synthetic.", from, to, last_err);
    Ok(synthetic_batch(cat, from, to, facts))
}

fn synthetic_batch(cat: &str, from: u32, to: u32, facts: &[(&Fact, u32)]) -> Vec<Turn> {
    let mut rng = rand::thread_rng();
    let noise = [
        "Had a pretty normal day.", "Nothing much going on.", "Just chilling.",
        "Been busy with stuff.", "Same old same old.", "You know how it is.",
        "Can't complain really.", "Just thinking about things.", "Feeling okay I guess.",
        "Not much to report today.",
    ];
    let mut result = Vec::new();
    for t in from..=to {
        let fact_at_turn: Vec<&&Fact> = facts.iter().filter(|(_, ft)| *ft == t).map(|(f, _)| f).collect();
        if let Some(f) = fact_at_turn.first() {
            result.push(Turn {
                turn_id: t, category: cat.into(), speaker: "user".into(),
                text: f.natural_text.clone(),
                embedded_facts: vec![f.id.clone()],
                fact_type: Some("initial".into()),
            });
        } else {
            result.push(Turn {
                turn_id: t, category: cat.into(),
                speaker: if t % 2 == 1 { "user" } else { "assistant" }.into(),
                text: noise[rng.gen_range(0..noise.len())].into(),
                embedded_facts: vec![], fact_type: None,
            });
        }
    }
    result
}

fn generate_synthetic(cat: &str, facts: &[Fact], total: u32) -> Vec<Turn> {
    let empty_facts: Vec<(&Fact, u32)> = Vec::new();
    let mut all = Vec::new();
    let mut fact_map: HashMap<u32, Vec<&Fact>> = HashMap::new();
    for f in facts {
        let turn = if total < FULL_TURNS {
            ((f.target_turn as f64 * total as f64 / FULL_TURNS as f64) as u32).max(1)
        } else { f.target_turn };
        fact_map.entry(turn).or_default().push(f);
    }

    let mut from = 1u32;
    while from <= total {
        let to = (from + BATCH_SIZE - 1).min(total);
        let batch_facts: Vec<(&Fact, u32)> = (from..=to)
            .flat_map(|t| fact_map.get(&t).into_iter().flatten().map(move |f| (*f, t)))
            .collect();
        all.extend(synthetic_batch(cat, from, to, &batch_facts));
        from = to + 1;
    }
    all
}

fn generate_questions(cat: &str, facts: &[Fact]) -> Vec<Question> {
    let mut questions = Vec::new();
    let mut l1_count = 0;
    let mut l2_count = 0;
    let mut l3_count = 0;
    let mut l4_count = 0;
    let mut l5_count = 0;

    // L1: Simple recall (all facts)
    for fact in facts {
        l1_count += 1;
        questions.push(Question {
            id: format!("{}.L1.{:03}", cat, l1_count),
            category: cat.into(), qtype: QuestionType::L1Simple,
            text: make_direct_q(fact), gold_answer: fact.content.clone(),
            gold_fact_ids: vec![fact.id.clone()], points: 0.1, false_penalty: 0.0,
            category2: None, required_memories: vec![], gold_turn_ids: vec![],
        });
    }

    // L2: Cross-search (must connect 2 facts to answer)
    for pair in facts.windows(2) {
        let a = &pair[0];
        let b = &pair[1];
        // Generate cross-question if related keywords overlap within the same category
        let shared = a.keywords.iter().any(|k| b.keywords.iter().any(|bk| k == bk));
        if shared || (a.target_turn as i32 - b.target_turn as i32).abs() < 200 {
            l2_count += 1;
            questions.push(Question {
                id: format!("{}.L2.{:03}", cat, l2_count),
                category: cat.into(), qtype: QuestionType::L2Cross,
                text: make_cross_q(a, b),
                gold_answer: format!("{} AND {}", a.content, b.content),
                gold_fact_ids: vec![a.id.clone(), b.id.clone()],
                points: 0.1, false_penalty: 0.0,
                category2: None, required_memories: vec![], gold_turn_ids: vec![],
            });
            if l2_count >= 20 { break; }
        }
    }

    // L3: Time+Cross (time-related facts)
    for fact in facts {
        if fact.keywords.iter().any(|k| {
            ["month","january","february","march","april","may","june",
             "july","august","september","october","november","december",
             "year","week"].iter().any(|m| k.contains(m))
        }) || fact.content.to_lowercase().contains("in ") {
            l3_count += 1;
            questions.push(Question {
                id: format!("{}.L3.{:03}", cat, l3_count),
                category: cat.into(), qtype: QuestionType::L3TimeCross,
                text: make_temporal_q(fact), gold_answer: fact.content.clone(),
                gold_fact_ids: vec![fact.id.clone()], points: 0.1, false_penalty: 0.0,
                category2: None, required_memories: vec![], gold_turn_ids: vec![],
            });
        }
    }

    // L4: Comprehensive (update chain -- must find both previous+current)
    for fact in facts {
        if fact.update_order.unwrap_or(0) > 1 {
            // Find previous version
            let chain = fact.update_chain.as_ref().unwrap();
            let prev: Vec<&Fact> = facts.iter()
                .filter(|f| f.update_chain.as_ref() == Some(chain) && f.update_order < fact.update_order)
                .collect();

            let mut all_ids: Vec<String> = prev.iter().map(|f| f.id.clone()).collect();
            all_ids.push(fact.id.clone());

            let prev_content: Vec<String> = prev.iter().map(|f| f.content.clone()).collect();

            l4_count += 1;
            questions.push(Question {
                id: format!("{}.L4.{:03}", cat, l4_count),
                category: cat.into(), qtype: QuestionType::L4Comprehensive,
                text: make_update_q(fact),
                gold_answer: format!("Current: {}. Previous: {}", fact.content, prev_content.join(", ")),
                gold_fact_ids: all_ids,
                points: 0.1, false_penalty: 0.0,
                category2: None, required_memories: vec![], gold_turn_ids: vec![],
            });
        }
    }

    // L5: Multi-reasoning (must synthesize 3+ facts to answer)
    if facts.len() >= 5 {
        // Combine early + middle + late facts
        let early = &facts[0..facts.len()/3];
        let mid = &facts[facts.len()/3..facts.len()*2/3];
        let late = &facts[facts.len()*2/3..];

        for (i, (e, (m, l))) in early.iter().zip(mid.iter().zip(late.iter())).enumerate() {
            if i >= 10 { break; }
            l5_count += 1;
            questions.push(Question {
                id: format!("{}.L5.{:03}", cat, l5_count),
                category: cat.into(), qtype: QuestionType::L5MultiReason,
                text: make_multi_q(e, m, l),
                gold_answer: format!("{} + {} + {}", e.content, m.content, l.content),
                gold_fact_ids: vec![e.id.clone(), m.id.clone(), l.id.clone()],
                points: 0.1, false_penalty: 0.0,
                category2: None, required_memories: vec![], gold_turn_ids: vec![],
            });
        }
    }

    questions
}

fn make_direct_q(f: &Fact) -> String {
    let kw = f.keywords.first().map(|s| s.as_str()).unwrap_or("this topic");
    format!("What do you know about the user's {}?", kw)
}
fn make_cross_q(a: &Fact, b: &Fact) -> String {
    let kw_a = a.keywords.first().map(|s| s.as_str()).unwrap_or("first topic");
    let kw_b = b.keywords.first().map(|s| s.as_str()).unwrap_or("second topic");
    format!("How does the user's {} relate to their {}?", kw_a, kw_b)
}
fn make_temporal_q(f: &Fact) -> String {
    let kw = f.keywords.first().map(|s| s.as_str()).unwrap_or("event");
    format!("When did the user's {} happen?", kw)
}
fn make_update_q(f: &Fact) -> String {
    let kw = f.keywords.first().map(|s| s.as_str()).unwrap_or("situation");
    format!("What is the current status of the user's {}? Has it changed from before?", kw)
}
fn make_multi_q(a: &Fact, b: &Fact, c: &Fact) -> String {
    let kw_a = a.keywords.first().map(|s| s.as_str()).unwrap_or("early");
    let kw_b = b.keywords.first().map(|s| s.as_str()).unwrap_or("middle");
    let kw_c = c.keywords.first().map(|s| s.as_str()).unwrap_or("recent");
    format!("Considering the user's {}, {}, and {}, what can you tell me about how these connect?", kw_a, kw_b, kw_c)
}

fn category_description(cat: &str) -> &'static str {
    match cat {
        "daily_life" => "morning routines, meals, commuting, apartment life, household chores, sleep habits",
        "relationships" => "family, friends, romantic partner, coworkers, social events, conflicts and resolutions",
        "work_career" => "startup life, design work, team dynamics, promotions, company milestones, career decisions",
        "health_fitness" => "exercise routines, injuries, doctor visits, mental health, diet changes, fitness goals",
        "travel_places" => "trips, restaurants, neighborhoods, moving, dream destinations, commute experiences",
        "media_taste" => "movies, books, music, TV shows, games, podcasts, concerts, streaming habits",
        "finance_goals" => "savings, loans, rent, investments, budgeting, financial milestones, spending habits",
        "education_skills" => "language learning, online courses, certifications, career development, study habits",
        "pets_hobbies" => "photography, cooking, climbing, vinyl collecting, cat care, creative hobbies",
        "beliefs_values" => "philosophy, politics, relationships views, life goals, meditation, personal growth",
        _ => "everyday life topics",
    }
}

fn save_jsonl<T: serde::Serialize>(items: &[T], path: &str) -> anyhow::Result<()> {
    let mut content = String::new();
    for item in items { content.push_str(&serde_json::to_string(item)?); content.push('\n'); }
    std::fs::write(path, content)?; Ok(())
}
fn save_json<T: serde::Serialize>(items: &[T], path: &str) -> anyhow::Result<()> {
    std::fs::write(path, serde_json::to_string_pretty(items)?)?; Ok(())
}
