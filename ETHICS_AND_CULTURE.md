# Ethics, Culture, and Indigenous Governance

This document summarizes the ethical principles, cultural safety goals, and
Indigenous governance patterns that inform this medical transcription and
clinical intelligence platform. It focuses on how the existing backend is
structured to support these goals in a concrete, inspectable way.

This is not legal or policy advice; it is a technical companion to your
organization's own ethics, compliance, and community agreements.

## 1. Core principles

The system is designed around the following principles:

- **Patient and community data sovereignty**
  - Patients and communities (especially Indigenous nations) must retain control
    over how their data is used, including secondary uses such as model
    training.
- **Self-identification only**
  - Race, ethnicity, and Indigenous affiliation must never be inferred from
    names, speech, or behavior. They are modeled as *self-reported* metadata
    supplied by the clinic/EHR layer where appropriate.
- **Cultural safety and non-harm**
  - AI outputs must avoid pathologizing spiritual or cultural language by
    default, and should provide clinicians with context rather than
    hard-coded stereotypes.
- **Local control and on-prem options**
  - Indigenous and rural deployments should be able to run entirely on-prem or
    in a tightly controlled environment, with clear switches to disable cloud
    dependencies.
- **Transparency and auditability**
  - Critical decisions (e.g., CDS suggestions) must be explainable and
    auditable, with minimal PHI exposure in logs.

## 2. Data sovereignty and consent hooks

### 2.1 Governance service

- `src/backend/services/governance/indigenous_data_sovereignty_guard.py` defines:
  - `CulturalConsentContext` – per-request view of consent for:
    - `cultural_ai_allowed` – whether cultural/Indigenous-aware features are
      permitted.
    - `training_allowed` – whether data from this request may be used for
      model-training or similar secondary uses.
  - `evaluate_cultural_ai_consent(tenant_id, patient_metadata)` – helper that
    derives a `CulturalConsentContext` from the current tenant and any
    patient-level flags such as `consent_cultural_ai` and
    `consent_data_training`.

### 2.2 How consent affects NLP/ML components

- `PipelineNLPService` in `services/nlp/service.py`:
  - Accepts optional `patient_metadata` and uses
    `evaluate_cultural_ai_consent(...)` to decide whether to apply cultural
    phrase normalizers.
  - When cultural AI features are explicitly disabled for a patient, the
    transcript is passed through without cultural/Indigenous normalization.

In later phases, the same consent context can be used to:

- Disable cultural risk engines and CDS variants for specific tenants.
- Block export of transcripts into training pipelines when
  `training_allowed=False`.

## 3. Cultural phrase normalization

### 3.1 Goals

Patients and clinicians may use culturally specific phrases to describe
symptoms (e.g., "my blood is hot"). If these phrases are fed directly into
ASR/NLP models trained on Western clinical text, they can be misinterpreted or
ignored.

The platform aims to:

- Preserve the **original language** for clinicians.
- Provide a **parallel clinical phrasing** for downstream machine reasoning.

### 3.2 Current implementation

- `services/nlp/cultural_phrase_normalizer.py`
- `services/nlp/indigenous_phrase_normalizer.py`

These modules:

- Take raw transcript text and a `CulturalConsentContext`.
- Apply a **small, conservative rule set** that maps known idioms to more
  explicit clinical descriptions (e.g., fever, fatigue), while leaving the rest
  of the text unchanged.
- Are **disabled** when `cultural_ai_allowed` is `False` in the consent
  context.

In future deployments, these rules should be **tenant- and community-driven**
(e.g., loaded from configuration curated by local cultural experts).

## 4. Culture-aware and Indigenous-aware risk engines

### 4.1 Design constraints

The cultural and Indigenous risk engines are designed to:

- Trigger **only** when explicit metadata is present (e.g., region flags,
  documented Indigenous affiliation, documented trauma history).
- Avoid using race/ethnicity as a proxy for biology.
- Provide **advisory** hints rather than hard-coded diagnoses.

### 4.2 Modules

- `services/nlp/cultural_risk_engine.py`
- `services/nlp/indigenous_risk_engine.py`

They are wired into `DecisionSupportService.suggest(...)` and may add
suggestions such as:

- Heat-related illness considerations for outdoor/pastoralist environments.
- Context for trauma-informed care when both Indigenous affiliation and
  historical trauma are explicitly documented.

If no relevant metadata is present, these engines return **no suggestions**, so
existing behavior is preserved.

## 5. Bias auditing and cultural safety guardrails

### 5.1 Bias auditor

- `services/nlp/bias_auditor.py` provides a `BiasAuditor` with:
  - `audit_suggestions(suggestions)` – logs aggregate counts of suggestion
    severities via `audit_service`, tagged under the
    `decision_support_suggestions` resource type.

This is intentionally **observability-only**: it does not change CDS output,
only provides a dataset for later bias and fairness analysis across tenants and
populations.

### 5.2 Cultural safety guard

- `services/nlp/cultural_safety_guard.py` provides a `CulturalSafetyGuard` that:
  - Examines CDS suggestions plus SOAP text.
  - In specific edge cases (e.g., spiritual/ancestral language combined with
    high-severity alerts), **adds** a low-severity advisory suggestion urging
    clinicians to interpret alerts in cultural and spiritual context.

It **never removes** or downgrades existing suggestions.

## 6. Accent-aware ASR

### 6.1 Rationale

Many ASR models underperform on non-Western and Indigenous speech patterns.
Rather than assume a single "neutral" English, the system surfaces accent
information so that future deployments can route to accent-appropriate models
or tuning profiles.

### 6.2 Components

- `core/accent_classifier.py`:
  - Defines `AccentLabel` (e.g., `EAST_AFRICAN_ENGLISH`, `WEST_AFRICAN_ENGLISH`,
    `AFRICAN_AMERICAN_ENGLISH`, `CARIBBEAN_ENGLISH`, `INDIGENOUS_LANGUAGE`,
    etc.).
  - Provides a heuristic `AccentClassifier` that maps language codes and simple
    region hints into `AccentLabel`.
- `core/multi_accent_asr_backend.py`:
  - `MultiAccentASRBackend` wraps any ASR backend implementing
    `transcribe(audio_url, language_code)`,
  - Classifies an accent label before delegating to the wrapped backend,
  - Stores the last detected accent for logging/diagnostics.

In current deployments, accent labels are primarily for **observability and
future tuning**, not for hard routing decisions. This avoids untested
behavioural changes while still exposing useful signals.

## 7. On-prem and cloud control flags

### 7.1 Settings

`src/backend/config.py` exposes two environment-driven controls:

- `REQUIRE_ON_PREM_ONLY`
  - Boolean flag (`"true"` / `"false"`) indicating that deployments should
    avoid external SaaS/cloud dependencies.
  - Enforcement is implemented in individual backends (e.g., LLM translation)
    and must be combined with infrastructure policies (network, hosting).
- `ALLOW_CLOUD_LLM`
  - Boolean flag that gates `LLMTranslationBackend`:
    - When `false`, any attempt to use LLM-based translation raises a
      `RuntimeError` even if `OPENAI_API_KEY` is configured.

### 7.2 LLM translation backend

- `services/transcription/backends.py` defines `LLMTranslationBackend`.
- Its `translate(...)` method now enforces:
  - `ALLOW_CLOUD_LLM` must be `true`.
  - `OPENAI_API_KEY` must be set.

This makes it possible to **hard-disable cloud LLM usage** for clinics and
Indigenous deployments that require strictly on-prem inference.

## 8. Community feedback and continuous improvement

A future module (planned under `services/nlp/culture_feedback_service.py` and
`api/v1/routes_culture.py`) is intended to:

- Expose `/api/v1/culture/feedback` for clinicians and community partners to:
  - Flag offensive language or unsafe interpretations.
  - Suggest corrections to cultural phrase mappings.
  - Provide additional context for local risk patterns.
- Store feedback in a tenant-scoped store for periodic review with:
  - Clinical safety leads,
  - Cultural/Indigenous representatives.

This feedback loop is central to keeping the system aligned with local norms
and preventing drift toward harmful generalizations.

## 9. How to run in a conservative, Indigenous-friendly mode

For deployments on tribal lands or in Indigenous-run clinics, consider the
following baseline configuration:

- **Backend configuration**
  - Set `REQUIRE_ON_PREM_ONLY="true"`.
  - Set `ALLOW_CLOUD_LLM="false"`.
  - Prefer on-prem or self-hosted ASR backends (e.g., `ASR_BACKEND="llama"` or
    other local models) instead of cloud ASR.
- **Data sovereignty**
  - Ensure patient-level fields such as `consent_cultural_ai` and
    `consent_data_training` are surfaced from your EHR and passed into the
    backend as `patient_metadata` where applicable.
  - Default `consent_data_training` to `false` unless explicitly granted.
- **Governance**
  - Treat `indigenous_data_sovereignty_guard` as the enforcement point for
    community agreements about data reuse and model training.
  - Integrate its decisions into any offline export or training pipelines.

## 10. Future work

The current implementation provides **hooks and defaults**, not a complete
ethics program. Important next steps include:

- Extending domain models to carry explicit, self-reported cultural/Indigenous
  identity fields.
- Moving idiom dictionaries and cultural risk rules into community-owned
  configuration with clear versioning.
- Adding formal bias and safety evaluations across tenants and communities,
  using the data produced by `bias_auditor`.
- Co-designing UI and messaging with Indigenous and minoritized communities so
  that the system's behaviour is understandable and correctable.

This document should evolve alongside those efforts. Changes to production
behaviour that affect cultural or Indigenous groups should be reflected here
with both their **technical mechanisms** and their **community review process**.
