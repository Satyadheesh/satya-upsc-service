import os
import json
import logging
import argparse
from huggingface_hub import hf_hub_download
from llama_cpp import Llama
import libsql_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

MODEL_REPO = "bartowski/Qwen2.5-7B-Instruct-GGUF"
MODEL_FILENAME = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
MODEL_DIR = os.path.join(os.getcwd(), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

MAIN_DB_URL = os.environ.get("SATYA_DB_URL")
MAIN_DB_TOKEN = os.environ.get("SATYA_DB_TOKEN")
UPSC_DB_URL = os.environ.get("SATYA_UPSC_DB_URL")
UPSC_DB_TOKEN = os.environ.get("SATYA_UPSC_DB_TOKEN")

SYSTEM_PROMPT = """You are a master UPSC Civil Services Examination coach.
Analyze the provided Indian news article and extract relevant facts for a UPSC aspirant.

If the article is NOT relevant to UPSC (e.g. gossip, sports, minor local crime, entertainment), you MUST return EXACTLY this JSON:
{"relevant": false}

If the article IS relevant to UPSC (e.g. economy, polity, environment, IR, governance, science), return EXACTLY this JSON:
{
  "relevant": true,
  "gs_paper": "GS1" | "GS2" | "GS3" | "GS4" | "Prelims facts",
  "topic": "Economy" | "Polity" | "IR" | "Environment" | etc (keep it to 1-2 words),
  "fact_box": "A concise 1-2 sentence summary of the core hard facts/data.",
  "relevance_tags": ["tag1", "tag2"]
}

Respond ONLY with valid JSON. Do not include markdown formatting or extra text."""

def download_model():
    model_path = os.path.join(MODEL_DIR, MODEL_FILENAME)
    if not os.path.exists(model_path):
        logging.info(f"Downloading model {MODEL_FILENAME}...")
        hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILENAME, local_dir=MODEL_DIR)
        logging.info("Download complete.")
    return model_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", type=str, help="Comma-separated list of article IDs to process")
    args = parser.parse_args()

    if not MAIN_DB_URL or not UPSC_DB_URL:
        logging.error("Missing database environment variables.")
        return

    main_client = libsql_client.create_client_sync(url=MAIN_DB_URL.replace('libsql://', 'https://'), auth_token=MAIN_DB_TOKEN)
    upsc_client = libsql_client.create_client_sync(url=UPSC_DB_URL.replace('libsql://', 'https://'), auth_token=UPSC_DB_TOKEN)

    if not args.ids:
        logging.info("No IDs provided, nothing to process in this shard.")
        return

    id_list = [int(x.strip()) for x in args.ids.split(',') if x.strip()]
    if not id_list:
        return

    placeholders = ",".join(["?"] * len(id_list))
    res = main_client.execute(
        f"SELECT id, title, rephrased_article, category FROM articles WHERE id IN ({placeholders}) ORDER BY id ASC",
        id_list
    )
    articles = res.rows

    logging.info(f"Fetched {len(articles)} articles to process in this shard.")

    model_path = download_model()
    logging.info("Loading Qwen-2.5-7B-Instruct...")
    llm = Llama(
        model_path=model_path,
        n_ctx=4096,
        n_gpu_layers=-1,
        verbose=False
    )

    for row in articles:
        article_id = int(row[0])
        title = row[1]
        content = row[2] or ""
        category = row[3]
        
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
                gs_paper = data.get("gs_paper", "Prelims facts")
                topic = data.get("topic", "Current Affairs")
                fact_box = data.get("fact_box", "")
                tags = json.dumps(data.get("relevance_tags", []))
                
                upsc_client.execute(
                    "INSERT OR IGNORE INTO upsc_articles (article_id, gs_paper, topic, fact_box, relevance_tags, created_at) VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))",
                    [article_id, gs_paper, topic, fact_box, tags]
                )
                logging.info(f"  [+] Saved as {gs_paper} - {topic}")
            else:
                logging.info(f"  [-] Skipped (Not relevant to UPSC)")
                
        except Exception as e:
            logging.error(f"  [!] Failed to process article {article_id}: {e}")

    main_client.close()
    upsc_client.close()
    logging.info("Shard complete.")

if __name__ == "__main__":
    main()
