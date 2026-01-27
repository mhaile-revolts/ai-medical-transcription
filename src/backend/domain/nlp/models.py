from __future__ import annotations

from typing import List, Optional
from enum import Enum

from pydantic import BaseModel


class ClinicalEntity(BaseModel):
    """Simplified representation of a clinical entity extracted from text.

    As the pipeline matures, this model can carry richer semantics such as
    coded terminology, confidence scores, and basic measurement attributes.
    All additional fields are optional so early demo backends remain valid.
    """

    label: str
    text: str
    code: Optional[str] = None  # e.g., ICD-10 / SNOMED / RxNorm code
    code_system: Optional[str] = None  # e.g., "ICD10", "SNOMED", "RxNorm"
    code_display: Optional[str] = None  # human-readable concept name
    confidence: Optional[float] = None  # model confidence for this span/entity
    negated: Optional[bool] = None  # True if explicitly negated ("no history of...")
    value: Optional[str] = None  # e.g., numeric value for vitals/labs
    unit: Optional[str] = None  # unit for value, e.g. "mmHg", "mg/dL"


class ClinicalEntities(BaseModel):
    """Collection of entities grouped by coarse type."""

    diagnoses: List[ClinicalEntity] = []
    medications: List[ClinicalEntity] = []
    symptoms: List[ClinicalEntity] = []
    vitals: List[ClinicalEntity] = []


class SOAPSection(BaseModel):
    text: str


class SOAPNote(BaseModel):
    """Very lightweight SOAP structure for demo purposes."""

    subjective: SOAPSection
    objective: SOAPSection
    assessment: SOAPSection
    plan: SOAPSection


class RelevanceLabel(str, Enum):
    """Coarse relevance classification for transcript segments."""

    CLINICAL_CORE = "CLINICAL_CORE"
    CLINICAL_CONTEXT = "CLINICAL_CONTEXT"
    BACKGROUND = "BACKGROUND"
    SMALL_TALK = "SMALL_TALK"
    OTHER = "OTHER"


class SpeakerRole(str, Enum):
    """High-level speaker role labels for diarized segments."""

    CLINICIAN = "CLINICIAN"
    PATIENT = "PATIENT"
    OTHER = "OTHER"


class EmotionLabel(str, Enum):
    """Coarse emotional tone label for a segment."""

    NEUTRAL = "NEUTRAL"
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    DISTRESSED = "DISTRESSED"


class TranscriptSegment(BaseModel):
    """Represents a portion of the transcript with a relevance label.

    Timestamps are optional and are left undefined in the current demo
    implementation.
    """

    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    relevance: RelevanceLabel
    speaker: Optional[SpeakerRole] = None
    emotion: Optional[EmotionLabel] = None
    confidence: Optional[float] = None
