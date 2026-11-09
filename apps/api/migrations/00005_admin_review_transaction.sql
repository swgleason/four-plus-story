CREATE OR REPLACE FUNCTION public.admin_review_story(
    p_story_id UUID,
    p_reviewer_user_id UUID,
    p_action TEXT,
    p_visibility story_visibility,
    p_notes TEXT,
    p_override_title TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
DECLARE
    v_story public.stories%ROWTYPE;
    v_document public.documents%ROWTYPE;
    v_next_status public.story_status;
    v_next_visibility public.story_visibility;
    v_new_state JSONB;
    v_now TIMESTAMPTZ := NOW();
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

    SELECT * INTO v_story
    FROM public.stories
    WHERE id = p_story_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Story not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_story.status NOT IN ('discovered_pending_review', 'under_review') THEN
        RAISE EXCEPTION 'Story is no longer awaiting review' USING ERRCODE = '40001';
    END IF;

    SELECT * INTO v_document
    FROM public.documents
    WHERE id = v_story.document_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Source document is missing' USING ERRCODE = '23503';
    END IF;

    CASE p_action
        WHEN 'approve', 'edit_and_approve' THEN
            v_next_status := 'approved';
            v_next_visibility := p_visibility;
            IF v_next_visibility <> 'internal_only'
               AND (
                   v_document.rights_status NOT IN (
                       'public_domain', 'licensed', 'fair_use_educational'
                   )
                   OR v_document.publication_restrictions IS NOT NULL
               ) THEN
                RAISE EXCEPTION 'Document rights must be cleared and publication restrictions removed'
                    USING ERRCODE = '23514';
            END IF;
        WHEN 'reject' THEN
            v_next_status := 'rejected';
            v_next_visibility := 'internal_only';
        WHEN 'request_revision' THEN
            v_next_status := 'under_review';
            v_next_visibility := 'internal_only';
        ELSE
            RAISE EXCEPTION 'Unsupported editorial action' USING ERRCODE = '22023';
    END CASE;

    UPDATE public.stories AS updated_story
    SET status = v_next_status,
        visibility = v_next_visibility,
        title = CASE
            WHEN p_action = 'edit_and_approve'
                 AND NULLIF(BTRIM(p_override_title), '') IS NOT NULL
            THEN BTRIM(p_override_title)
            ELSE v_story.title
        END,
        approved_by_user_id = CASE
            WHEN v_next_status = 'approved' THEN p_reviewer_user_id
            ELSE NULL
        END,
        approved_at = CASE WHEN v_next_status = 'approved' THEN v_now ELSE NULL END
    WHERE id = p_story_id
    RETURNING TO_JSONB(updated_story) INTO v_new_state;

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
        p_action,
        TO_JSONB(v_story),
        v_new_state,
        p_notes
    );

    RETURN JSONB_BUILD_OBJECT(
        'story_id', p_story_id,
        'status', v_next_status,
        'visibility', v_next_visibility,
        'approved_at', CASE WHEN v_next_status = 'approved' THEN v_now ELSE NULL END,
        'approved_by_user_id', CASE
            WHEN v_next_status = 'approved' THEN p_reviewer_user_id
            ELSE NULL
        END
    );
END;
$$;

REVOKE ALL ON FUNCTION public.admin_review_story(
    UUID, UUID, TEXT, story_visibility, TEXT, TEXT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_review_story(
    UUID, UUID, TEXT, story_visibility, TEXT, TEXT
) TO service_role;
