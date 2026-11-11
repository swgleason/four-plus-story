# PRODUCT_REQUIREMENTS.md: Product Requirements & Acceptance Criteria

## 1. Product Requirements Matrix

| ID | Category | Requirement Description | Priority | Target Interface |
|---|---|---|---|---|
| **PR-01** | Architecture | Single unified story library accessible across mobile and web interfaces | P0 | Database / Mobile / Admin |
| **PR-02** | Access & Visibility | Multi-tier visibility (internal, registered, public) conditioned on approval and document rights | P0 | Database / Mobile / Admin |
| **PR-03** | Governance | Invitation-only access for administrators, reviewers, and curators | P0 | Admin Web App |
| **PR-04** | Ingestion & Spans | Ingestion of PDF books and TXT transcripts into pages, chunks, and multi-span stories | P0 | API / Admin Web App |
| **PR-05** | Editorial Workflow | Mandatory human review; approval separate from visibility and rights clearance | P0 | Admin Web App / API |
| **PR-06** | Data Integrity | Immutable preservation of original story text, word counts, and protected source lineage | P0 | Database / Storage |
| **PR-07** | Separation of Dimensions | Independent tracking of autobiographical status, 4+ classification, variants, emotions, and STEP | P0 | Database / AI Engine |
| **PR-08** | Story Variants | Authoritative 4 variants: Return to Joy, Acting Like Myself, Godsight/Immanuel, Joy-Spreading | P0 | AI Engine / API |
| **PR-09** | Emotion & Somatics | Big 6 emotions (high/low energy) + positive emotions, progressions, and strict somatic analysis | P0 | AI Engine / API |
| **PR-10** | STEP Analysis | Restored STEP framework: Setting, Trigger, Emotion & Body Sensations, Point | P0 | AI Engine / Mobile / Admin |
| **PR-11** | Story Length & Curation | Word count, spoken duration, >800 word advisory, and separate human-approved curated versions | P0 | Database / Admin / Mobile |
| **PR-12** | Natural Language Search | Hybrid search across original and curated text, emotions, variants, and STEP components | P0 | API / Mobile App |

---

## 2. Detailed Functional Requirements

### PR-01: One Shared Story Library
- **Description**: All approved stories reside in a central, multi-tenant capable repository. Changes approved by administrators immediately reflect in the shared pool according to visibility and rights settings.
- **Acceptance Criteria**:
  1. A single PostgreSQL database hosts core story records, documents, evaluations, and curated versions.
  2. Mobile and Admin applications query the identical API endpoints or Supabase PostgREST views.
  3. No duplicate story silos exist across mobile and web platforms.

### PR-02: Multi-Tier Visibility & Publication Rights
- **Description**: Editorial approval alone does NOT automatically make a story public. A story is published only when it satisfies approval, visibility tier, and source document rights.
- **Acceptance Criteria**:
  1. Visibility tiers supported: `internal_only`, `registered_users`, `public`.
  2. Document rights statuses supported: `public_domain`, `licensed`, `restricted_internal`, `fair_use_educational`.
  3. A story is accessible to unauthenticated public users if and only if:
     - `stories.status = 'approved'`
     - `stories.visibility = 'public'`
     - `documents.rights_status IN ('public_domain', 'licensed', 'fair_use_educational')`
     - `documents.publication_restrictions IS NULL`
  4. Registered church members can access stories where `visibility IN ('public', 'registered_users')` with `status = 'approved'`.
  5. Curators and admins have access to all stories across all tiers.

### PR-03: Invitation-Only Administration and Review
- **Description**: The Next.js administration portal is protected by role-based access control. Public self-registration for admin roles is strictly prohibited.
- **Acceptance Criteria**:
  1. Administrative accounts can only be created via invitation token issued by a Super Admin.
  2. Roles supported: `super_admin`, `curator`, `reviewer`, `church_member`, `public_guest`.
  3. RLS policies and Next.js middleware reject any user without an active admin/curator role claim.

### PR-04: Document Ingestion, Structured Pages, Chunks, & Multi-Span Stories
- **Description**: Ingests PDF books and TXT transcripts into structured document records, individual pages (`document_pages`), and semantic chunks (`document_chunks`). Stories can be composed of one or more source spans (`story_source_spans`).
- **Acceptance Criteria**:
  1. Upload accepts `.pdf` and `.txt` files up to 100MB.
  2. Processing decomposes documents into `document_pages` with verbatim text and metadata, and `document_chunks` with token counts and overlap.
  3. Tracks asynchronous progress via `processing_jobs` and `processing_job_events`.
  4. Supports narratives split across page boundaries or interrupted by sidebars via linked `story_source_spans` ordered by `span_order`.
  5. Deleting a story MUST NOT cascade delete original documents or document pages (`ON DELETE RESTRICT`).

### PR-05: Mandatory Human Approval Workflow
- **Description**: No AI-discovered story candidate is ever displayed to end users without explicit human sign-off.
- **Acceptance Criteria**:
  1. Every story candidate extracted by AI enters the system with status `discovered_pending_review`.
  2. The admin portal provides an approval queue showing candidate boundaries, criteria scores, emotion progressions, somatics, and STEP analysis.
  3. A curator can `Approve`, `Request Revision`, `Edit & Approve`, or `Reject`.
  4. Public endpoints enforce approval, visibility, and rights verification via RLS.

### PR-06: Verbatim Story Text & Source Lineage Preservation
- **Description**: The exact wording of the author/speaker is extracted directly from document text using verified boundary offsets and preserved immutably.
- **Acceptance Criteria**:
  1. The AI does NOT output the complete story in a `verbatim_text` field; the backend retrieves the exact text from extracted pages using verified start/end boundaries.
  2. The database field `original_text` is immutable once verified.
  3. Lineage records: `document_id`, linked `story_source_spans` (`page_number`, `char_start`, `char_end`), author, publication year, and document SHA-256 hash.

### PR-07: Separation of Classification Dimensions
- **Description**: The system strictly separates distinct analytical dimensions and never treats them as interchangeable.
- **Acceptance Criteria**:
  1. **Autobiographical Status**: `is_autobiographical` (boolean/status), evaluated independently. A story may be autobiographical without being 4+.
  2. **Overall 4+ Classification**: `four_plus_classification` (`confirmed_4_plus`, `not_4_plus`, `uncertain_needs_review`).
  3. **Five Criteria Evaluations**: Each criterion evaluated as `met`, `partially_met`, `not_met`, `uncertain`, or `not_applicable`, accompanied by confidence, evidence quote, and reasoning.
  4. **Story Variants**: Independent of 4+ status. A story may have 0, 1, or multiple variants. Having a variant does not automatically make a story 4+.
  5. **Emotion Classifications**: Tracks multiple emotions, energy levels, and emotional progressions.
  6. **STEP Analysis**: Dedicated Setting, Trigger, Emotion & Body Sensations, Point fields.
  7. **Storytelling Quality**: Word count, duration, and length advisories.

### PR-08: The Authoritative Four Story Variants
- **Description**: Stories are classified against the four authoritative Life Model / Thrive Today variants:
  1. **Return to Joy (Level 3)** (`return_to_joy`): Recounting how the narrator moved from negative emotions back into relational joy and peace.
  2. **Acting Like Myself (Level 4)** (`acting_like_myself`): Sustaining or restoring core relational identity and values under stress or temptation ("acting like the person God made me to be").
  3. **Godsight / Immanuel** (`godsight_immanuel`): Perceiving God’s active presence, perspective, or comfort directly within an event.
  4. **Appreciation / Joy-Spreading** (`appreciation_joy_spreading`): Recalling and sharing relational delight, gratitude, and wonder without requiring distress.
- **Acceptance Criteria**:
  1. The former variants ("Distress to Peace", "Rupture and Repair", "Endurance & Hope") are removed from the variant taxonomy.
  2. A story may be assigned **zero, one, or multiple variants**.
  3. Each variant assignment is stored in `story_variant_assignments` with `confidence`, `evidence_quote`, and `reasoning`.
  4. Variant assignment is independent of overall 4+ classification.

### PR-09: Big 6 Emotion Taxonomy & Somatic Rigor
- **Description**: Structured emotion extraction covering high-energy and low-energy negative emotions and positive connective emotions, with mandatory somatic sensation tracking.
- **Acceptance Criteria**:
  1. Emotion categories:
     - **High-energy**: `fear`, `anger`.
     - **Low-energy**: `sadness`, `shame`, `disgust`, `hopeless_despair`.
     - **Additional**: `joy`, `gratitude`, `peace`, `other`.
  2. A story can contain multiple emotions and an emotional progression (`initial`, `peak`, `shift`, `resolving`).
  3. **Somatic Analysis**: AI must identify explicit physical sensations (e.g. tight chest, racing heart, shallow breathing, clenched jaw, knot in stomach, warmth, tears, relaxed shoulders).
  4. **Zero Somatic Hallucination**: Missing sensations must be recorded as missing/null. The AI must never invent physical sensations.

### PR-10: Restored STEP Framework
- **Description**: Structured extraction of the authentic 4-part STEP framework:
  - **S — Setting**: Time, place, context, people present, relational atmosphere.
  - **T — Trigger**: The specific incident, word, event, or disruption that catalyzed the reaction.
  - **E — Emotion & Body Sensations**: Explicit named feelings AND visceral physical body sensations.
  - **P — Point**: The core relational, spiritual, or life lesson/takeaway of the story.
- **Acceptance Criteria**:
  1. The previous Situation / Thought / Emotion / Presence framework is fully replaced by Setting / Trigger / Emotion & Body Sensations / Point.
  2. Supplementary fields (`internal_thoughts`, `relational_presence`) may be captured optionally, but never substituted for STEP fields.
  3. Missing STEP elements must be recorded as missing or null.

### PR-11: Story Length, Spoken Duration, & Curated Telling Versions
- **Description**: Authentic oral storytelling requires manageable length. The system tracks metrics, flags overly long stories, and manages curated telling versions.
- **Acceptance Criteria**:
  1. Tracks `original_word_count` and `estimated_spoken_duration_seconds` (calculated at ~140 words per minute).
  2. Automatically flags `length_advisory_exceeds_800_words = TRUE` when word count exceeds 800 words (~5.7 minutes spoken).
  3. Supports separate `story_curated_versions` storing streamlined, spoken-friendly adaptations.
  4. The AI may propose a curated telling, but it MUST NOT overwrite the original text.
  5. A curated version requires explicit human approval before becoming available for reading or sharing.

### PR-12: Natural Language Hybrid Search
- **Description**: Natural language querying across both original text, curated versions, STEP components, variants, and emotions.
- **Acceptance Criteria**:
  1. Hybrid search combines PostgreSQL full-text search with pgvector semantic embeddings via Reciprocal Rank Fusion (RRF).
  2. Embeddings are stored with model name, version, and content hash; vector dimensions are not hard-coded.
  3. Search results strictly enforce RLS approval, visibility, and rights filters.

---

## 3. Non-Functional Requirements (NFRs)

| NFR Category | Requirement | Target Metric |
|---|---|---|
| **Performance** | Reading API response time | P95 < 150ms |
| **Search Latency** | Hybrid search execution | P95 < 250ms |
| **Document Processing** | Processing a 300-page PDF into pages, chunks, and spans | < 90 seconds total pipeline |
| **Availability** | System uptime | 99.9% uptime |
| **Data Integrity** | Cascade protection on source documents | Zero accidental deletions of documents or pages |
| **Security & Privacy** | Search path protection & RLS verification | 100% of tables protected by RLS; explicit search paths on all SECURITY DEFINER functions |
| **Accessibility** | Mobile & Web UI compliance | WCAG 2.1 Level AA |
| **Spoken Story Standards** | Story length advisory | Flag applied to all stories > 800 words |
