-- Migration: 00001_initial_schema.sql
-- Description: Core schema, enums, tables, cascade protections, pgvector HNSW, RLS, and hybrid search function

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector for semantic embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- Trigram matching for fuzzy searching

-- 2. Custom Enumerations
DO $$ BEGIN
    CREATE TYPE story_variant AS ENUM (
        'return_to_joy',              -- Return to Joy (Level 3)
        'acting_like_myself',          -- Acting Like Myself (Level 4)
        'godsight_immanuel',           -- Godsight / Immanuel
        'appreciation_joy_spreading'   -- Appreciation / Joy-Spreading
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE story_status AS ENUM (
        'discovered_pending_review',
        'under_review',
        'approved',
        'rejected',
        'archived'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE story_visibility AS ENUM (
        'internal_only',
        'registered_users',
        'public'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE four_plus_classification AS ENUM (
        'confirmed_4_plus',
        'not_4_plus',
        'uncertain_needs_review'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE criterion_result AS ENUM (
        'met',
        'partially_met',
        'not_met',
        'uncertain',
        'not_applicable'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
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
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE emotion_energy_level AS ENUM (
        'high_energy',
        'low_energy',
        'positive_connective'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE progression_stage AS ENUM (
        'initial',
        'escalation',
        'peak',
        'shift',
        'resolving'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE document_rights_status AS ENUM (
        'public_domain',
        'licensed',
        'restricted_internal',
        'fair_use_educational'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE user_role AS ENUM (
        'super_admin',
        'curator',
        'reviewer',
        'church_member',
        'public_guest'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE document_type AS ENUM (
        'pdf_book',
        'pdf_article',
        'txt_transcript',
        'txt_story_note'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE job_status AS ENUM (
        'pending',
        'processing',
        'completed',
        'failed',
        'cancelled'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 3. Core Tables

-- 3.1. user_profiles
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'church_member',
    church_affiliation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_role ON user_profiles(role);

-- 3.2. admin_invitations
CREATE TABLE IF NOT EXISTS admin_invitations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT NOT NULL UNIQUE,
    role user_role NOT NULL CHECK (role IN ('super_admin', 'curator', 'reviewer')),
    invite_token TEXT NOT NULL UNIQUE,
    invited_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_invitations_token ON admin_invitations(invite_token);

-- 3.3. documents
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    author TEXT,
    document_type document_type NOT NULL,
    source_file_path TEXT NOT NULL,
    file_hash_sha256 TEXT NOT NULL UNIQUE,
    page_count INTEGER,
    rights_status document_rights_status NOT NULL DEFAULT 'fair_use_educational',
    publication_restrictions TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash_sha256);
CREATE INDEX IF NOT EXISTS idx_documents_rights ON documents(rights_status);

-- 3.4. document_pages (Protected with ON DELETE RESTRICT)
CREATE TABLE IF NOT EXISTS document_pages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    page_number INTEGER NOT NULL,
    extracted_text TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_document_pages_doc_page ON document_pages(document_id, page_number);

-- 3.5. document_chunks (Protected with ON DELETE RESTRICT)
CREATE TABLE IF NOT EXISTS document_chunks (
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

CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_chunk ON document_chunks(document_id, chunk_index);

-- 3.6. processing_jobs & job events
CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    job_type TEXT NOT NULL,
    status job_status NOT NULL DEFAULT 'pending',
    error_message TEXT,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_doc ON processing_jobs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);

CREATE TABLE IF NOT EXISTS processing_job_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON processing_job_events(job_id);

-- 3.7. stories (Original text & spoken duration metrics)
CREATE TABLE IF NOT EXISTS stories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    original_text TEXT NOT NULL,
    original_word_count INTEGER NOT NULL,
    estimated_spoken_duration_seconds INTEGER NOT NULL,
    length_advisory_exceeds_600_words BOOLEAN GENERATED ALWAYS AS (original_word_count > 600) STORED,
    is_autobiographical BOOLEAN,
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

CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);
CREATE INDEX IF NOT EXISTS idx_stories_visibility ON stories(visibility);
CREATE INDEX IF NOT EXISTS idx_stories_document_id ON stories(document_id);
CREATE INDEX IF NOT EXISTS idx_stories_length_advisory ON stories(length_advisory_exceeds_600_words);
CREATE INDEX IF NOT EXISTS idx_stories_tsv_search ON stories USING GIN(tsv_search);

-- 3.8. story_source_spans (Multi-span tracking)
CREATE TABLE IF NOT EXISTS story_source_spans (
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

CREATE INDEX IF NOT EXISTS idx_source_spans_story ON story_source_spans(story_id);
CREATE INDEX IF NOT EXISTS idx_source_spans_page ON story_source_spans(document_page_id);

-- 3.9. story_curated_versions (Separate curated oral telling versions)
CREATE TABLE IF NOT EXISTS story_curated_versions (
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

CREATE INDEX IF NOT EXISTS idx_curated_versions_story ON story_curated_versions(story_id);
CREATE INDEX IF NOT EXISTS idx_curated_versions_approved ON story_curated_versions(is_approved);

-- 3.10. story_ai_evaluations
CREATE TABLE IF NOT EXISTS story_ai_evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    overall_classification four_plus_classification NOT NULL,
    overall_confidence NUMERIC(4, 3) NOT NULL CHECK (overall_confidence BETWEEN 0 AND 1),
    criteria_evaluations JSONB NOT NULL,
    reasoning_summary TEXT NOT NULL,
    token_usage JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_evaluations_story ON story_ai_evaluations(story_id);
CREATE INDEX IF NOT EXISTS idx_ai_evaluations_classification ON story_ai_evaluations(overall_classification);

-- 3.11. story_variant_assignments (Zero, one, or multiple variants per story)
CREATE TABLE IF NOT EXISTS story_variant_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    variant story_variant NOT NULL,
    assignment_source TEXT NOT NULL DEFAULT 'ai_proposed',
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_quote TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    assigned_by_user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(story_id, variant)
);

CREATE INDEX IF NOT EXISTS idx_variant_assignments_story ON story_variant_assignments(story_id);
CREATE INDEX IF NOT EXISTS idx_variant_assignments_variant ON story_variant_assignments(variant);

-- 3.12. story_emotions (Big 6 + Connective Emotions & Somatic Sensations)
CREATE TABLE IF NOT EXISTS story_emotions (
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
    assigned_by TEXT NOT NULL DEFAULT 'ai_extracted',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_story_emotions_story ON story_emotions(story_id);
CREATE INDEX IF NOT EXISTS idx_story_emotions_emotion ON story_emotions(emotion);

-- 3.13. story_step_analyses (Restored STEP: Setting, Trigger, Emotion & Sensations, Point)
CREATE TABLE IF NOT EXISTS story_step_analyses (
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

CREATE INDEX IF NOT EXISTS idx_step_analyses_story ON story_step_analyses(story_id);

-- 3.14. story_embeddings (Unhardcoded parameterized vector dimension)
CREATE TABLE IF NOT EXISTS story_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    embedding_type TEXT NOT NULL DEFAULT 'story_composite',
    embedding_model TEXT NOT NULL,
    model_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(story_id, embedding_type, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_story_embeddings_story ON story_embeddings(story_id);
CREATE INDEX IF NOT EXISTS idx_story_embeddings_vector ON story_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 3.15. story_human_reviews (Immutable audit log)
CREATE TABLE IF NOT EXISTS story_human_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    reviewer_user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE RESTRICT,
    action TEXT NOT NULL,
    diff JSONB,
    previous_state JSONB NOT NULL,
    new_state JSONB NOT NULL,
    reviewer_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_human_reviews_story ON story_human_reviews(story_id);
CREATE INDEX IF NOT EXISTS idx_human_reviews_user ON story_human_reviews(reviewer_user_id);

-- 3.16. Tags & Collections
CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS story_tags (
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (story_id, tag_id)
);

CREATE TABLE IF NOT EXISTS collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS collection_stories (
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (collection_id, story_id)
);

CREATE TABLE IF NOT EXISTS user_bookmarks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, story_id)
);

CREATE INDEX IF NOT EXISTS idx_user_bookmarks_user ON user_bookmarks(user_id);

-- 4. Triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER trigger_user_profiles_updated_at
BEFORE UPDATE ON user_profiles
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

DROP TRIGGER IF EXISTS trigger_documents_updated_at ON documents;
CREATE TRIGGER trigger_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

DROP TRIGGER IF EXISTS trigger_processing_jobs_updated_at ON processing_jobs;
CREATE TRIGGER trigger_processing_jobs_updated_at
BEFORE UPDATE ON processing_jobs
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

DROP TRIGGER IF EXISTS trigger_stories_updated_at ON stories;
CREATE TRIGGER trigger_stories_updated_at
BEFORE UPDATE ON stories
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

DROP TRIGGER IF EXISTS trigger_story_curated_versions_updated_at ON story_curated_versions;
CREATE TRIGGER trigger_story_curated_versions_updated_at
BEFORE UPDATE ON story_curated_versions
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

DROP TRIGGER IF EXISTS trigger_story_step_analyses_updated_at ON story_step_analyses;
CREATE TRIGGER trigger_story_step_analyses_updated_at
BEFORE UPDATE ON story_step_analyses
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- 5. Helper Functions & Stored Procedures (with Security Controls)

-- Helper function: Check if current user has an administrative or curator role
CREATE OR REPLACE FUNCTION auth.is_curator_or_admin()
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

REVOKE EXECUTE ON FUNCTION auth.is_curator_or_admin() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth.is_curator_or_admin() TO authenticated;

-- Hybrid Search Stored Procedure combining dense vector search and sparse full-text search via RRF
-- Strictly enforces: approval + visibility + document rights clearance
CREATE OR REPLACE FUNCTION public.hybrid_story_search(
    query_text TEXT,
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 20,
    filter_variant story_variant DEFAULT NULL,
    filter_emotion emotion_type DEFAULT NULL,
    rrf_k INT DEFAULT 60
)
RETURNS TABLE (
    story_id UUID,
    title TEXT,
    original_text TEXT,
    original_word_count INT,
    estimated_spoken_duration_seconds INT,
    length_advisory_exceeds_600_words BOOLEAN,
    sparse_rank BIGINT,
    dense_rank BIGINT,
    rrf_score FLOAT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
BEGIN
    RETURN QUERY
    WITH accessible_stories AS (
        SELECT s.id
        FROM public.stories s
        JOIN public.documents d ON d.id = s.document_id
        WHERE s.status = 'approved'
          AND (
              -- Public access: Approved + Public Visibility + Document Rights cleared
              (s.visibility = 'public' 
               AND d.rights_status IN ('public_domain', 'licensed', 'fair_use_educational')
               AND d.publication_restrictions IS NULL)
              OR
              -- Registered user access
              (auth.uid() IS NOT NULL AND s.visibility IN ('public', 'registered_users'))
              OR
              -- Curator / admin access
              auth.is_curator_or_admin()
          )
          AND (filter_variant IS NULL OR EXISTS (
              SELECT 1 FROM public.story_variant_assignments sva
              WHERE sva.story_id = s.id AND sva.variant = filter_variant
          ))
          AND (filter_emotion IS NULL OR EXISTS (
              SELECT 1 FROM public.story_emotions se
              WHERE se.story_id = s.id AND se.emotion = filter_emotion
          ))
    ),
    sparse_results AS (
        SELECT 
            s.id AS s_id,
            ROW_NUMBER() OVER (ORDER BY ts_rank_cd(s.tsv_search, websearch_to_tsquery('english', query_text)) DESC) AS rank
        FROM public.stories s
        JOIN accessible_stories acc ON acc.id = s.id
        WHERE s.tsv_search @@ websearch_to_tsquery('english', query_text)
        LIMIT 50
    ),
    dense_results AS (
        SELECT 
            se.story_id AS d_id,
            ROW_NUMBER() OVER (ORDER BY se.embedding <=> query_embedding ASC) AS rank
        FROM public.story_embeddings se
        JOIN accessible_stories acc ON acc.id = se.story_id
        ORDER BY se.embedding <=> query_embedding ASC
        LIMIT 50
    )
    SELECT 
        s.id AS story_id,
        s.title,
        s.original_text,
        s.original_word_count,
        s.estimated_spoken_duration_seconds,
        s.length_advisory_exceeds_600_words,
        sr.rank AS sparse_rank,
        dr.rank AS dense_rank,
        (
            COALESCE(1.0 / (rrf_k + sr.rank), 0.0) +
            COALESCE(1.0 / (rrf_k + dr.rank), 0.0)
        )::FLOAT AS rrf_score
    FROM public.stories s
    LEFT JOIN sparse_results sr ON s.id = sr.s_id
    LEFT JOIN dense_results dr ON s.id = dr.d_id
    WHERE sr.s_id IS NOT NULL OR dr.d_id IS NOT NULL
    ORDER BY rrf_score DESC
    LIMIT match_count;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.hybrid_story_search(TEXT, VECTOR, INT, story_variant, emotion_type, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.hybrid_story_search(TEXT, VECTOR, INT, story_variant, emotion_type, INT) TO anon, authenticated;

-- 6. Row-Level Security (RLS) Configuration
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE stories ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_source_spans ENABLE ROW LEVEL SECURITY;
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

-- 6.1. user_profiles Policies
CREATE POLICY "Users can read own profile"
ON user_profiles FOR SELECT
USING (auth.uid() = id OR auth.is_curator_or_admin());

CREATE POLICY "Users can update own profile"
ON user_profiles FOR UPDATE
USING (auth.uid() = id);

-- 6.2. documents & document_pages Policies
CREATE POLICY "Curators manage documents"
ON documents FOR ALL
USING (auth.is_curator_or_admin());

CREATE POLICY "Curators manage document pages"
ON document_pages FOR ALL
USING (auth.is_curator_or_admin());

CREATE POLICY "Curators manage document chunks"
ON document_chunks FOR ALL
USING (auth.is_curator_or_admin());

CREATE POLICY "Curators manage processing jobs"
ON processing_jobs FOR ALL
USING (auth.is_curator_or_admin());

CREATE POLICY "Curators manage processing job events"
ON processing_job_events FOR ALL
USING (auth.is_curator_or_admin());

-- 6.3. stories Policies
-- Public access: Requires approved + public visibility + rights clearance
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

-- Registered church member access: Requires approved + visibility in ('public', 'registered_users')
CREATE POLICY "Registered members read approved stories"
ON stories FOR SELECT
USING (
    auth.uid() IS NOT NULL
    AND status = 'approved'
    AND visibility IN ('public', 'registered_users')
);

-- Curators & admins have full management access
CREATE POLICY "Curators full access on stories"
ON stories FOR ALL
USING (auth.is_curator_or_admin());

-- 6.4. story_source_spans Policies
CREATE POLICY "Public read spans of approved stories"
ON story_source_spans FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM stories s
        JOIN documents d ON d.id = s.document_id
        WHERE s.id = story_source_spans.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
        AND d.rights_status IN ('public_domain', 'licensed', 'fair_use_educational')
        AND d.publication_restrictions IS NULL
    ) OR auth.is_curator_or_admin()
);

CREATE POLICY "Curators manage story source spans"
ON story_source_spans FOR ALL
USING (auth.is_curator_or_admin());

-- 6.5. story_curated_versions Policies
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
USING (auth.is_curator_or_admin());

-- 6.6. Analysis Dimensions (STEP, Variants, Emotions, AI Evaluations)
CREATE POLICY "Public read approved STEP analyses"
ON story_step_analyses FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM stories s
        WHERE s.id = story_step_analyses.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
    ) OR auth.is_curator_or_admin()
);

CREATE POLICY "Curators manage STEP analyses"
ON story_step_analyses FOR ALL
USING (auth.is_curator_or_admin());

CREATE POLICY "Public read approved variant assignments"
ON story_variant_assignments FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM stories s
        WHERE s.id = story_variant_assignments.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
    ) OR auth.is_curator_or_admin()
);

CREATE POLICY "Curators manage variant assignments"
ON story_variant_assignments FOR ALL
USING (auth.is_curator_or_admin());

CREATE POLICY "Public read approved emotions"
ON story_emotions FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM stories s
        WHERE s.id = story_emotions.story_id
        AND s.status = 'approved'
        AND s.visibility = 'public'
    ) OR auth.is_curator_or_admin()
);

CREATE POLICY "Curators manage emotions"
ON story_emotions FOR ALL
USING (auth.is_curator_or_admin());

-- AI evaluations are strictly internal to curators/admins
CREATE POLICY "Curators access AI evaluations"
ON story_ai_evaluations FOR ALL
USING (auth.is_curator_or_admin());

CREATE POLICY "Curators manage embeddings"
ON story_embeddings FOR ALL
USING (auth.is_curator_or_admin());

-- 6.7. story_human_reviews (Immutable audit log)
CREATE POLICY "Curators view audit reviews"
ON story_human_reviews FOR SELECT
USING (auth.is_curator_or_admin());

CREATE POLICY "Curators create audit review entries"
ON story_human_reviews FOR INSERT
WITH CHECK (auth.is_curator_or_admin());

-- 6.8. User Bookmarks Policies
CREATE POLICY "Users manage own bookmarks"
ON user_bookmarks FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- 6.9. Admin Invitations Policies
CREATE POLICY "Super admins manage admin invitations"
ON admin_invitations FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM user_profiles
        WHERE id = auth.uid()
        AND role = 'super_admin'
    )
);

