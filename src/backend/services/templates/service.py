from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID, uuid4

from src.backend.domain.models.note_template import NoteTemplate, NoteTemplateSection
from src.backend.tenancy import get_current_tenant


class InMemoryTemplateService:
    """Simple in-memory store for note templates, scoped by tenant.

    This is primarily intended for early pilots and UI prototyping.
    """

    def __init__(self) -> None:
        self._templates: Dict[UUID, NoteTemplate] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        tenant = "default"
        # Cardiology example
        self._add_seed_template(
            tenant_id=tenant,
            name="Cardiology outpatient follow-up",
            specialty="cardiology",
            visit_type="follow_up",
            sections=[
                ("subjective", "History of Present Illness", None),
                ("objective", "Cardiovascular Exam", None),
                ("assessment", "Cardiac Assessment", None),
                ("plan", "Management Plan", None),
            ],
        )
        # Pediatrics example
        self._add_seed_template(
            tenant_id=tenant,
            name="Pediatrics well-child visit",
            specialty="pediatrics",
            visit_type="well_child",
            sections=[
                ("subjective", "Parental Concerns", None),
                ("objective", "Growth and Development", None),
                ("assessment", "Pediatric Assessment", "Key problems and differentials"),
                ("plan", "Immunizations and Follow-up", "Vaccines, anticipatory guidance, follow-up"),
            ],
        )
        # OB-GYN example
        self._add_seed_template(
            tenant_id=tenant,
            name="OB-GYN prenatal visit",
            specialty="obgyn",
            visit_type="prenatal",
            sections=[
                ("subjective", "Pregnancy History", "LMP, parity, current complaints"),
                ("objective", "Maternal & Fetal Status", "Vitals, fundal height, fetal heart tones"),
                ("assessment", "Pregnancy Assessment", "Gestational age and complications"),
                ("plan", "Plan", "Labs, imaging, follow-up, counseling"),
            ],
        )
        # Behavioral health example
        self._add_seed_template(
            tenant_id=tenant,
            name="Behavioral health follow-up",
            specialty="behavioral_health",
            visit_type="follow_up",
            sections=[
                ("subjective", "Current Concerns", "Mood, sleep, anxiety, safety"),
                ("objective", "Mental Status Exam", None),
                ("assessment", "Assessment", "Diagnosis and risk assessment"),
                ("plan", "Plan", "Therapy, meds, safety plan, follow-up"),
            ],
        )

    def _add_seed_template(
        self,
        *,
        tenant_id: str,
        name: str,
        specialty: str,
        visit_type: Optional[str],
        sections: list[tuple[str, str, Optional[str]]],
    ) -> None:
        template_id = uuid4()
        tmpl = NoteTemplate(
            id=template_id,
            tenant_id=tenant_id,
            name=name,
            specialty=specialty,
            visit_type=visit_type,
            sections=[
                NoteTemplateSection(id=s_id, title=title, hint=hint)
                for s_id, title, hint in sections
            ],
            is_default=True,
        )
        self._templates[template_id] = tmpl

    def list_templates(
        self,
        *,
        specialty: Optional[str] = None,
        visit_type: Optional[str] = None,
    ) -> List[NoteTemplate]:
        tenant = get_current_tenant()
        results: List[NoteTemplate] = []
        for tmpl in self._templates.values():
            if tmpl.tenant_id != tenant:
                continue
            if specialty and tmpl.specialty != specialty:
                continue
            if visit_type and tmpl.visit_type != visit_type:
                continue
            results.append(tmpl)
        return results

    def create_template(
        self,
        *,
        name: str,
        specialty: str,
        visit_type: Optional[str],
        sections: List[NoteTemplateSection],
    ) -> NoteTemplate:
        tenant = get_current_tenant()
        template_id = uuid4()
        tmpl = NoteTemplate(
            id=template_id,
            tenant_id=tenant,
            name=name,
            specialty=specialty,
            visit_type=visit_type,
            sections=sections,
            is_default=False,
        )
        self._templates[template_id] = tmpl
        return tmpl

    def get_default_for(self, *, specialty: str, visit_type: Optional[str] = None) -> Optional[NoteTemplate]:
        tenant = get_current_tenant()
        for tmpl in self._templates.values():
            if tmpl.tenant_id != tenant:
                continue
            if tmpl.specialty != specialty:
                continue
            if visit_type is not None and tmpl.visit_type != visit_type:
                continue
            if tmpl.is_default:
                return tmpl
        return None


template_service = InMemoryTemplateService()
