import { z } from "zod";

/**
 * Custom Enums
 */

// Authoritative Four Story Variants
export const StoryVariantEnum = z.enum([
  "return_to_joy",
  "acting_like_myself",
  "godsight_immanuel",
  "appreciation_joy_spreading",
]);
export type StoryVariant = z.infer<typeof StoryVariantEnum>;

// Story Lifecycle Status
export const StoryStatusEnum = z.enum([
  "discovered_pending_review",
  "under_review",
  "approved",
  "rejected",
  "archived",
]);
export type StoryStatus = z.infer<typeof StoryStatusEnum>;

// Story Visibility Tier
export const StoryVisibilityEnum = z.enum([
  "internal_only",
  "registered_users",
  "public",
]);
export type StoryVisibility = z.infer<typeof StoryVisibilityEnum>;

// Narrator gender classification
export const NarratorGenderEnum = z.enum(["male", "female", "unknown"]);
export type NarratorGender = z.infer<typeof NarratorGenderEnum>;

// Overall 4+ Classification
export const FourPlusClassificationEnum = z.enum([
  "confirmed_4_plus",
  "not_4_plus",
  "uncertain_needs_review",
]);
export type FourPlusClassification = z.infer<typeof FourPlusClassificationEnum>;

// 5-Way Individual Criterion Result
export const CriterionResultEnum = z.enum([
  "met",
  "partially_met",
  "not_met",
  "uncertain",
  "not_applicable",
]);
export type CriterionResult = z.infer<typeof CriterionResultEnum>;

// Big 6 Emotion Taxonomy + Connective States
export const EmotionTypeEnum = z.enum([
  "fear",
  "anger",
  "sadness",
  "shame",
  "disgust",
  "hopeless_despair",
  "joy",
  "gratitude",
  "peace",
  "other",
]);
export type EmotionType = z.infer<typeof EmotionTypeEnum>;

export const EmotionEnergyLevelEnum = z.enum([
  "high_energy",
  "low_energy",
  "positive_connective",
]);
export type EmotionEnergyLevel = z.infer<typeof EmotionEnergyLevelEnum>;

export const ProgressionStageEnum = z.enum([
  "initial",
  "escalation",
  "peak",
  "shift",
  "resolving",
]);
export type ProgressionStage = z.infer<typeof ProgressionStageEnum>;

// Document Rights Status
export const DocumentRightsStatusEnum = z.enum([
  "public_domain",
  "licensed",
  "restricted_internal",
  "fair_use_educational",
]);
export type DocumentRightsStatus = z.infer<typeof DocumentRightsStatusEnum>;

// User Roles
export const UserRoleEnum = z.enum([
  "super_admin",
  "curator",
  "reviewer",
  "church_member",
  "public_guest",
]);
export type UserRole = z.infer<typeof UserRoleEnum>;

// Document Types
export const DocumentTypeEnum = z.enum([
  "pdf_book",
  "pdf_article",
  "txt_transcript",
  "txt_story_note",
]);
export type DocumentType = z.infer<typeof DocumentTypeEnum>;

// Job Status
export const JobStatusEnum = z.enum([
  "pending",
  "processing",
  "completed",
  "failed",
  "cancelled",
]);
export type JobStatus = z.infer<typeof JobStatusEnum>;

/**
 * Five 4+ Evaluation Criteria Schemas
 */
export const CriterionEvaluationDetailSchema = z.object({
  result: CriterionResultEnum,
  confidence: z.number().min(0).max(1),
  evidence_quote: z.string(),
  reasoning: z.string(),
});
export type CriterionEvaluationDetail = z.infer<typeof CriterionEvaluationDetailSchema>;

export const EmotionalIntensityDetailSchema = CriterionEvaluationDetailSchema.extend({
  intensity_level: z.enum(["flat_detached", "appropriate_moderate", "overwhelming_flooding"]),
});
export type EmotionalIntensityDetail = z.infer<typeof EmotionalIntensityDetailSchema>;

export const ExplicitEmotionSensationDetailSchema = CriterionEvaluationDetailSchema.extend({
  emotions_identified: z.array(z.string()),
  sensations_identified: z.array(z.string()),
  sensations_missing: z.boolean(),
});
export type ExplicitEmotionSensationDetail = z.infer<typeof ExplicitEmotionSensationDetailSchema>;

export const CoRegulationDetailSchema = CriterionEvaluationDetailSchema.extend({
  coregulator_type: z.enum(["divine_god_jesus_spirit", "human_other", "both", "none"]),
});
export type CoRegulationDetail = z.infer<typeof CoRegulationDetailSchema>;

export const CriteriaBreakdownSchema = z.object({
  autobiographical_involvement: CriterionEvaluationDetailSchema,
  appropriate_emotional_intensity: EmotionalIntensityDetailSchema,
  explicit_emotion_and_body_sensations: ExplicitEmotionSensationDetailSchema,
  relational_co_regulation: CoRegulationDetailSchema,
  redemptive_outcome: CriterionEvaluationDetailSchema,
});
export type CriteriaBreakdown = z.infer<typeof CriteriaBreakdownSchema>;

/**
 * Story Variant Assignment Schema
 */
export const StoryVariantAssignmentSchema = z.object({
  variant: StoryVariantEnum,
  assignment_source: z.string().default("ai_proposed"),
  confidence: z.number().min(0).max(1),
  evidence_quote: z.string(),
  reasoning: z.string(),
});
export type StoryVariantAssignment = z.infer<typeof StoryVariantAssignmentSchema>;

/**
 * Structured Emotion & Somatics Schema
 */
export const StoryEmotionSchema = z.object({
  emotion: EmotionTypeEnum,
  energy_level: EmotionEnergyLevelEnum,
  progression_stage: ProgressionStageEnum,
  evidence_quote: z.string(),
  source_page: z.number().int().positive().nullable().optional(),
  source_char_offset: z.number().int().nonnegative().nullable().optional(),
  sensations_identified: z.array(z.string()).default([]),
  sensations_missing: z.boolean().default(false),
});
export type StoryEmotion = z.infer<typeof StoryEmotionSchema>;

/**
 * Restored STEP Analysis Schema
 * S — Setting: Time, place, context, people present, relational atmosphere
 * T — Trigger: Specific incident, word, event, or stimulus that sparked the reaction
 * E — Emotion & Body Sensations: Explicit feelings AND physical body sensations
 * P — Point: The core relational, spiritual, or life lesson/takeaway
 */
export const StepAnalysisSchema = z.object({
  setting: z.string().describe("S — Setting: Time, place, context, people present, relational atmosphere"),
  trigger: z.string().describe("T — Trigger: Specific incident, word, event, or stimulus that sparked the reaction"),
  emotion_and_body_sensations: z.string().describe("E — Emotion & Body Sensations: Explicit feelings AND physical body sensations"),
  point: z.string().describe("P — Point: The core relational, spiritual, or life lesson/takeaway"),
  internal_thoughts: z.string().nullable().optional().describe("Supplementary: Automatic cognitions, assumptions, or beliefs"),
  relational_presence: z.string().nullable().optional().describe("Supplementary: Relational presence, attunement, or comfort"),
});
export type StepAnalysis = z.infer<typeof StepAnalysisSchema>;

/**
 * Document Models
 */
export const DocumentSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  author: z.string().nullable().optional(),
  document_type: DocumentTypeEnum,
  source_file_path: z.string(),
  file_hash_sha256: z.string(),
  page_count: z.number().int().positive().nullable().optional(),
  rights_status: DocumentRightsStatusEnum,
  publication_restrictions: z.string().nullable().optional(),
  metadata: z.record(z.unknown()).default({}),
  created_by: z.string().uuid().nullable().optional(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type Document = z.infer<typeof DocumentSchema>;

export const DocumentPageSchema = z.object({
  id: z.string().uuid(),
  document_id: z.string().uuid(),
  page_number: z.number().int().positive(),
  extracted_text: z.string(),
  char_count: z.number().int().nonnegative(),
  metadata: z.record(z.unknown()).default({}),
  created_at: z.string().datetime(),
});
export type DocumentPage = z.infer<typeof DocumentPageSchema>;

export const DocumentChunkSchema = z.object({
  id: z.string().uuid(),
  document_id: z.string().uuid(),
  chunk_index: z.number().int().nonnegative(),
  token_count: z.number().int().positive(),
  text: z.string(),
  page_start: z.number().int().positive(),
  page_end: z.number().int().positive(),
  char_start: z.number().int().nonnegative(),
  char_end: z.number().int().positive(),
  created_at: z.string().datetime(),
});
export type DocumentChunk = z.infer<typeof DocumentChunkSchema>;

export const ProcessingJobEventSchema = z.object({
  id: z.string().uuid(),
  job_id: z.string().uuid(),
  stage: z.string(),
  level: z.enum(["info", "warn", "error"]),
  message: z.string(),
  details: z.record(z.unknown()).default({}),
  created_at: z.string().datetime(),
});
export type ProcessingJobEvent = z.infer<typeof ProcessingJobEventSchema>;

export const ProcessingJobSchema = z.object({
  id: z.string().uuid(),
  document_id: z.string().uuid().nullable().optional(),
  job_type: z.string(),
  status: JobStatusEnum,
  error_message: z.string().nullable().optional(),
  config: z.record(z.unknown()).default({}),
  events: z.array(ProcessingJobEventSchema).default([]),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type ProcessingJob = z.infer<typeof ProcessingJobSchema>;

/**
 * Multi-Span Source Schema
 */
export const StorySourceSpanSchema = z.object({
  id: z.string().uuid(),
  story_id: z.string().uuid(),
  document_page_id: z.string().uuid(),
  chunk_id: z.string().uuid().nullable().optional(),
  span_order: z.number().int().positive(),
  page_number: z.number().int().positive(),
  char_start: z.number().int().nonnegative(),
  char_end: z.number().int().positive(),
  verbatim_text: z.string(),
  created_at: z.string().datetime(),
});
export type StorySourceSpan = z.infer<typeof StorySourceSpanSchema>;

/**
 * Separate Curated Oral Telling Version Schema
 */
export const StoryCuratedVersionSchema = z.object({
  id: z.string().uuid(),
  story_id: z.string().uuid(),
  curated_title: z.string(),
  curated_text: z.string(),
  curated_word_count: z.number().int().positive(),
  curated_spoken_duration_seconds: z.number().int().positive(),
  is_approved: z.boolean(),
  approved_by_user_id: z.string().uuid().nullable().optional(),
  approved_at: z.string().datetime().nullable().optional(),
  editorial_notes: z.string().nullable().optional(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type StoryCuratedVersion = z.infer<typeof StoryCuratedVersionSchema>;

/**
 * Core Story Entity
 */
export const StorySchema = z.object({
  id: z.string().uuid(),
  document_id: z.string().uuid(),
  title: z.string(),
  original_text: z.string(),
  original_word_count: z.number().int().nonnegative(),
  estimated_spoken_duration_seconds: z.number().int().nonnegative(),
  length_advisory_exceeds_800_words: z.boolean(),
  is_autobiographical: z.boolean().nullable().optional(),
  narrator_gender: NarratorGenderEnum.default("unknown"),
  status: StoryStatusEnum,
  visibility: StoryVisibilityEnum,
  approved_by_user_id: z.string().uuid().nullable().optional(),
  approved_at: z.string().datetime().nullable().optional(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type Story = z.infer<typeof StorySchema>;

export const StoryDetailSchema = StorySchema.extend({
  document: z.object({
    id: z.string().uuid(),
    title: z.string(),
    author: z.string().nullable().optional(),
    rights_status: DocumentRightsStatusEnum,
    publication_restrictions: z.string().nullable().optional(),
  }),
  spans: z.array(StorySourceSpanSchema).default([]),
  assigned_variants: z.array(StoryVariantAssignmentSchema).default([]),
  emotions: z.array(StoryEmotionSchema).default([]),
  step_analysis: StepAnalysisSchema.nullable().optional(),
  curated_version: StoryCuratedVersionSchema.nullable().optional(),
});
export type StoryDetail = z.infer<typeof StoryDetailSchema>;

/**
 * AI Output Schemas (NO verbatim_text field!)
 */
export const CandidateStorySegmentSchema = z.object({
  first_sentence: z.string(),
  last_sentence: z.string(),
  approx_char_start: z.number().int().nonnegative(),
  approx_char_end: z.number().int().positive(),
});
export type CandidateStorySegment = z.infer<typeof CandidateStorySegmentSchema>;

export const CandidateStoryBoundarySchema = CandidateStorySegmentSchema.extend({
  tentative_title: z.string(),
  evidence_quote: z.string().min(1),
  source_segments: z.array(CandidateStorySegmentSchema).default([]),
});
export type CandidateStoryBoundary = z.infer<typeof CandidateStoryBoundarySchema>;

export const StoryBoundaryExtractionResponseSchema = z.object({
  has_candidates: z.boolean(),
  candidates: z.array(CandidateStoryBoundarySchema),
});
export type StoryBoundaryExtractionResponse = z.infer<typeof StoryBoundaryExtractionResponseSchema>;

export const StoryBoundaryCandidateInDBSchema = z.object({
  id: z.string().uuid(),
  document_id: z.string().uuid(),
  story_id: z.string().uuid(),
  chunk_id: z.string().uuid().nullable().optional(),
  tentative_title: z.string(),
  first_sentence: z.string(),
  last_sentence: z.string(),
  evidence_quote: z.string(),
  approx_char_start: z.number().int().nonnegative(),
  approx_char_end: z.number().int().positive(),
  document_char_start: z.number().int().nonnegative(),
  document_char_end: z.number().int().positive(),
  created_at: z.string().datetime(),
});
export type StoryBoundaryCandidateInDB = z.infer<typeof StoryBoundaryCandidateInDBSchema>;

export const StoryEvaluationResponseSchema = z.object({
  title: z.string(),
  is_autobiographical: z.boolean(),
  narrator_gender: NarratorGenderEnum,
  overall_classification: FourPlusClassificationEnum,
  overall_confidence: z.number().min(0).max(1),
  criteria_breakdown: CriteriaBreakdownSchema,
  assigned_variants: z.array(StoryVariantAssignmentSchema),
  emotions: z.array(StoryEmotionSchema),
  step_analysis: StepAnalysisSchema,
  suggested_curated_telling: z.string().nullable().optional(),
  reasoning_summary: z.string(),
});
export type StoryEvaluationResponse = z.infer<typeof StoryEvaluationResponseSchema>;

/**
 * Search Schemas
 */
export const HybridSearchRequestSchema = z.object({
  query: z.string().trim().min(1),
  filter_variant: StoryVariantEnum.optional(),
  filter_emotion: EmotionTypeEnum.optional(),
  limit: z.number().int().min(1).max(50).default(20),
  offset: z.number().int().min(0).default(0),
});
export type HybridSearchRequest = z.infer<typeof HybridSearchRequestSchema>;

export const HybridSearchResultItemSchema = z.object({
  story_id: z.string().uuid(),
  title: z.string(),
  original_text_preview: z.string(),
  original_word_count: z.number().int().nonnegative(),
  estimated_spoken_duration_seconds: z.number().int().nonnegative(),
  length_advisory_exceeds_800_words: z.boolean(),
  rrf_score: z.number(),
});
export type HybridSearchResultItem = z.infer<typeof HybridSearchResultItemSchema>;

export const HybridSearchResponseSchema = z.object({
  query: z.string(),
  total_matched: z.number().int().nonnegative(),
  results: z.array(HybridSearchResultItemSchema),
});
export type HybridSearchResponse = z.infer<typeof HybridSearchResponseSchema>;

/**
 * Review Queue & Action Schemas
 */
export const ReviewQueueItemSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  document_title: z.string(),
  original_word_count: z.number().int().nonnegative(),
  estimated_spoken_duration_seconds: z.number().int().nonnegative(),
  length_advisory_exceeds_800_words: z.boolean(),
  is_autobiographical: z.boolean().nullable().optional(),
  narrator_gender: NarratorGenderEnum.default("unknown"),
  overall_classification: FourPlusClassificationEnum,
  overall_confidence: z.number().min(0).max(1),
  assigned_variants: z.array(StoryVariantEnum),
  created_at: z.string().datetime(),
});
export type ReviewQueueItem = z.infer<typeof ReviewQueueItemSchema>;

export const ReviewQueueResponseSchema = z.object({
  total: z.number().int().nonnegative(),
  items: z.array(ReviewQueueItemSchema),
});
export type ReviewQueueResponse = z.infer<typeof ReviewQueueResponseSchema>;

export const ReviewActionRequestSchema = z.object({
  action: z.enum(["approve", "reject", "request_revision", "edit_and_approve"]),
  visibility: StoryVisibilityEnum.default("public"),
  notes: z.string().optional(),
  editorial_overrides: z
    .object({
      title: z.string().optional(),
      primary_emotion: z.string().optional(),
    })
    .optional(),
});
export type ReviewActionRequest = z.infer<typeof ReviewActionRequestSchema>;

export const ReviewActionResponseSchema = z.object({
  story_id: z.string().uuid(),
  status: StoryStatusEnum,
  visibility: StoryVisibilityEnum,
  approved_at: z.string().datetime().nullable(),
  approved_by_user_id: z.string().uuid().nullable(),
});
export type ReviewActionResponse = z.infer<typeof ReviewActionResponseSchema>;

/**
 * AI Evaluation Entity
 */
export const StoryAIEvaluationSchema = z.object({
  id: z.string().uuid(),
  story_id: z.string().uuid(),
  model_name: z.string(),
  model_version: z.string(),
  prompt_version: z.string(),
  overall_classification: FourPlusClassificationEnum,
  overall_confidence: z.number().min(0).max(1),
  criteria_evaluations: CriteriaBreakdownSchema,
  reasoning_summary: z.string(),
  token_usage: z.record(z.unknown()).default({}),
  created_at: z.string().datetime(),
});
export type StoryAIEvaluation = z.infer<typeof StoryAIEvaluationSchema>;

/**
 * Human Review Audit Log Entity
 */
export const StoryHumanReviewSchema = z.object({
  id: z.string().uuid(),
  story_id: z.string().uuid(),
  reviewer_user_id: z.string().uuid(),
  action: z.string(),
  diff: z.record(z.unknown()).nullable().optional(),
  previous_state: z.record(z.unknown()),
  new_state: z.record(z.unknown()),
  reviewer_notes: z.string().nullable().optional(),
  created_at: z.string().datetime(),
});
export type StoryHumanReview = z.infer<typeof StoryHumanReviewSchema>;

/**
 * User Profile Entity
 */
export const UserProfileSchema = z.object({
  id: z.string().uuid(),
  role: UserRoleEnum,
  display_name: z.string().nullable().optional(),
  email: z.string().email(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type UserProfile = z.infer<typeof UserProfileSchema>;
