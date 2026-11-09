# AGENTS.md: AI Pair Programming and Engineering Guidelines

This repository houses the **Four Plus Story Library**, a platform for discovering, analyzing, curating, and sharing autobiographical 4+ stories from literature and transcripts.

All AI coding assistants (including Antigravity, Claude, Cursor, Copilot, etc.) working on this repository **must strictly adhere** to the following instructions, constraints, and architecture boundaries.

---

## 1. Core Domain Principles & Hard Invariants

1. **Never Publish AI Discoveries Without Human Approval**:
   - AI discovery is strictly a proposal mechanism.
   - All AI-extracted story candidates must default to status `discovered_pending_review`.
   - Editorial approval alone does not grant public access; publication requires `status = 'approved'`, `visibility = 'public'`, and adherence to document publication rights.
2. **Preserve Complete Original Story Text and Source References**:
   - Original verbatim text is retrieved from extracted document text using verified boundary offsets and must never be mutated or summarized in place.
   - Support multiple source spans per story (`story_source_spans`) for narratives crossing page breaks or split by sidebars.
   - Document source references (filename, file hash, page start/end, character offset start/end, book title, author, transcript timestamp) must remain immutable and linked.
   - Original documents, pages, and chunks must never be accidentally deleted through cascading story deletions (`ON DELETE RESTRICT`).
3. **Store AI Analysis Separately from Story Content**:
   - Original story text is stored in the core story table (`stories`).
   - Human-approved curated telling versions are stored separately (`story_curated_versions`).
   - AI evaluations (classification scores, confidence ratings, criteria evaluations, reasoning) are stored in distinct analysis records (`story_ai_evaluations`).
   - Story variants (`story_variant_assignments`), emotions (`story_emotions`), and STEP analyses (`story_step_analyses`) are stored in distinct tables.
4. **Separate the Classification Dimensions**:
   - Do not treat classification dimensions as interchangeable:
     1. Autobiographical status (`is_autobiographical`).
     2. Overall 4+ classification (`four_plus_classification`: `confirmed_4_plus`, `not_4_plus`, `uncertain_needs_review`).
     3. Individual 5 criteria results (`met`, `partially_met`, `not_met`, `uncertain`, `not_applicable`).
     4. Story variant assignments (zero, one, or multiple variants per story).
     5. Emotion classifications (multiple emotions, energy levels, progression).
     6. STEP analysis (Setting, Trigger, Emotion & Body Sensations, Point).
     7. Storytelling quality and length metadata (word count, spoken duration, >600 word advisory).
   - A story can be autobiographical without being 4+.
   - A story can have a variant (such as Appreciation / Joy-Spreading) without qualifying as a standard 4+.
   - Do not automatically classify a story as 4+ merely because it has a variant.
5. **The Authoritative Four Story Variants**:
   - The four authoritative variants are:
     1. **Return to Joy (Level 3)** (`return_to_joy`)
     2. **Acting Like Myself (Level 4)** (`acting_like_myself`)
     3. **Godsight / Immanuel** (`godsight_immanuel`)
     4. **Appreciation / Joy-Spreading** (`appreciation_joy_spreading`)
   - Remove/prohibit: "Distress to Peace", "Rupture and Repair", "Endurance & Hope" as variants (these may exist only as descriptive thematic tags).
   - A story may have zero, one, or multiple variants.
   - Variant classification is independent of 4+ classification.
6. **Agreed STEP Framework**:
   - **S — Setting**: Time, place, context, people present, relational atmosphere.
   - **T — Trigger**: Specific incident, word, event, or disruption catalyzing the reaction.
   - **E — Emotion & Body Sensations**: Explicit feelings AND somatic sensations (e.g. tight chest, racing heart, knot in stomach, tears). Missing sensations must be recorded as missing/null!
   - **P — Point**: The core relational, spiritual, or life lesson/takeaway of the story.
   - Thoughts and relational presence may be captured as supplementary analysis fields, but never substituted for STEP.
7. **The Big 6 Emotion Taxonomy & Somatic Rigor**:
   - High-energy: **Fear**, **Anger**.
   - Low-energy: **Sadness**, **Shame**, **Disgust**, **Hopeless Despair**.
   - Additional emotions permitted: Joy, Gratitude, Peace, etc.
   - A story can contain multiple emotions and emotional progression.
   - The AI must identify explicit physical/body sensations and MUST NEVER infer or invent sensations not present in the source. Missing sensations are recorded as missing.
8. **AI Extraction Boundaries & Anti-Hallucination**:
   - The AI must NOT output the full verbatim story text in a field. Instead, it outputs boundary sentence identifiers, page/character offsets, and evidence quotes. The backend extracts the true verbatim text.
   - Never invent facts, characters, sensations, or emotions not explicitly supported by source text.
9. **Preserve Human Corrections and Review History**:
   - All human edits, approvals, rejects, and curated telling versions are captured in audited revision history (`story_human_reviews`).
10. **Story Length & Curated Telling Versions**:
    - Original story stores `original_word_count`, `estimated_spoken_duration_seconds`, and a length advisory when exceeding 600 words (`length_advisory_exceeds_600_words`).
    - AI may suggest a shorter curated version, but a human must review and approve it before publication.

---

## 2. Monorepo Architecture & Tech Stack

```text
four-plus-story/
├── apps/
│   ├── admin/       # Next.js 15+ App Router, React 19, TypeScript, Tailwind CSS, Supabase SSR
│   ├── api/         # FastAPI, Python 3.13, PyMuPDF, Pydantic v2, provider-agnostic AI layer
│   └── mobile/      # React Native, Expo SDK 52+, TypeScript, Supabase Client
├── packages/
│   ├── shared-types/# TypeScript definitions, Zod schemas, shared validation contracts
│   └── eslint-config/# ESLint and formatting standards
└── docs/            # Single source of architectural truth
```

### Approved Technologies
- **Monorepo**: pnpm workspaces + Turborepo.
- **Frontend Admin**: Next.js (TypeScript), Tailwind CSS.
- **Mobile**: React Native, Expo, TypeScript.
- **Backend API**: Python 3.13, FastAPI, PyMuPDF (`fitz`), Pydantic v2.
- **Database & Auth**: Supabase PostgreSQL with `pgvector` and Supabase Auth.
- **File Storage**: Supabase Storage buckets (`raw-documents`, `processed-texts`, `story-assets`).
- **Search**: PostgreSQL Full-Text Search (tsvector/tsquery) + pgvector (cosine/HNSW).
- **Validation**: Pydantic v2 (Python) and Zod (TypeScript). Shared schemas must stay in lockstep.

---

## 3. Engineering Workflows & Guardrails

### Type Safety & Schema Synchronization
- Any change to database schemas must be reflected across all four locations:
  1. `docs/DATABASE_SCHEMA.md`
  2. Supabase migration files in `apps/api/migrations/`
  3. Pydantic models in `apps/api/app/schemas/`
  4. Zod schemas and TypeScript interfaces in `packages/shared-types/`

### AI Service Provider Abstraction
- Never hardcode vendor-specific API calls directly into business logic.
- Use the provider-independent AI layer (`apps/api/app/services/ai/base.py`) with adapter implementations (Anthropic, OpenAI, Gemini, Local/Ollama).
- All AI responses must be validated against strict Pydantic schemas using structured JSON output.

### Running Commands & Sandbox Rules
- Commands must be run inside the sandboxed environment first.
- Do not run long-running daemons synchronously; background them with appropriate wait times.
- Ensure linting (`pnpm run lint`) and type checks (`pnpm run typecheck`, `mypy`) pass before marking tasks as complete.

---

## 4. Documentation First

- Every architectural decision, schema modification, or pipeline evolution must be documented in the corresponding `docs/*.md` file before or alongside code changes.
- Refer to `docs/DEVELOPMENT_ROADMAP.md` and `docs/IMPLEMENTATION_STATUS.md` to track current task boundaries.
