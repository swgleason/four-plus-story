"""
Authoritative Enums for Four Plus Story Library.

These enums correspond exactly to PostgreSQL custom enum types and
TypeScript Zod definitions in @four-plus/shared-types.
"""

from enum import Enum


class StoryVariant(str, Enum):
    """
    Authoritative four story variants in the Life Model framework.
    Prohibited as variants: 'distress_to_peace', 'rupture_and_repair', 'endurance_and_hope'.
    """
    RETURN_TO_JOY = "return_to_joy"
    ACTING_LIKE_MYSELF = "acting_like_myself"
    GODSIGHT_IMMANUEL = "godsight_immanuel"
    APPRECIATION_JOY_SPREADING = "appreciation_joy_spreading"


class StoryStatus(str, Enum):
    """Lifecycle review status for discovered stories."""
    DISCOVERED_PENDING_REVIEW = "discovered_pending_review"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class StoryVisibility(str, Enum):
    """Multi-tier publication visibility."""
    INTERNAL_ONLY = "internal_only"
    REGISTERED_USERS = "registered_users"
    PUBLIC = "public"


class NarratorGender(str, Enum):
    """Evidence-based narrator gender classification."""
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class FourPlusClassification(str, Enum):
    """Overall 4+ classification independent of autobiographical status or variants."""
    CONFIRMED_4_PLUS = "confirmed_4_plus"
    NOT_4_PLUS = "not_4_plus"
    UNCERTAIN_NEEDS_REVIEW = "uncertain_needs_review"


class CriterionResult(str, Enum):
    """5-way evaluation result for individual criteria."""
    MET = "met"
    PARTIALLY_MET = "partially_met"
    NOT_MET = "not_met"
    UNCERTAIN = "uncertain"
    NOT_APPLICABLE = "not_applicable"


class EmotionType(str, Enum):
    """
    Authoritative Big 6 Emotion Taxonomy + Connective / Positive States.
    High-energy: fear, anger.
    Low-energy: sadness, shame, disgust, hopeless_despair.
    Positive/connective: joy, gratitude, peace, other.
    """
    FEAR = "fear"
    ANGER = "anger"
    SADNESS = "sadness"
    SHAME = "shame"
    DISGUST = "disgust"
    HOPELESS_DESPAIR = "hopeless_despair"
    JOY = "joy"
    GRATITUDE = "gratitude"
    PEACE = "peace"
    OTHER = "other"


class EmotionEnergyLevel(str, Enum):
    """Physiological energy arousal tier for emotions."""
    HIGH_ENERGY = "high_energy"
    LOW_ENERGY = "low_energy"
    POSITIVE_CONNECTIVE = "positive_connective"


class ProgressionStage(str, Enum):
    """Progression stage of an emotion within the narrative arc."""
    INITIAL = "initial"
    ESCALATION = "escalation"
    PEAK = "peak"
    SHIFT = "shift"
    RESOLVING = "resolving"


class DocumentRightsStatus(str, Enum):
    """Legal copyright and publication rights clearance status."""
    PUBLIC_DOMAIN = "public_domain"
    LICENSED = "licensed"
    RESTRICTED_INTERNAL = "restricted_internal"
    FAIR_USE_EDUCATIONAL = "fair_use_educational"


class UserRole(str, Enum):
    """RBAC roles for platform access."""
    SUPER_ADMIN = "super_admin"
    CURATOR = "curator"
    REVIEWER = "reviewer"
    CHURCH_MEMBER = "church_member"
    PUBLIC_GUEST = "public_guest"


class DocumentType(str, Enum):
    """Source document formats."""
    PDF_BOOK = "pdf_book"
    PDF_ARTICLE = "pdf_article"
    TXT_TRANSCRIPT = "txt_transcript"
    TXT_STORY_NOTE = "txt_story_note"


class JobStatus(str, Enum):
    """Asynchronous background processing job statuses."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CoregulatorType(str, Enum):
    """Type of co-regulator identified in Criterion 4."""
    DIVINE_GOD_JESUS_SPIRIT = "divine_god_jesus_spirit"
    HUMAN_OTHER = "human_other"
    BOTH = "both"
    NONE = "none"


class EmotionalIntensityLevel(str, Enum):
    """Arousal intensity level in Criterion 2."""
    FLAT_DETACHED = "flat_detached"
    APPROPRIATE_MODERATE = "appropriate_moderate"
    OVERWHELMING_FLOODING = "overwhelming_flooding"


class JobLogLevel(str, Enum):
    """Severity level for processing job events."""
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class ReviewAction(str, Enum):
    """Action taken by a human reviewer."""
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"
    EDIT_AND_APPROVE = "edit_and_approve"
