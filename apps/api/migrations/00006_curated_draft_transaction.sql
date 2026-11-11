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
