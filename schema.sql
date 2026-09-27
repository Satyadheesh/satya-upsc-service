-- satya-upsc DB, schema v2. Applied by migrate.py (idempotent).

-- One row per article judged UPSC-relevant (upsc_score >= threshold).
CREATE TABLE IF NOT EXISTS upsc_articles (
  article_id       INTEGER PRIMARY KEY,      -- articles.id in main DB
  published_at     INTEGER NOT NULL,         -- articles.scraped_at (NOT processing time)
  event_id         INTEGER,                  -- event_articles.event_id, for dedup in UI
  cluster_id       TEXT,
  upsc_score       INTEGER NOT NULL,         -- 3..5 (gate score)
  exam_type        TEXT NOT NULL CHECK (exam_type IN ('prelims','mains','both')),
  gs_paper         TEXT NOT NULL CHECK (gs_paper IN ('GS1','GS2','GS3','GS4')),
  subject          TEXT NOT NULL,            -- syllabus.py subject key
  syllabus_node    TEXT NOT NULL,            -- syllabus.py node key
  secondary        TEXT,                     -- JSON [{"subject","node"}] cross-paper links
  why_in_news      TEXT NOT NULL,            -- 1 line
  fact_box         TEXT NOT NULL,            -- 2-3 lines of hard facts
  prelims_pointers TEXT,                     -- JSON [{"type","text"}]
  mains_question   TEXT,
  mains_dimensions TEXT,                     -- JSON [str]
  keywords         TEXT,                     -- JSON [str]
  states           TEXT,                     -- JSON [str] from main DB, for State PSC filter
  model            TEXT,
  prompt_version   TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_upsc_pub     ON upsc_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_upsc_paper   ON upsc_articles(gs_paper, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_upsc_subject ON upsc_articles(subject, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_upsc_score   ON upsc_articles(upsc_score, published_at DESC);

-- Every article the service has looked at, whatever the outcome.
-- Selection = eligible main-DB articles NOT done in this ledger (no checkpoint).
CREATE TABLE IF NOT EXISTS upsc_processed (
  article_id     INTEGER PRIMARY KEY,
  verdict        TEXT NOT NULL CHECK (verdict IN ('relevant','irrelevant','prefiltered','failed')),
  upsc_score     INTEGER,
  reason         TEXT,                       -- gate reason / prefilter rule / error
  attempts       INTEGER NOT NULL DEFAULT 1,
  prompt_version TEXT,
  processed_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_upsc_proc_verdict ON upsc_processed(verdict, processed_at DESC);

-- Articles handed to a shard but not yet finished. Prevents two overlapping
-- runs from grabbing the same IDs; stale claims expire (see CLAIM_TTL).
CREATE TABLE IF NOT EXISTS upsc_claims (
  article_id INTEGER PRIMARY KEY,
  claimed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS upsc_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
INSERT OR REPLACE INTO upsc_meta (key, value) VALUES ('schema_version', '2');
