use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// === Categories ===

pub const ALL_CATEGORIES: &[&str] = &[
    "daily_life", "relationships", "work_career", "health_fitness",
    "travel_places", "media_taste", "finance_goals", "education_skills",
    "pets_hobbies", "beliefs_values",
];

pub const QUICK_CATEGORIES: &[&str] = &["daily_life", "work_career", "relationships"];

pub const FULL_TURNS: u32 = 10_000;
pub const QUICK_TURNS: u32 = 1_000;
pub const FACTS_PER_CATEGORY: usize = 100;
pub const FALSE_PROBES_PER_CATEGORY: usize = 40;

// === Dataset Types ===

/// One conversation turn.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Turn {
    pub turn_id: u32,
    pub category: String,
    pub speaker: String,
    pub text: String,
    #[serde(default)]
    pub embedded_facts: Vec<String>,
    #[serde(default)]
    pub fact_type: Option<String>,
}

/// A fact definition (ground truth).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Fact {
    pub id: String,
    pub category: String,
    pub content: String,
    pub natural_text: String,        // how it appears in conversation
    pub target_turn: u32,
    pub importance: f64,
    pub keywords: Vec<String>,       // for question generation
    pub update_chain: Option<String>,
    pub update_order: Option<u32>,
}

/// A benchmark question.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Question {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub category: String,
    #[serde(default)]
    pub category2: Option<String>,
    #[serde(default)]
    pub qtype: QuestionType,
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub gold_answer: String,
    #[serde(default)]
    pub required_memories: Vec<String>,
    #[serde(default)]
    pub gold_fact_ids: Vec<String>,
    #[serde(default)]
    pub gold_turn_ids: Vec<u32>,
    #[serde(default)]
    pub points: f64,
    #[serde(default)]
    pub false_penalty: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub enum QuestionType {
    // v2.1 types
    #[default]
    S1Situational,
    S2MultiMemory,
    S3CrossCategory,
    S4Temporal,
    S5Adversarial,
    S6Contradiction,
    S7ReasoningChain,
    FalseMemory,
    // v1 aliases (backward compat)
    #[serde(alias = "DirectRecall")]
    L1Simple,
    #[serde(alias = "IndirectRecall")]
    L2Cross,
    #[serde(alias = "TemporalRecall")]
    L3TimeCross,
    #[serde(alias = "UpdateRecall")]
    L4Comprehensive,
    L5MultiReason,
}

/// Answer from a memory system.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Answer {
    pub question_id: String,
    pub system_response: String,
    pub memories_returned: Vec<String>,
    pub latency_ms: u64,
}

/// Final benchmark result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WmbResult {
    pub system_name: String,
    pub version: String,
    pub timestamp: String,
    pub mode: String,  // "full" or "quick"
    pub wmb_score: f64,
    pub max_score: f64,
    pub breakdown: ScoreBreakdown,
    pub category_scores: HashMap<String, CategoryScore>,
    pub latency: LatencyStats,
    pub meta: Meta,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreBreakdown {
    pub s1_situational: TypeScore,
    pub s2_multi_memory: TypeScore,
    pub s3_cross_category: TypeScore,
    pub s4_temporal: TypeScore,
    pub s5_adversarial: TypeScore,
    pub s6_contradiction: TypeScore,
    pub s7_reasoning_chain: TypeScore,
    pub false_memory: FalseMemoryScore,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeScore {
    pub correct: u32,
    pub total: u32,
    pub points: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FalseMemoryScore {
    pub probes: u32,
    pub false_positives: u32,
    pub penalty: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CategoryScore {
    pub earned: f64,
    pub possible: f64,
    pub pct: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LatencyStats {
    pub p50_ms: u64,
    pub p95_ms: u64,
    pub p99_ms: u64,
    pub mean_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meta {
    pub total_turns: u64,
    pub total_questions: u32,
    pub total_facts: u32,
    pub seed: u64,
}

/// WMB-100K grade from score (100 max).
pub fn grade(score: f64) -> &'static str {
    if score >= 90.0 { "Exceptional" }
    else if score >= 80.0 { "Excellent" }
    else if score >= 70.0 { "Good" }
    else if score >= 60.0 { "Fair" }
    else if score >= 50.0 { "Below Average" }
    else { "Failing" }
}
