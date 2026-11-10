-- Ensure original document uploads use a private Supabase Storage bucket.
INSERT INTO storage.buckets (id, name, public)
VALUES ('raw-documents', 'raw-documents', false)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    public = false;
