# AI_PROMPT_DESIGN.md: AI Prompt Engineering & Structured Output Schemas

## 1. Prompt Engineering Principles

1. **Boundary Extraction Over Text Reproduction**: The AI must **never** output the full verbatim text of a story in a `verbatim_text` field. Instead, it identifies exact source boundaries (`first_sentence`, `last_sentence`, approximate chunk-relative offsets) and quotes. For interrupted narratives, it can identify ordered additional segments to exclude unrelated sidebars. The backend verifies all anchors and extracts the true verbatim text from `document_pages`.
2. **Deterministic Structured JSON**: All AI endpoints enforce strict Pydantic v2 JSON Schema models.
3. **Structured 5-State Criteria Rubric**: Replaces simple booleans with `met`, `partially_met`, `not_met`, `uncertain`, `not_applicable`.
4. **Independent Variant Assignment**: Supports zero, one, or multiple variants from the authoritative list:
   - `return_to_joy`
   - `acting_like_myself`
   - `godsight_immanuel`
   - `appreciation_joy_spreading`
5. **Big 6 Emotion & Somatic Rigor**: Detects high-energy (Fear, Anger) and low-energy (Sadness, Shame, Disgust, Hopeless Despair) emotions plus connective emotions, identifying somatic physical markers. Missing sensations must be explicitly marked as missing (`sensations_missing: true`).
6. **Restored STEP Structure**: Enforces Setting, Trigger, Emotion & Body Sensations, Point.
7. **Evidence-Based Narrator Gender**: Classifies the autobiographical narrator as `male`, `female`, or `unknown`. Use explicit pronouns, self-identification, or clear contextual evidence. First-person pronouns such as “I” and “me” are not gender evidence by themselves. Names may support a classification only when corroborated by context; do not rely on stereotypes or author metadata unless the source establishes that the author is the narrator. Use `unknown` when evidence is absent or ambiguous.

---

## 2. Pydantic v2 Schema Definitions (`apps/api/app/schemas/ai.py`)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# Criterion Result Evaluation
CriterionResult = Literal["met", "partially_met", "not_met", "uncertain", "not_applicable"]

class CriterionEvaluationDetail(BaseModel):
    result: CriterionResult = Field(description="Evaluation outcome for this criterion")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    evidence_quote: str = Field(description="Direct verbatim quote from text demonstrating criterion, or empty string")
    reasoning: str = Field(description="Explicit explanation of why this criterion received this outcome")

class EmotionalIntensityDetail(CriterionEvaluationDetail):
    intensity_level: Literal["flat_detached", "appropriate_moderate", "overwhelming_flooding"]

class ExplicitEmotionSensationDetail(CriterionEvaluationDetail):
    emotions_identified: List[str]
    sensations_identified: List[str]
    sensations_missing: bool = Field(description="True if no physical sensations are present in source text")

class CoRegulationDetail(CriterionEvaluationDetail):
    coregulator_type: Literal["divine_god_jesus_spirit", "human_other", "both", "none"]

class CriteriaBreakdown(BaseModel):
    autobiographical_involvement: CriterionEvaluationDetail
    appropriate_emotional_intensity: EmotionalIntensityDetail
    explicit_emotion_and_body_sensations: ExplicitEmotionSensationDetail
    relational_co_regulation: CoRegulationDetail
    redemptive_outcome: CriterionEvaluationDetail

# Variant Assignment
StoryVariantType = Literal[
    "return_to_joy",
    "acting_like_myself",
    "godsight_immanuel",
    "appreciation_joy_spreading"
]

class VariantAssignmentItem(BaseModel):
    variant: StoryVariantType
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str
    reasoning: str

# Structured Emotion & Somatics
EmotionType = Literal[
    "fear", "anger", "sadness", "shame", "disgust", "hopeless_despair",
    "joy", "gratitude", "peace", "other"
]
EmotionEnergyLevel = Literal["high_energy", "low_energy", "positive_connective"]
ProgressionStage = Literal["initial", "escalation", "peak", "shift", "resolving"]

class StoryEmotionItem(BaseModel):
    emotion: EmotionType
    energy_level: EmotionEnergyLevel
    progression_stage: ProgressionStage
    evidence_quote: str
    sensations_identified: List[str] = Field(default_factory=list)
    sensations_missing: bool = Field(description="True if no physical sensations are linked to this emotion in text")

# Restored STEP Framework
class StepAnalysisOutput(BaseModel):
    setting: str = Field(description="S — Setting: Time, place, context, people present, relational atmosphere")
    trigger: str = Field(description="T — Trigger: Specific incident, word, event, or stimulus that sparked the reaction")
    emotion_and_body_sensations: str = Field(description="E — Emotion & Body Sensations: Explicit feelings AND physical body sensations")
    point: str = Field(description="P — Point: The core relational, spiritual, or life lesson/takeaway")
    internal_thoughts: Optional[str] = Field(None, description="Supplementary: Automatic cognitions, assumptions, or beliefs")
    relational_presence: Optional[str] = Field(None, description="Supplementary: Relational presence, attunement, or comfort")

# Stage 1 Candidate Boundary Detection Payload
class CandidateStorySegment(BaseModel):
    first_sentence: str
    last_sentence: str
    approx_char_start: int
    approx_char_end: int

class CandidateStoryBoundary(BaseModel):
    tentative_title: str
    first_sentence: str
    last_sentence: str
    approx_char_start: int
    approx_char_end: int
    evidence_quote: str
    source_segments: List[CandidateStorySegment] = Field(
        default_factory=list,
        description="All ordered story segments, including the first and final, when unrelated text interrupts the narrative"
    )

class StoryBoundaryExtractionResponse(BaseModel):
    has_candidates: bool
    candidates: List[CandidateStoryBoundary]

# Stage 2 Comprehensive Evaluation Payload (NO verbatim_text field)
class StoryEvaluationResponse(BaseModel):
    title: str
    is_autobiographical: bool
    narrator_gender: Literal["male", "female", "unknown"]
    overall_classification: Literal["confirmed_4_plus", "not_4_plus", "uncertain_needs_review"]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    criteria_breakdown: CriteriaBreakdown
    assigned_variants: List[VariantAssignmentItem] = Field(default_factory=list)
    emotions: List[StoryEmotionItem] = Field(default_factory=list)
    step_analysis: StepAnalysisOutput
    suggested_curated_telling: Optional[str] = Field(None, description="Optional suggested concise oral version (<300 words)")
    reasoning_summary: str
```

---

## 3. Production System Prompts

### 3.1. Stage 1: Story Candidate Boundary Detection
```text
SYSTEM PROMPT:
You are an expert narrative analyst. Scan the provided document chunk to detect boundaries of complete, self-contained personal autobiographical stories.

CRITICAL INSTRUCTIONS:
1. Do NOT output the entire verbatim story.
2. Identify the exact FIRST SENTENCE and LAST SENTENCE marking the narrative boundary.
3. Provide approximate character offsets and a brief supporting quote.
4. When a story resumes after unrelated sidebar or intervening material, return exact first/last sentence markers for every ordered source segment, including the first and final. Keep the top-level first/last markers equal to the outer story boundaries, and omit unrelated material.
5. Only identify genuine personal autobiographical stories (first-person lived experience). Omit generic sermon illustrations, lectures, and abstract theological discussions.

Return valid JSON adhering to StoryBoundaryExtractionResponse schema.
```

### 3.2. Stage 2: Multidimensional Evaluation & STEP Extraction
```text
SYSTEM PROMPT:
You are the Senior Relational Neuroscience & 4+ Story Evaluator for the Four Plus Story Library.

Your mission is to evaluate a candidate narrative against independent analytical dimensions:
1. Narrator gender: classify as `male`, `female`, or `unknown` using explicit pronouns referring to the autobiographical narrator, self-identification, or clear contextual evidence. First-person pronouns (“I”, “me”) alone do not indicate gender. A name can support a classification only when corroborated by context. Do not rely on stereotypes or author metadata unless the text establishes that the author is the narrator. Use `unknown` if the evidence is absent or ambiguous.
2. Five 4+ Criteria (autobiographical involvement, appropriate emotional intensity, explicit emotion and body sensations, relational co-regulation, redemptive outcome). Use 5-way results: met, partially_met, not_met, uncertain, not_applicable.
3. Story Variants: Assign zero, one, or multiple variants from the authoritative list:
   - return_to_joy (Level 3)
   - acting_like_myself (Level 4)
   - godsight_immanuel
   - appreciation_joy_spreading
4. Big 6 Emotions: Fear, Anger, Sadness, Shame, Disgust, Hopeless Despair, plus Joy, Gratitude, Peace. Track progression stage and somatic body sensations.
5. STEP Analysis: Extract Setting, Trigger, Emotion & Body Sensations, Point. Missing elements must be noted as missing. Never invent sensations or facts.

ANTI-HALLUCINATION RULES:
- Never infer physical sensations not explicitly stated in the source text. If missing, mark sensations_missing: true.
- Map fear/anger to high_energy; sadness/shame/disgust/hopeless_despair to low_energy; joy/gratitude/peace to positive_connective.
- Use only exact source text for criteria, emotion, and variant evidence quotes. Do not invent facts to fill STEP fields; state when evidence is missing.
- Do NOT output full verbatim text.
- Base every judgment strictly on verbatim quotes.

Return valid JSON adhering to StoryEvaluationResponse schema.
```

---

## 4. Benchmark Few-Shot Examples

### Example 1: Confirmed 4+ Story (Return to Joy + Godsight)
**Input Excerpt**:
> "As I stood outside the hospital room, a sickening wave of nausea hit me. My hands were shaking so hard I dropped my keys on the linoleum floor. The doctor had just given us the diagnosis, and my mind was screaming, 'Your life is over.' I slid down the wall and wept. That’s when Pastor Mark sat down beside me on the cold floor. He didn't offer clichés. He put a firm hand on my trembling shoulder and said quietly, 'I'm right here with you, Stanley.' In that moment, I sensed God's gentle whisper reminding me that I was not abandoned. Slowly, my breathing evened out and the knot in my stomach softened into deep peace."

**AI Evaluation Output**:
```json
{
  "title": "Held on the Hospital Floor",
  "is_autobiographical": true,
  "overall_classification": "confirmed_4_plus",
  "overall_confidence": 0.98,
  "criteria_breakdown": {
    "autobiographical_involvement": {
      "result": "met",
      "confidence": 1.0,
      "evidence_quote": "As I stood outside the hospital room, a sickening wave of nausea hit me.",
      "reasoning": "First-person autobiographical lived experience."
    },
    "appropriate_emotional_intensity": {
      "result": "met",
      "intensity_level": "appropriate_moderate",
      "confidence": 0.95,
      "evidence_quote": "The doctor had just given us the diagnosis... wept.",
      "reasoning": "Genuine distress that is emotionally manageable and resolves into peace."
    },
    "explicit_emotion_and_body_sensations": {
      "result": "met",
      "emotions_identified": ["nausea", "deep peace"],
      "sensations_identified": ["sickening wave of nausea", "hands shaking", "breathing evened out", "knot in my stomach softened"],
      "sensations_missing": false,
      "confidence": 1.0,
      "evidence_quote": "sickening wave of nausea hit me. My hands were shaking... knot in my stomach softened",
      "reasoning": "Explicit somatic sensations clearly documented in the source."
    },
    "relational_co_regulation": {
      "result": "met",
      "coregulator_type": "both",
      "confidence": 0.98,
      "evidence_quote": "Pastor Mark sat down beside me... firm hand on my trembling shoulder... sensed God's gentle whisper",
      "reasoning": "Attuned human presence combined with felt divine presence."
    },
    "redemptive_outcome": {
      "result": "met",
      "confidence": 0.96,
      "evidence_quote": "softened into deep peace",
      "reasoning": "Clear restoration to peace and relational calm."
    }
  },
  "assigned_variants": [
    {
      "variant": "return_to_joy",
      "confidence": 0.95,
      "evidence_quote": "knot in my stomach softened into deep peace",
      "reasoning": "Moves from acute fear/despair back to settled peace and joy through relational attunement."
    },
    {
      "variant": "godsight_immanuel",
      "confidence": 0.90,
      "evidence_quote": "sensed God's gentle whisper reminding me that I was not abandoned",
      "reasoning": "Experiential perception of God's presence directly providing comfort."
    }
  ],
  "emotions": [
    {
      "emotion": "fear",
      "energy_level": "high_energy",
      "progression_stage": "initial",
      "evidence_quote": "sickening wave of nausea hit me. My hands were shaking",
      "sensations_identified": ["nausea", "hands shaking"],
      "sensations_missing": false
    },
    {
      "emotion": "peace",
      "energy_level": "positive_connective",
      "progression_stage": "resolving",
      "evidence_quote": "knot in my stomach softened into deep peace",
      "sensations_identified": ["breathing evened out", "knot softened"],
      "sensations_missing": false
    }
  ],
  "step_analysis": {
    "setting": "Hospital corridor outside a patient room immediately after receiving a medical diagnosis.",
    "trigger": "The doctor delivering a severe diagnosis and keys dropping on the floor.",
    "emotion_and_body_sensations": "Terror and grief; nausea, trembling hands, weeping; shifting to settled peace, even breathing, softened stomach knot.",
    "point": "In sudden crisis, attuned physical presence and God's whisper bring our nervous system back into peace.",
    "internal_thoughts": "'Your life is over.'",
    "relational_presence": "Pastor Mark sitting on the floor with hand on shoulder."
  },
  "suggested_curated_telling": "Standing outside the hospital room, a sickening wave of nausea hit me. The doctor had just given us the diagnosis, and my hands shook so hard I dropped my keys. I sank down and wept. Then Pastor Mark sat beside me on the cold floor, placing his firm hand on my shoulder: 'I'm right here with you, Stanley.' In that shared quiet, God's peace broke in. My breathing slowed, the knot in my gut softened, and I knew we were held.",
  "reasoning_summary": "Exemplary 4+ story meeting all criteria, exhibiting Return to Joy and Godsight variants, with explicit somatic sensations."
}
```

### Example 2: Non-4+ Story with Missing Sensations (Honest Missing Detection)
**Input Excerpt**:
> "During my second year of seminary, I became very anxious about paying tuition. I thought I might have to drop out. I worried for two weeks until a check arrived in the mail from an anonymous donor."

**Evaluation Outcome**:
- `is_autobiographical`: `true`
- `overall_classification`: `not_4_plus`
- `explicit_emotion_and_body_sensations`: `result: "not_met"`, `sensations_missing: true`, `sensations_identified: []` ("Author mentions being anxious and worried, but provides zero somatic or physiological bodily sensations. In accordance with anti-hallucination rules, no sensations were invented.")
- `relational_co_regulation`: `result: "not_met"` ("Circumstantial rescue via check; no relational co-regulation with another person or experiential encounter.")
- `step_analysis`:
  - `setting`: "Seminary campus during second year."
  - `trigger`: "Tuition bill arrival."
  - `emotion_and_body_sensations`: "Anxious and worried; physical sensations missing/unrecorded."
  - `point`: "God provides financial resources for school."
