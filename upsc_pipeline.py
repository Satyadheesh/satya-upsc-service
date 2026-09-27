import os
import json
import logging
from huggingface_hub import hf_hub_download
from llama_cpp import Llama
import libsql_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION ---
MODEL_REPO = "Qwen/Qwen2.5-7B-Instruct-GGUF"
MODEL_FILENAME = "qwen2.5-7b-instruct-q4_k_m.gguf"
MODEL_DIR = os.path.join(os.getcwd(), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Main DB
MAIN_DB_URL = os.environ.get("SATYA_DB_URL")
MAIN_DB_TOKEN = os.environ.get("SATYA_DB_TOKEN")
# UPSC DB
UPSC_DB_URL = os.environ.get("SATYA_UPSC_DB_URL")
UPSC_DB_TOKEN = os.environ.get("SATYA_UPSC_DB_TOKEN")

BATCH_SIZE = 10

SYSTEM_PROMPT = """You are a master UPSC Civil Services Examination coach.
Analyze the provided Indian news article and extract relevant facts for a UPSC aspirant.

If the article is NOT relevant to UPSC (e.g. gossip, sports, minor local crime, entertainment), you MUST return EXACTLY this JSON:
{"relevant": false}

If the article IS relevant to UPSC (e.g. economy, polity, environment, IR, governance, science), return EXACTLY this JSON:
{
  "relevant": true,
  "gs_paper": "GS1" | "GS2" | "GS3" | "GS4" | "Prelims facts",
  "topic": "Economy" | "Polity" | "IR" | "Environment" | etc (keep it to 1-2 words),
  "fact_box": "A concise 1-2 sentence summary of the core hard facts/data (e.g., 'FIIs withdrew ₹18,531 crore this month...').",
  "relevance_tags": ["tag1", "tag2"]
}

Respond ONLY with valid JSON. Do not include markdown formatting or extra text."""

def download_model():
    model_path = os.path.join(MODEL_DIR, MODEL_FILENAME)
    if not os.path.exists(model_path):
        logging.info(f"Downloading model {MODEL_FILENAME} (approx 4.9GB)... This may take a while.")
        hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILENAME, local_dir=MODEL_DIR)
        logging.info("Download complete.")
    else:
        logging.info("Model already exists locally.")
    return model_path

def main():
    if not MAIN_DB_URL or not UPSC_DB_URL:
        logging.error("Missing database environment variables.")
        return

    # Initialize Clients
    main_client = libsql_client.create_client_sync(url=MAIN_DB_URL, auth_token=MAIN_DB_TOKEN)
    upsc_client = libsql_client.create_client_sync(url=UPSC_DB_URL, auth_token=UPSC_DB_TOKEN)

    # 1. Get the last processed article ID
    res = upsc_client.execute("SELECT last_article_id FROM upsc_checkpoint WHERE id = 1")
    last_id = res.rows[0][0] if res.rows else 0
    logging.info(f"Starting processing from article ID > {last_id}")

    # 2. Fetch new batch of processed articles from Main DB
    # We only care about articles that have gone through the pipeline and have a title and category
    res = main_client.execute(
        "SELECT id, title, rephrased_article, category FROM articles WHERE id > ? AND status IN ('classified', 'entity_processed', 'processed') ORDER BY id ASC LIMIT ?",
        [last_id, BATCH_SIZE]
    )
    articles = res.rows
    if not articles:
        logging.info("No new articles to process.")
        return

    logging.info(f"Fetched {len(articles)} new articles to process.")

    # 3. Load Model
    model_path = download_model()
    logging.info("Loading Qwen-2.5-7B-Instruct...")
    llm = Llama(
        model_path=model_path,
        n_ctx=4096,
        n_gpu_layers=-1, # Use all available GPU layers (Metal on Mac)
        verbose=False
    )

    # 4. Process each article
    highest_id = last_id
    processed_count = 0

    for row in articles:
        article_id = int(row[0])
        title = row[1]
        content = row[2] or ""  # It's actually a BLOB in DB, but let's assume it's small enough or just use the title for now if it's too complex to decompress.
        category = row[3]
        
        # NOTE: the content in the DB is zlib compressed. We can decompress it, or just use the title and category for testing.
        # Let's import zlib and decompress it.
        import zlib
        try:
            if isinstance(content, bytes):
                text_content = zlib.decompress(content).decode('utf-8')
            else:
                text_content = str(content)
        except Exception:
            text_content = str(content)

        prompt = f"Article Title: {title}\nCategory: {category}\nContent: {text_content[:2000]}\n\nAnalyze the above article."
        
        logging.info(f"Processing Article {article_id}: {title[:50]}...")
        
        try:
            response = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.1,
                max_tokens=250
            )
            
            output_str = response['choices'][0]['message']['content'].strip()
            data = json.loads(output_str)
            
            if data.get("relevant"):
                # Insert into UPSC DB
                gs_paper = data.get("gs_paper", "Prelims facts")
                topic = data.get("topic", "Current Affairs")
                fact_box = data.get("fact_box", "")
                tags = json.dumps(data.get("relevance_tags", []))
                
                upsc_client.execute(
                    "INSERT INTO upsc_articles (article_id, gs_paper, topic, fact_box, relevance_tags, created_at) VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))",
                    [article_id, gs_paper, topic, fact_box, tags]
                )
                logging.info(f"  [+] Saved as {gs_paper} - {topic}")
            else:
                logging.info(f"  [-] Skipped (Not relevant to UPSC)")
                
        except Exception as e:
            logging.error(f"  [!] Failed to process article {article_id}: {e}")
        
        highest_id = max(highest_id, article_id)
        processed_count += 1

    # 5. Update Checkpoint
    upsc_client.execute("UPDATE upsc_checkpoint SET last_article_id = ? WHERE id = 1", [highest_id])
    logging.info(f"Batch complete. Updated checkpoint to {highest_id}. Processed {processed_count} articles.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    # If run in parent directory, fallback to parent .env
    if not os.environ.get("SATYA_DB_URL"):
        load_dotenv("../.env")
    main()
