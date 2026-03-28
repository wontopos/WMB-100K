//! Benchmark execution: data ingestion + querying.
//! Any memory system with a REST API can be tested.

use crate::types::*;
use futures::stream::{self, StreamExt};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

const INGEST_CONCURRENCY: usize = 5;
const QUERY_CONCURRENCY: usize = 5;

/// Ingest data into a POST /api/v1/memory/store compatible API.
pub async fn ingest(url: &str, key: &str, dataset: &str, quick: bool) -> anyhow::Result<()> {
    let cats = if quick { QUICK_CATEGORIES } else { ALL_CATEGORIES };
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;
    let mut total_ingested = 0u64;
    let mut total_failed = 0u64;

    println!("=== WMB-100K Ingestion ({}x parallel) ===", INGEST_CONCURRENCY);
    println!("  Target: {}", url);

    for cat in cats {
        let path = format!("{}/{}.jsonl", dataset, cat);
        let turns = load_jsonl::<Turn>(&path)?;

        // 소비자 환경: 모든 턴을 3턴씩 묶어서 저장 (실제 서비스와 동일)
        let chunk_size = 3;
        let mut all_contents: Vec<(u64, String)> = Vec::new();

        for i in (0..turns.len()).step_by(chunk_size) {
            let end = (i + chunk_size).min(turns.len());
            let context: String = turns[i..end]
                .iter()
                .map(|t| t.text.as_str())
                .collect::<Vec<_>>()
                .join("\n");
            if !context.trim().is_empty() {
                all_contents.push((turns[i].turn_id as u64, context));
            }
        }

        println!("  {} — {} turns ({} chunks to store)", cat, turns.len(), all_contents.len());
        let start = Instant::now();
        let cat_ok = Arc::new(AtomicU64::new(0));
        let cat_fail = Arc::new(AtomicU64::new(0));

        stream::iter(all_contents.into_iter())
            .for_each_concurrent(INGEST_CONCURRENCY, |(turn_id, content)| {
                let client = client.clone();
                let url = url.to_string();
                let key = key.to_string();
                let cat = cat.to_string();
                let ok = cat_ok.clone();
                let fail = cat_fail.clone();

                async move {
                    let body = serde_json::json!({
                        "user_id": format!("wmb_{}", cat),
                        "content": content,
                        "metadata": {
                            "category": cat,
                            "turn_number": turn_id,
                            "importance": 0.7
                        }
                    });

                    let mut retries = 0;
                    loop {
                        match client
                            .post(format!("{}/api/v1/memory/store", url))
                            .header("X-API-Key", &key)
                            .json(&body)
                            .send()
                            .await
                        {
                            Ok(r) if r.status().is_success() => {
                                let n = ok.fetch_add(1, Ordering::Relaxed) + 1;
                                if n % 100 == 0 {
                                    println!("    [{}/...] ingested", n);
                                }
                                break;
                            }
                            Ok(r) if r.status().as_u16() == 429 && retries < 3 => {
                                retries += 1;
                                tokio::time::sleep(std::time::Duration::from_secs(2 * retries)).await;
                            }
                            _ => {
                                fail.fetch_add(1, Ordering::Relaxed);
                                break;
                            }
                        }
                    }
                }
            })
            .await;

        let ok = cat_ok.load(Ordering::Relaxed);
        let fl = cat_fail.load(Ordering::Relaxed);
        total_ingested += ok;
        total_failed += fl;
        println!("    {} ingested, {} failed in {:.1}s", ok, fl, start.elapsed().as_secs_f64());
    }

    println!("  Total: {} ingested, {} failed", total_ingested, total_failed);
    Ok(())
}

/// Query a POST /api/v1/memory/search compatible API.
pub async fn query(url: &str, key: &str, dataset: &str, quick: bool) -> anyhow::Result<()> {
    let cats = if quick { QUICK_CATEGORIES } else { ALL_CATEGORIES };
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;
    let mut all_answers: Vec<Answer> = Vec::new();

    println!("\n=== WMB-100K Query ({}x parallel) ===", QUERY_CONCURRENCY);

    for cat in cats {
        let q_path = format!("{}/{}_questions.json", dataset, cat);
        let questions = load_json::<Vec<Question>>(&q_path)?;

        println!("  {} — {} questions", cat, questions.len());

        let results: Vec<Answer> = stream::iter(questions.iter())
            .map(|q| {
                let client = client.clone();
                let url = url.to_string();
                let key = key.to_string();
                let cat = cat.to_string();
                let q = q.clone();

                async move {
                    let body = serde_json::json!({
                        "user_id": format!("wmb_{}", cat),
                        "query": q.text,
                        "max_results": 10
                    });

                    let start = Instant::now();
                    let resp = client
                        .post(format!("{}/api/v1/memory/search", url))
                        .header("X-API-Key", &key)
                        .json(&body)
                        .send()
                        .await;

                    let latency = start.elapsed().as_millis() as u64;

                    let (response, memories) = match resp {
                        Ok(r) if r.status().is_success() => {
                            let body: serde_json::Value = r.json().await.unwrap_or_default();
                            let mems: Vec<String> = body["memories"]
                                .as_array()
                                .map(|arr| {
                                    arr.iter()
                                        .filter_map(|m| m["content"].as_str().map(String::from))
                                        .collect()
                                })
                                .unwrap_or_default();
                            let top = mems.first().cloned().unwrap_or("NO_RESULT".into());
                            (top, mems)
                        }
                        _ => ("ERROR".into(), vec![]),
                    };

                    Answer {
                        question_id: q.id.clone(),
                        system_response: response,
                        memories_returned: memories,
                        latency_ms: latency,
                    }
                }
            })
            .buffer_unordered(QUERY_CONCURRENCY)
            .collect()
            .await;

        all_answers.extend(results);
    }

    // Save results
    let answers_path = format!("{}/answers.json", dataset);
    std::fs::write(&answers_path, serde_json::to_string_pretty(&all_answers)?)?;
    println!("\n  {} answers saved → {}", all_answers.len(), answers_path);

    Ok(())
}

fn load_jsonl<T: serde::de::DeserializeOwned>(path: &str) -> anyhow::Result<Vec<T>> {
    let content = std::fs::read_to_string(path)?;
    Ok(content
        .lines()
        .filter(|l| !l.trim().is_empty())
        .filter_map(|l| serde_json::from_str(l).ok())
        .collect())
}

fn load_json<T: serde::de::DeserializeOwned>(path: &str) -> anyhow::Result<T> {
    let content = std::fs::read_to_string(path)?;
    Ok(serde_json::from_str(&content)?)
}
