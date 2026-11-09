-- Limit the definer-privileged search procedure to the trusted API service role.
-- The API passes include_registered only after verifying the caller's Supabase profile.
DROP FUNCTION IF EXISTS public.hybrid_story_search(
    TEXT, VECTOR, INT, story_variant, emotion_type, INT
);

CREATE OR REPLACE FUNCTION public.hybrid_story_search(
    query_text TEXT,
    requested_embedding_model TEXT,
    query_embedding VECTOR(1536),
    include_registered BOOLEAN DEFAULT FALSE,
    match_count INT DEFAULT 20,
    result_offset INT DEFAULT 0,
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
    rrf_score FLOAT,
    total_matched BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, extensions
AS $$
BEGIN
    IF match_count < 1 OR match_count > 50 OR result_offset < 0 OR rrf_k < 1 THEN
        RAISE EXCEPTION 'Invalid hybrid search pagination or RRF parameters';
    END IF;

    RETURN QUERY
    WITH accessible_stories AS MATERIALIZED (
        SELECT s.id
        FROM public.stories s
        JOIN public.documents d ON d.id = s.document_id
        WHERE s.status = 'approved'
          AND d.rights_status IN ('public_domain', 'licensed', 'fair_use_educational')
          AND d.publication_restrictions IS NULL
          AND (
              s.visibility = 'public'
              OR (include_registered AND s.visibility = 'registered_users')
          )
          AND (filter_variant IS NULL OR EXISTS (
              SELECT 1
              FROM public.story_variant_assignments sva
              WHERE sva.story_id = s.id
                AND sva.variant = filter_variant
          ))
          AND (filter_emotion IS NULL OR EXISTS (
              SELECT 1
              FROM public.story_emotions se
              WHERE se.story_id = s.id
                AND se.emotion = filter_emotion
          ))
    ),
    sparse_results AS (
        SELECT
            s.id AS s_id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                    s.tsv_search,
                    websearch_to_tsquery('english', query_text)
                ) DESC, s.id
            ) AS rank
        FROM public.stories s
        JOIN accessible_stories acc ON acc.id = s.id
        WHERE s.tsv_search @@ websearch_to_tsquery('english', query_text)
        ORDER BY ts_rank_cd(
            s.tsv_search,
            websearch_to_tsquery('english', query_text)
        ) DESC, s.id
        LIMIT 100
    ),
    dense_results AS (
        SELECT
            se.story_id AS d_id,
            ROW_NUMBER() OVER (ORDER BY se.embedding <=> query_embedding, se.story_id) AS rank
        FROM public.story_embeddings se
        JOIN accessible_stories acc ON acc.id = se.story_id
        WHERE se.embedding_model = requested_embedding_model
          AND se.embedding_type = 'story_composite'
        ORDER BY se.embedding <=> query_embedding, se.story_id
        LIMIT 100
    ),
    fused AS (
        SELECT
            COALESCE(sr.s_id, dr.d_id) AS matched_id,
            sr.rank AS sparse_rank,
            dr.rank AS dense_rank,
            (
                COALESCE(1.0 / (rrf_k + sr.rank), 0.0)
                + COALESCE(1.0 / (rrf_k + dr.rank), 0.0)
            )::FLOAT AS score
        FROM sparse_results sr
        FULL OUTER JOIN dense_results dr ON dr.d_id = sr.s_id
    ),
    ranked AS (
        SELECT
            f.matched_id,
            f.sparse_rank,
            f.dense_rank,
            f.score,
            COUNT(*) OVER () AS match_total
        FROM fused f
    )
    SELECT
        s.id,
        s.title,
        s.original_text,
        s.original_word_count,
        s.estimated_spoken_duration_seconds,
        s.length_advisory_exceeds_600_words,
        ranked.sparse_rank,
        ranked.dense_rank,
        ranked.score,
        ranked.match_total
    FROM ranked
    JOIN public.stories s ON s.id = ranked.matched_id
    ORDER BY ranked.score DESC, s.id
    LIMIT match_count
    OFFSET result_offset;
END;
$$;

REVOKE ALL ON FUNCTION public.hybrid_story_search(
    TEXT, TEXT, VECTOR, BOOLEAN, INT, INT, story_variant, emotion_type, INT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hybrid_story_search(
    TEXT, TEXT, VECTOR, BOOLEAN, INT, INT, story_variant, emotion_type, INT
) TO service_role;
