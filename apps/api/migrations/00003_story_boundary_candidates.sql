-- Persist boundary-detection proposals separately from immutable story text.
CREATE TABLE IF NOT EXISTS story_boundary_candidates (
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

CREATE INDEX IF NOT EXISTS idx_boundary_candidates_document
    ON story_boundary_candidates(document_id, created_at);

ALTER TABLE story_boundary_candidates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Curators manage story boundary candidates"
ON story_boundary_candidates FOR ALL
USING (public.is_curator_or_admin())
WITH CHECK (public.is_curator_or_admin());
