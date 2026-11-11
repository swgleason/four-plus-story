DROP INDEX IF EXISTS public.idx_stories_length_advisory;

DROP FUNCTION IF EXISTS public.hybrid_story_search(
    TEXT, TEXT, VECTOR, BOOLEAN, INT, INT, story_variant, emotion_type, INT
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'stories'
          AND column_name = 'length_advisory_exceeds_600_words'
    ) THEN
        ALTER TABLE public.stories
            DROP COLUMN length_advisory_exceeds_600_words;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'stories'
          AND column_name = 'length_advisory_exceeds_800_words'
    ) THEN
        ALTER TABLE public.stories
            ADD COLUMN length_advisory_exceeds_800_words BOOLEAN
            GENERATED ALWAYS AS (original_word_count > 800) STORED;
    END IF;
END;
$$;

CREATE INDEX idx_stories_length_advisory
    ON public.stories(length_advisory_exceeds_800_words);

CREATE FUNCTION public.hybrid_story_search(
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
    length_advisory_exceeds_800_words BOOLEAN,
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
        s.length_advisory_exceeds_800_words,
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

CREATE OR REPLACE FUNCTION public.admin_save_curated_draft(
    p_story_id UUID,
    p_reviewer_user_id UUID,
    p_curated_title TEXT,
    p_curated_text TEXT,
    p_editorial_notes TEXT,
    p_version_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
DECLARE
    v_version public.story_curated_versions%ROWTYPE;
    v_previous_state JSONB := '{}'::JSONB;
    v_new_state JSONB;
    v_word_count INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.user_profiles
        WHERE id = p_reviewer_user_id
          AND role IN ('super_admin', 'curator')
    ) THEN
        RAISE EXCEPTION 'Curator or administrator access is required'
            USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.stories WHERE id = p_story_id) THEN
        RAISE EXCEPTION 'Story not found' USING ERRCODE = 'P0002';
    END IF;
    IF NULLIF(BTRIM(p_curated_title), '') IS NULL
       OR NULLIF(BTRIM(p_curated_text), '') IS NULL THEN
        RAISE EXCEPTION 'Curated title and text must not be blank'
            USING ERRCODE = '22023';
    END IF;

    v_word_count := CARDINALITY(
        REGEXP_SPLIT_TO_ARRAY(BTRIM(p_curated_text), '\s+')
    );

    IF p_version_id IS NULL THEN
        INSERT INTO public.story_curated_versions (
            story_id,
            curated_title,
            curated_text,
            curated_word_count,
            curated_spoken_duration_seconds,
            editorial_notes,
            is_approved
        )
        VALUES (
            p_story_id,
            BTRIM(p_curated_title),
            BTRIM(p_curated_text),
            v_word_count,
            CEIL(v_word_count * 60.0 / 140)::INTEGER,
            p_editorial_notes,
            FALSE
        )
        RETURNING * INTO v_version;
    ELSE
        SELECT * INTO v_version
        FROM public.story_curated_versions
        WHERE id = p_version_id
          AND story_id = p_story_id
          AND is_approved = FALSE
        FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Unapproved curated draft not found'
                USING ERRCODE = 'P0002';
        END IF;

        v_previous_state := TO_JSONB(v_version);
        UPDATE public.story_curated_versions AS updated_version
        SET curated_title = BTRIM(p_curated_title),
            curated_text = BTRIM(p_curated_text),
            curated_word_count = v_word_count,
            curated_spoken_duration_seconds = CEIL(v_word_count * 60.0 / 140)::INTEGER,
            editorial_notes = p_editorial_notes,
            is_approved = FALSE,
            approved_by_user_id = NULL,
            approved_at = NULL
        WHERE id = p_version_id
        RETURNING updated_version.* INTO v_version;
    END IF;

    v_new_state := TO_JSONB(v_version);
    INSERT INTO public.story_human_reviews (
        story_id,
        reviewer_user_id,
        action,
        previous_state,
        new_state,
        reviewer_notes
    )
    VALUES (
        p_story_id,
        p_reviewer_user_id,
        'curate_version',
        v_previous_state,
        v_new_state,
        p_editorial_notes
    );

    RETURN v_new_state || JSONB_BUILD_OBJECT(
        'length_advisory_exceeds_800_words',
        v_word_count > 800
    );
END;
$$;

REVOKE ALL ON FUNCTION public.admin_save_curated_draft(
    UUID, UUID, TEXT, TEXT, TEXT, UUID
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_save_curated_draft(
    UUID, UUID, TEXT, TEXT, TEXT, UUID
) TO service_role;
