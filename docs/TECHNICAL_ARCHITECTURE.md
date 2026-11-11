# TECHNICAL_ARCHITECTURE.md: Technical Architecture Blueprint

## 1. System Architecture Overview

The **Four Plus Story Library** architecture is built as a modular monorepo leveraging cloud-native PostgreSQL (Supabase), high-performance Python services for document parsing and AI orchestration, a responsive Next.js administration portal, and a cross-platform Expo (React Native) mobile application.

```mermaid
graph TB
    subgraph Clients["Client Applications"]
        Mobile["Mobile App (React Native / Expo)<br/>iOS & Android (Public & Registered Church Users)"]
        Admin["Admin Workbench (Next.js 15+)<br/>Curators, Reviewers & Super Admins"]
    end

    subgraph Edge["Edge & Security Layer"]
        CDN["Global Edge CDN / Vercel"]
        AuthGateway["Supabase Auth / JWT Validation"]
        RLS["PostgreSQL RLS<br/>(Enforces Approval + Visibility + Rights)"]
    end

    subgraph BackendAPI["Backend Core Services (Python / FastAPI)"]
        IngestRouter["Document & Ingestion API"]
        JobWorker["Job & Event Engine<br/>(processing_jobs & events)"]
        PipelineWorker["Extraction & Evaluation Engine"]
        SearchRouter["Hybrid Search Engine"]
        AdminRouter["Editorial & Curation API"]
        DocParser["PyMuPDF Document Parser<br/>(Decomposes into pages & chunks)"]
        TextRetriever["Verified Span & Boundary Assembler"]
        AIAdapter["Provider-Agnostic AI Service Layer"]
    end

    subgraph DataLayer["Storage & Database (Supabase PostgreSQL)"]
        DocTables[("Documents, Pages, Chunks<br/>(ON DELETE RESTRICT protection)")]
        StoryTables[("Stories & Source Spans<br/>(Original Text, Spans, Curated Versions)")]
        AnalysisTables[("Evaluations, Variants, Emotions, STEP<br/>(Orthogonal Analysis Records)")]
        PGVector[("pgvector HNSW Extension<br/>(Configurable-dim Story Embeddings)")]
        FTS[("PostgreSQL Full-Text Search<br/>(GIN tsvector indexes)")]
        StorageBucket[("Supabase Storage Buckets<br/>(raw-documents, processed-texts)")]
    end

    subgraph ExternalAI["External AI Model Providers"]
        Anthropic["Claude 3.5 Sonnet / Haiku"]
        OpenAI["GPT-4o / GPT-4o-mini"]
        Gemini["Gemini 2.5 Flash / Pro"]
        LocalLLM["Local Ollama / vLLM (Optional)"]
    end

    Mobile -->|HTTPS / REST| SearchRouter
    Mobile -->|HTTPS / Supabase SDK| StoryTables
    Admin -->|HTTPS / Next.js Server Actions| BackendAPI
    Admin -->|Supabase SSR Client| StoryTables
    
    BackendAPI --> DocParser
    BackendAPI --> TextRetriever
    BackendAPI --> AIAdapter
    AIAdapter --> Anthropic
    AIAdapter --> OpenAI
    AIAdapter --> Gemini
    AIAdapter --> LocalLLM

    BackendAPI --> DocTables
    BackendAPI --> StoryTables
    BackendAPI --> AnalysisTables
    BackendAPI --> PGVector
    BackendAPI --> FTS
    BackendAPI --> StorageBucket
```

---

## 2. Ingestion, Multi-Span Extraction, & Curation Pipeline

The document ingestion pipeline transforms raw documents into structured document pages, semantic chunks, candidate story boundaries, and verified multi-span stories.

```mermaid
sequenceDiagram
    autonumber
    actor Curator as Human Curator
    participant AdminApp as Admin Portal (Next.js)
    participant API as FastAPI Ingestion Engine
    participant DB as PostgreSQL DB
    participant AI as Provider-Agnostic AI Layer

    Curator->>AdminApp: Upload Book PDF or TXT Transcript
    AdminApp->>API: POST /api/v1/documents/upload (multipart)
    API->>DB: Insert document metadata & create processing_job
    API->>API: PyMuPDF parses document into document_pages
    API->>DB: Bulk insert document_pages
    API->>API: Sliding-window chunking into document_chunks
    API->>DB: Bulk insert document_chunks
    
    loop For each candidate chunk window
        API->>AI: Stage 1: Detect Story Candidate Boundaries (Start/End Sentences & Offsets)
        AI-->>API: Candidate sentence markers, offsets, evidence quotes (NO verbatim text output)
    end

    loop For each detected story candidate
        API->>API: Backend retrieves exact text from document_pages across boundary offsets
        API->>DB: Insert story & story_source_spans (status: discovered_pending_review)
        API->>AI: Stage 2: Evaluate 5 Criteria, Assign Variants, Classify Emotions & Somatics, Extract STEP
        AI-->>API: Structured Analysis (5-way criteria, variants array, emotions & somatics, STEP: S/T/E/P)
        API->>DB: Insert story_ai_evaluations, story_variant_assignments, story_emotions, story_step_analyses
        API->>AI: Stage 3: Generate Embedding (text, variant, emotions, STEP point)
        AI-->>API: Embedding vector (with model, version, content_hash)
        API->>DB: Insert story_embeddings
    end

    API->>DB: Complete processing_job
    API-->>AdminApp: Ingestion Complete (Found N candidate stories)
    Curator->>AdminApp: Review candidates, verify boundaries, approve/edit, create curated telling version
```

### Pipeline Key Invariants
1. **No LLM Verbatim Reproduction**: The LLM outputs boundary markers, sentence identifiers, and quotes. The backend engine resolves character coordinates against `document_pages` to extract the true verbatim source text.
2. **Multi-Span Boundary Assembly**: Stories spanning page boundaries or split by sidebars are represented as ordered `story_source_spans` linked to parent `stories`.
3. **Cascade Deletion Protection**: Documents, pages, and chunks are protected by `ON DELETE RESTRICT`. Deleting a story never destroys underlying source document pages.
4. **Independent Analysis Insertion**: AI evaluations, variant assignments (0 to 4), emotion classifications, and STEP analyses are stored in separate relational records.

---

## 3. Separation of Analytical Dimensions

```mermaid
classDiagram
    class Story {
        +UUID id
        +UUID document_id
        +String title
        +String original_text
        +Integer original_word_count
        +Integer estimated_spoken_duration_seconds
        +Boolean length_advisory_exceeds_800_words
        +Boolean is_autobiographical
        +StoryStatus status
        +StoryVisibility visibility
    }

    class StorySourceSpan {
        +UUID id
        +UUID story_id
        +UUID document_page_id
        +Integer span_order
        +Integer page_number
        +Integer char_start
        +Integer char_end
        +String verbatim_text
    }

    class StoryCuratedVersion {
        +UUID id
        +UUID story_id
        +String curated_title
        +String curated_text
        +Integer curated_word_count
        +Integer curated_spoken_duration_seconds
        +Boolean is_approved
    }

    class StoryAIEvaluation {
        +UUID id
        +FourPlusClassification overall_classification
        +Float overall_confidence
        +JSONB criteria_evaluations
        +String reasoning_summary
    }

    class StoryVariantAssignment {
        +UUID id
        +StoryVariant variant
        +Float confidence
        +String evidence_quote
        +String reasoning
    }

    class StoryEmotion {
        +UUID id
        +EmotionType emotion
        +EmotionEnergyLevel energy_level
        +ProgressionStage progression_stage
        +String evidence_quote
        +Array sensations_identified
        +Boolean sensations_missing
    }

    class StoryStepAnalysis {
        +UUID id
        +String setting
        +String trigger
        +String emotion_and_body_sensations
        +String point
        +String internal_thoughts
        +String relational_presence
    }

    Story "1" -- "1..*" StorySourceSpan : assembled from
    Story "1" -- "0..*" StoryCuratedVersion : curated into
    Story "1" -- "0..*" StoryAIEvaluation : evaluated by
    Story "1" -- "0..*" StoryVariantAssignment : assigned
    Story "1" -- "0..*" StoryEmotion : expresses
    Story "1" -- "0..1" StoryStepAnalysis : analyzed by
```

---

## 4. The Authoritative Four Story Variants

Variants are assigned via `story_variant_assignments` (0, 1, or multiple per story):
1. **Return to Joy (Level 3)** (`return_to_joy`): Traces moving from distress/negative emotions back to joy and peace through relational co-regulation.
2. **Acting Like Myself (Level 4)** (`acting_like_myself`): Sustaining or restoring core relational identity and integrity under stress.
3. **Godsight / Immanuel** (`godsight_immanuel`): Perceiving God's active, personal presence, comfort, or perspective directly within the event.
4. **Appreciation / Joy-Spreading** (`appreciation_joy_spreading`): Sharing and savoring relational delight, wonder, and gratitude without requiring distress.

---

## 5. Big 6 Emotion Taxonomy & Somatic Architecture

- **High-Energy Emotions**: `fear`, `anger`
- **Low-Energy Emotions**: `sadness`, `shame`, `disgust`, `hopeless_despair`
- **Connective/Positive Emotions**: `joy`, `gratitude`, `peace`, `other`
- **Emotional Progression Stages**: `initial`, `escalation`, `peak`, `shift`, `resolving`
- **Somatic Analysis**: Explicit physical sensations (e.g. tight chest, racing heart, shallow breathing, clenched jaw, knot in stomach, warmth, tears, relaxed shoulders).
  - *Hard Invariant*: AI must never invent sensations. Missing sensations are recorded as missing/null (`sensations_missing: true`).

---

## 6. Restored STEP Framework

The authentic 4-part **STEP** framework is modeled as:
- **S — Setting**: Time, place, context, people present, relational atmosphere.
- **T — Trigger**: The specific incident, word, event, or disruption catalyzing the reaction.
- **E — Emotion & Body Sensations**: Explicit feelings AND somatic body sensations.
- **P — Point**: The core relational, spiritual, or life lesson/takeaway of the story.

*Supplementary Analysis Fields*: `internal_thoughts` and `relational_presence` may be captured optionally, but never replace or redefine Setting, Trigger, Emotion & Sensations, or Point.

---

## 7. Security, RLS, & Search Path Architecture

- **PostgreSQL Row-Level Security (RLS)**:
  - Editorial approval alone does not grant public access. Publication requires:
    - `stories.status = 'approved'`
    - `stories.visibility = 'public'`
    - `documents.rights_status IN ('public_domain', 'licensed', 'fair_use_educational')`
    - `documents.publication_restrictions IS NULL`
  - Registered users can view `stories.visibility IN ('public', 'registered_users')` when `status = 'approved'`.
  - Curators/Admins can view all records across all tiers.
- **Function Security**:
  - All `SECURITY DEFINER` stored procedures must include explicit `SET search_path = public, auth` to prevent search path poisoning.
  - Execution privileges are explicitly revoked from public roles and granted only to authorized service roles.

---

## 8. Vector Embeddings & Unhardcoded Dimensions

- **Vector Dimension**: The current `story_embeddings` column and HNSW index are fixed at 1536 dimensions. The configured provider/model must return 1536-dimensional vectors; changing dimensions requires a coordinated database migration and embedding rebuild.
- **Embedding Metadata**: Every embedding record stores `embedding_model`, `model_version`, and `content_hash` to support seamless re-indexing when models evolve.
