# DATABASE_SCHEMA.md: Database Architecture & PostgreSQL Schema

## 1. Entity-Relationship Diagram

```

`admin_review_story` (installed by
[`00005_admin_review_transaction.sql`](../apps/api/migrations/00005_admin_review_transaction.sql))
atomically checks the curator role and publication rights, updates story status
and visibility, and inserts the matching `story_human_reviews` audit record.
Only the trusted API `service_role` can execute it.mermaid

`admin_save_curated_draft` (installed by
[`00006_curated_draft_transaction.sql`](../apps/api/migrations/00006_curated_draft_transaction.sql))
atomically creates or updates an unapproved curated version, calculates its
word count and 140 wpm duration, and stores the revision in
`story_human_reviews`. Approved versions cannot be overwritten as drafts.mermaid
erDiagram
    DOCUMENTS ||--o{ DOCUMENT_PAGES : "parsed into"
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : "chunked into"
    DOCUMENTS ||--o{ STORIES : "contains"
    DOCUMENTS ||--o{ PROCESSING_JOBS : "processed via"
    
    DOCUMENT_PAGES ||--o{ STORY_SOURCE_SPANS : "referenced by"
    DOCUMENT_CHUNKS ||--o{ STORY_SOURCE_SPANS : "spanned by"

    PROCESSING_JOBS ||--o{ PROCESSING_JOB_EVENTS : "logs"

    STORIES ||--o{ STORY_SOURCE_SPANS : "assembled from"
    STORIES ||--o{ STORY_CURATED_VERSIONS : "curated into"
    STORIES ||--o{ STORY_AI_EVALUATIONS : "evaluated by"
    STORIES ||--o{ STORY_VARIANT_ASSIGNMENTS : "assigned"
    STORIES ||--o{ STORY_EMOTIONS : "expresses"
    STORIES ||--o{ STORY_STEP_ANALYSES : "analyzed by"
    STORIES ||--o{ STORY_EMBEDDINGS : "vectorized in"
    STORIES ||--o{ STORY_HUMAN_REVIEWS : "audited in"
    STORIES ||--o{ STORY_TAGS : "tagged with"
    STORIES ||--o{ COLLECTION_STORIES : "grouped in"
    STORIES ||--o{ USER_BOOKMARKS : "bookmarked in"

    TAGS ||--o{ STORY_TAGS : "applied to"
    COLLECTIONS ||--o{ COLLECTION_STORIES : "contains"

    USER_PROFILES ||--o{ STORIES : "approved by"
    USER_PROFILES ||--o{ STORY_HUMAN_REVIEWS : "performed by"
    USER_PROFILES ||--o{ USER_BOOKMARKS : "saved by"
    USER_PROFILES ||--o{ ADMIN_INVITATIONS : "invited by"
```

---

## 2. PostgreSQL Custom Types & Extensions

```sql
-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector for dense embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- Trigram matching for fuzzy searching

-- Story Variants Enum (Authoritative 4 Variants)
CREATE TYPE story_variant AS ENUM (
    'return_to_joy',              -- Return to Joy (Level 3)
    'acting_like_myself',          -- Acting Like Myself (Level 4)
    'godsight_immanuel',           -- Godsight / Immanuel
    'appreciation_joy_spreading'   -- Appreciation / Joy-Spreading
);

-- Story Lifecycle Status Enum
CREATE TYPE story_status AS ENUM (
    'discovered_pending_review',
    'under_review',
    'approved',
    'rejected',
    'archived'
);

-- Narrator Gender Classification
CREATE TYPE narrator_gender AS ENUM ('male', 'female', 'unknown');

-- Story Visibility Tier
CREATE TYPE story_visibility AS ENUM (
    'internal_only',
    'registered_users',
    'public'
);

-- Overall 4+ Classification Enum
CREATE TYPE four_plus_classification AS ENUM (
    'confirmed_4_plus',
    'not_4_plus',
    'uncertain_needs_review'
);

-- Individual Criterion Result Enum
CREATE TYPE criterion_result AS ENUM (
    'met',
    'partially_met',
    'not_met',
    'uncertain',
    'not_applicable'
);

-- Emotion Categories (Big 6 + Positive / Connective)
CREATE TYPE emotion_type AS ENUM (
    'fear',
    'anger',
    'sadness',
    'shame',
    'disgust',
    'hopeless_despair',
    'joy',
    'gratitude',
    'peace',
    'other'
);

CREATE TYPE emotion_energy_level AS ENUM (
    'high_energy',
    'low_energy',
    'positive_connective'
);

CREATE TYPE progression_stage AS ENUM (
    'initial',
    'escalation',
    'peak',
    'shift',
    'resolving'
);

-- Document Rights Status Enum
CREATE TYPE document_rights_status AS ENUM (
    'public_domain',
    'licensed',
    'restricted_internal',
    'fair_use_educational'
);

-- User Role Enum
CREATE TYPE user_role AS ENUM (
    'super_admin',
    'curator',
    'reviewer',
    'church_member',
    'public_guest'
);

-- Document Type Enum
CREATE TYPE document_type AS ENUM (
    'pdf_book',
    'pdf_article',
    'txt_transcript',
    'txt_story_note'
);

-- Job Status Enum
CREATE TYPE job_status AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed',
    'cancelled'
);
```

---

## 3. Core Table Definitions (DDL)

### 3.1. User Management & Profiles
```sql
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'church_member',
    church_affiliation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_profiles_role ON user_profiles(role);

CREATE TABLE admin_invitations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT NOT NULL UNIQUE,
    role user_role NOT NULL CHECK (role IN ('super_admin', 'curator', 'reviewer')),
    invite_token TEXT NOT NULL UNIQUE,
    invited_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_admin_invitations_token ON admin_invitations(invite_token);
```

### 3.2. Documents, Pages, Chunks, & Processing Jobs
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    author TEXT,
    document_type document_type NOT NULL,
    source_file_path TEXT NOT NULL,
    file_hash_sha256 TEXT NOT NULL UNIQUE,
    page_count INTEGER,
    rights_status document_rights_status NOT NULL DEFAULT 'fair_use_educational',
    publication_restrictions TEXT, -- Optional legal/takedown restriction notice
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_file_hash ON documents(file_hash_sha256);
CREATE INDEX idx_documents_rights ON documents(rights_status);

CREATE TABLE document_pages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    page_number INTEGER NOT NULL,
    extracted_text TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb, -- Bounding boxes, layout data
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, page_number)
);

CREATE INDEX idx_document_pages_doc_page ON document_pages(document_id, page_number);

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    chunk_index INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX idx_document_chunks_doc_chunk ON document_chunks(document_id, chunk_index);

CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    job_type TEXT NOT NULL, -- 'pdf_extraction', 'story_discovery', 'story_evaluation'
    status job_status NOT NULL DEFAULT 'pending',
    error_message TEXT,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_processing_jobs_doc ON processing_jobs(document_id);
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);

CREATE TABLE processing_job_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info', -- 'info', 'warn', 'error'
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_job_events_job_id ON processing_job_events(job_id);
```

### 3.3. Stories, Multi-Span Sources, & Curated Versions
```sql
CREATE TABLE stories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    original_text TEXT NOT NULL, -- Verbatim text retrieved from verified page boundaries
    original_word_count INTEGER NOT NULL,
    estimated_spoken_duration_seconds INTEGER NOT NULL, -- e.g. (word_count / 140) * 60
    length_advisory_exceeds_800_words BOOLEAN GENERATED ALWAYS AS (original_word_count > 800) STORED,
    is_autobiographical BOOLEAN,
    narrator_gender narrator_gender NOT NULL DEFAULT 'unknown',
    status story_status NOT NULL DEFAULT 'discovered_pending_review',
    visibility story_visibility NOT NULL DEFAULT 'internal_only',
    tsv_search TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(original_text, '')), 'C')
    ) STORED,
    approved_by_user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stories_status ON stories(status);
CREATE INDEX idx_stories_visibility ON stories(visibility);
CREATE INDEX idx_stories_narrator_gender ON stories(narrator_gender);
CREATE INDEX idx_stories_document_id ON stories(document_id);
CREATE INDEX idx_stories_length_advisory ON stories(length_advisory_exceeds_800_words);
CREATE INDEX idx_stories_tsv_search ON stories USING GIN(tsv_search);

-- Source spans preserving exact multi-page / non-contiguous story text
CREATE TABLE story_source_spans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    document_page_id UUID NOT NULL REFERENCES document_pages(id) ON DELETE RESTRICT,
    chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    span_order INTEGER NOT NULL DEFAULT 1,
    page_number INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    verbatim_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(story_id, span_order)
);

CREATE INDEX idx_source_spans_story ON story_source_spans(story_id);
CREATE INDEX idx_source_spans_page ON story_source_spans(document_page_id);

-- Boundary proposals are separate from source text and remain curator-only.
CREATE TABLE story_boundary_candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    story_id UUID NOT NULL UNIQUE REFERENCES stories(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    tentative_title TEXT NOT NULL,
    first_sentence TEXT NOT NULL,
    last_sentence TEXT NOT NULL,
    evidence_quote TEXT NOT NULL,
    approx_char_start INTEGER NOT NULL CHECK (approx_char_start >= 0),
    approx_char_end INTEGER NOT NULL CHECK (approx_char_end >= 1),
    document_char_start INTEGER NOT NULL CHECK (document_char_start >= 0),
    document_char_end INTEGER NOT NULL CHECK (document_char_end > document_char_start),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, document_char_start, document_char_end)
);

CREATE INDEX idx_boundary_candidates_document
    ON story_boundary_candidates(document_id, created_at);

-- Separate human-approved curated telling versions
CREATE TABLE story_curated_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    curated_title TEXT NOT NULL,
    curated_text TEXT NOT NULL,
    curated_word_count INTEGER NOT NULL,
    curated_spoken_duration_seconds INTEGER NOT NULL,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by_user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    editorial_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_curated_versions_story ON story_curated_versions(story_id);
CREATE INDEX idx_curated_versions_approved ON story_curated_versions(is_approved);
```

### 3.4. Analysis Dimensions: AI Evaluations, Variants, Emotions, & STEP
```sql
CREATE TABLE story_ai_evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    overall_classification four_plus_classification NOT NULL,
    overall_confidence NUMERIC(4, 3) NOT NULL CHECK (overall_confidence BETWEEN 0 AND 1),
    criteria_evaluations JSONB NOT NULL,
    -- criteria_evaluations stores:
    -- {
    --   "autobiographical_involvement": {"result": "met", "confidence": float, "quote": str, "reasoning": str},
    --   "appropriate_emotional_intensity": {"result": "met", "intensity_level": str, "confidence": float, "quote": str, "reasoning": str},
    --   "explicit_emotion_and_body_sensations": {"result": "met", "sensations_identified": [...], "sensations_missing": bool, "quote": str, "reasoning": str},
    --   "relational_co_regulation": {"result": "met", "coregulator_type": str, "quote": str, "reasoning": str},
    --   "redemptive_outcome": {"result": "met", "quote": str, "reasoning": str}
    -- }
    reasoning_summary TEXT NOT NULL,
    token_usage JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_evaluations_story ON story_ai_evaluations(story_id);
CREATE INDEX idx_ai_evaluations_classification ON story_ai_evaluations(overall_classification);

-- Multi-variant assignment table (Zero, one, or multiple variants per story)
CREATE TABLE story_variant_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    variant story_variant NOT NULL,
    assignment_source TEXT NOT NULL DEFAULT 'ai_proposed', -- 'ai_proposed', 'human_curated'
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_quote TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    assigned_by_user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(story_id, variant)
);

CREATE INDEX idx_variant_assignments_story ON story_variant_assignments(story_id);
CREATE INDEX idx_variant_assignments_variant ON story_variant_assignments(variant);

-- Structured Emotion & Somatics Table
CREATE TABLE story_emotions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    emotion emotion_type NOT NULL,
    energy_level emotion_energy_level NOT NULL,
    progression_stage progression_stage NOT NULL DEFAULT 'initial',
    evidence_quote TEXT NOT NULL,
    source_page INTEGER,
    source_char_offset INTEGER,
    sensations_identified TEXT[] NOT NULL DEFAULT '{}',
    sensations_missing BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_by TEXT NOT NULL DEFAULT 'ai_extracted', -- 'ai_extracted', 'human_curated'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_story_emotions_story ON story_emotions(story_id);
CREATE INDEX idx_story_emotions_emotion ON story_emotions(emotion);

-- Restored STEP Analysis Table
CREATE TABLE story_step_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    setting TEXT NOT NULL,                        -- S: Setting
    trigger TEXT NOT NULL,                        -- T: Trigger
    emotion_and_body_sensations TEXT NOT NULL,    -- E: Emotion & Body Sensations
    point TEXT NOT NULL,                          -- P: Point
    internal_thoughts TEXT,                       -- Supplementary analysis
    relational_presence TEXT,                     -- Supplementary analysis
    is_human_edited BOOLEAN NOT NULL DEFAULT FALSE,
    edited_by_user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_step_analyses_story ON story_step_analyses(story_id);
```

### 3.5. Vector Embeddings with Parameterized Dimensionality
```sql
-- The deployed schema and HNSW index are fixed at 1536 dimensions.
-- Changing dimensions requires a coordinated migration and embedding rebuild.
CREATE TABLE story_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    embedding_type TEXT NOT NULL DEFAULT 'story_composite',
    embedding_model TEXT NOT NULL,
    model_version TEXT NOT NULL,
    content_hash TEXT NOT NULL, -- SHA-256 hash of embedded string to track staleness
    embedding VECTOR(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(story_id, embedding_type, embedding_model)
);

CREATE INDEX idx_story_embeddings_story ON story_embeddings(story_id);
CREATE INDEX idx_story_embeddings_vector ON story_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### 3.6. Audit Logging, Human Revisions, Tags, Collections, & Bookmarks
```sql
CREATE TABLE story_human_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    reviewer_user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE RESTRICT,
    action TEXT NOT NULL, -- 'approve', 'reject', 'edit_text', 'edit_step', 'curate_version'
    diff JSONB,
    previous_state JSONB NOT NULL,
    new_state JSONB NOT NULL,
    reviewer_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_human_reviews_story ON story_human_reviews(story_id);
CREATE INDEX idx_human_reviews_user ON story_human_reviews(reviewer_user_id);

CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE story_tags (
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (story_id, tag_id)
);

CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE collection_stories (
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (collection_id, story_id)
);

CREATE TABLE user_bookmarks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, story_id)
);

CREATE INDEX idx_user_bookmarks_user ON user_bookmarks(user_id);
```

---

## 4. Helper Functions & Stored Procedures (with Security Controls)

```sql
-- Helper function: Check if current user is an admin or curator
-- Hardened with explicit search_path
CREATE OR REPLACE FUNCTION public.is_curator_or_admin()
RETURNS BOOLEAN 
LANGUAGE plpgsql 
SECURITY DEFINER
SET search_path = public, auth
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE id = auth.uid()
        AND role IN ('super_admin', 'curator', 'reviewer')
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.is_curator_or_admin() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_curator_or_admin() TO authenticated;

-- The hardened hybrid_story_search implementation is maintained in
-- apps/api/migrations/00004_hardened_hybrid_search.sql. It is SECURITY DEFINER,
-- accepts a registered-visibility flag only from the trusted API service role,
-- enforces approval, visibility, document rights, and publication restrictions,
-- and fuses sparse/dense ranks with RRF. Execution is revoked from PUBLIC,
-- anon, and authenticated and granted only to service_role.
```

---

## 5. Row-Level Security (RLS) Policies

```sql
-- Enable RLS across all tables
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE stories ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_source_spans ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_boundary_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_curated_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_ai_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_variant_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_emotions ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_step_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_human_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE collections ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection_stories ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_bookmarks ENABLE ROW LEVEL SECURITY;

-- 1. Stories Policies:
-- Editorial approval ALONE does not grant public access. Must satisfy visibility + rights.
CREATE POLICY "Public read approved and rights-cleared stories"
ON stories FOR SELECT
USING (
    status = 'approved'
    AND visibility = 'public'
    AND EXISTS (
        SELECT 1 FROM documents d
        WHERE d.id = stories.document_id
        AND d.rights_status IN ('public_domain', 'licensed', 'fair_use_educational')
        AND d.publication_restrictions IS NULL
    )
);

CREATE POLICY "Registered members read approved stories"
ON stories FOR SELECT
USING (
    auth.uid() IS NOT NULL
    AND status = 'approved'
    AND visibility IN ('public', 'registered_users')
);

CREATE POLICY "Curators full access on stories"
ON stories FOR ALL
USING (public.is_curator_or_admin());

CREATE POLICY "Curators manage story boundary candidates"
ON story_boundary_candidates FOR ALL
USING (public.is_curator_or_admin())
WITH CHECK (public.is_curator_or_admin());

-- 2. Curated Versions Policies:
CREATE POLICY "Public read approved curated versions"
ON story_curated_versions FOR SELECT
USING (
    is_approved = TRUE
    AND EXISTS (
        SELECT 1 FROM stories s
        WHERE s.id = story_curated_versions.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
    )
);

CREATE POLICY "Curators manage curated versions"
ON story_curated_versions FOR ALL
USING (public.is_curator_or_admin());

-- 3. Document & Source Protection Policies:
CREATE POLICY "Curators manage documents"
ON documents FOR ALL
USING (public.is_curator_or_admin());

CREATE POLICY "Curators manage document pages"
ON document_pages FOR ALL
USING (public.is_curator_or_admin());

-- 4. Analysis Dimensions (STEP, Variants, Emotions):
CREATE POLICY "Public read approved STEP analyses"
ON story_step_analyses FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM stories s
        WHERE s.id = story_step_analyses.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
    ) OR public.is_curator_or_admin()
);

CREATE POLICY "Public read approved variant assignments"
ON story_variant_assignments FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM stories s
        WHERE s.id = story_variant_assignments.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
    ) OR public.is_curator_or_admin()
);

CREATE POLICY "Public read approved emotions"
ON story_emotions FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM stories s
        WHERE s.id = story_emotions.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
    ) OR public.is_curator_or_admin()
);

-- AI evaluations are restricted strictly to curators and admins
CREATE POLICY "Curators view AI evaluations"
ON story_ai_evaluations FOR ALL
USING (public.is_curator_or_admin());
```
