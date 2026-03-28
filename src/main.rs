//! WMB-100K — Wontopos Memory Benchmark v1.0
//!
//! The first 100,000-turn benchmark for AI memory systems.
//! Tests storage accuracy, retrieval precision, false memory defense,
//! and update tracking across 10 life categories.
//!
//! Usage:
//!   wmb generate                    # Generate full dataset (10 cats × 10K turns)
//!   wmb generate --quick            # Quick dataset (3 cats × 1K turns)
//!   wmb ingest --url <URL> --key <KEY>  # Feed into memory system
//!   wmb query --url <URL> --key <KEY>   # Run questions
//!   wmb score                       # Score results
//!   wmb report                      # Markdown report

mod types;
mod categories;
mod generator;
mod runner;
mod scorer;

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "wmb-100k", about = "WMB-100K — Wontopos Memory Benchmark v1.0", version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Generate benchmark dataset
    Generate {
        #[arg(long)]
        quick: bool,
        #[arg(long, default_value = "datasets")]
        output: String,
    },
    /// Ingest dataset into target memory system
    Ingest {
        #[arg(long, env = "MEMORY_API_URL")]
        url: String,
        #[arg(long, env = "MEMORY_API_KEY")]
        key: String,
        #[arg(long, default_value = "datasets")]
        dataset: String,
        #[arg(long)]
        quick: bool,
    },
    /// Run questions against memory system
    Query {
        #[arg(long, env = "MEMORY_API_URL")]
        url: String,
        #[arg(long, env = "MEMORY_API_KEY")]
        key: String,
        #[arg(long, default_value = "datasets")]
        dataset: String,
        #[arg(long)]
        quick: bool,
    },
    /// Score results
    Score {
        #[arg(long, default_value = "datasets")]
        dataset: String,
    },
    /// Generate markdown report
    Report {
        #[arg(long, default_value = "datasets")]
        dataset: String,
    },
    /// Full run: generate → ingest → query → score → report
    Run {
        #[arg(long, env = "MEMORY_API_URL")]
        url: String,
        #[arg(long, env = "MEMORY_API_KEY")]
        key: String,
        #[arg(long)]
        quick: bool,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    dotenvy::dotenv().ok();
    let cli = Cli::parse();

    match cli.command {
        Commands::Generate { quick, output } => {
            generator::generate(quick, &output).await?;
        }
        Commands::Ingest { url, key, dataset, quick } => {
            runner::ingest(&url, &key, &dataset, quick).await?;
        }
        Commands::Query { url, key, dataset, quick } => {
            runner::query(&url, &key, &dataset, quick).await?;
        }
        Commands::Score { dataset } => {
            scorer::score(&dataset).await?;
        }
        Commands::Report { dataset } => {
            scorer::report(&dataset).await?;
        }
        Commands::Run { url, key, quick } => {
            let d = "datasets";
            generator::generate(quick, d).await?;
            runner::ingest(&url, &key, d, quick).await?;
            runner::query(&url, &key, d, quick).await?;
            scorer::score(d).await?;
            scorer::report(d).await?;
        }
    }
    Ok(())
}
