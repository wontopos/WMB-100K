//! 100 fact definitions across 10 categories.
//! Each category: 100 facts x ~500 tokens context = ~50K tokens
//! 10 categories = ~500K tokens of facts
//! + conversation noise (~1.5M tokens) = ~2M total per category

mod daily_life;
mod relationships;
mod work_career;
mod health_fitness;
mod travel_places;
mod media_taste;
mod finance_goals;
mod education_skills;
mod pets_hobbies;
mod beliefs_values;

use crate::types::{Fact, Question, QuestionType};

/// Get all 100 facts for a category.
pub fn get_facts(category: &str) -> Vec<Fact> {
    match category {
        "daily_life" => daily_life::facts(),
        "relationships" => relationships::facts(),
        "work_career" => work_career::facts(),
        "health_fitness" => health_fitness::facts(),
        "travel_places" => travel_places::facts(),
        "media_taste" => media_taste::facts(),
        "finance_goals" => finance_goals::facts(),
        "education_skills" => education_skills::facts(),
        "pets_hobbies" => pets_hobbies::facts(),
        "beliefs_values" => beliefs_values::facts(),
        _ => vec![],
    }
}

/// Get false memory probes for a category.
pub fn get_false_probes(category: &str) -> Vec<Question> {
    match category {
        "daily_life" => daily_life::false_probes(),
        "relationships" => relationships::false_probes(),
        "work_career" => work_career::false_probes(),
        "health_fitness" => health_fitness::false_probes(),
        "travel_places" => travel_places::false_probes(),
        "media_taste" => media_taste::false_probes(),
        "finance_goals" => finance_goals::false_probes(),
        "education_skills" => education_skills::false_probes(),
        "pets_hobbies" => pets_hobbies::false_probes(),
        "beliefs_values" => beliefs_values::false_probes(),
        _ => vec![],
    }
}

/// Helper to create a fact.
pub fn fact(id: &str, cat: &str, content: &str, natural: &str, turn: u32, imp: f64, kw: &[&str]) -> Fact {
    Fact {
        id: id.into(),
        category: cat.into(),
        content: content.into(),
        natural_text: natural.into(),
        target_turn: turn,
        importance: imp,
        keywords: kw.iter().map(|s| s.to_string()).collect(),
        update_chain: None,
        update_order: None,
    }
}

/// Helper to create an update fact (part of a chain).
pub fn update(id: &str, cat: &str, content: &str, natural: &str, turn: u32, imp: f64, kw: &[&str], chain: &str, order: u32) -> Fact {
    Fact {
        id: id.into(),
        category: cat.into(),
        content: content.into(),
        natural_text: natural.into(),
        target_turn: turn,
        importance: imp,
        keywords: kw.iter().map(|s| s.to_string()).collect(),
        update_chain: Some(chain.into()),
        update_order: Some(order),
    }
}

/// Helper to create a false memory probe.
pub fn false_probe(id: &str, cat: &str, question: &str) -> Question {
    Question {
        id: id.into(),
        category: cat.into(),
        qtype: QuestionType::FalseMemory,
        text: question.into(),
        gold_answer: "NOT_MENTIONED".into(),
        gold_fact_ids: vec![],
        points: 0.0,
        false_penalty: -2.5,
        category2: None,
        required_memories: vec![],
        gold_turn_ids: vec![],
    }
}
