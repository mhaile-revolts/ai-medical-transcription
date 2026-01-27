from pathlib import Path

from src.backend.domain.nlp.models import ClinicalEntities, ClinicalEntity
from src.backend.services.nlp.backends import UmlsCodingBackend


def test_umls_coding_backend_assigns_codes_from_concepts_file(tmp_path):
    """Verify UmlsCodingBackend assigns codes using a small demo concepts file.

    This exercises the terminology mapping layer without requiring external
    UMLS services or large ontologies.
    """

    # Use the checked-in demo concepts file under tests/backend/data.
    concepts_path = Path("tests/backend/data/demo_umls_concepts.jsonl").resolve()
    assert concepts_path.exists(), "Demo UMLS concepts file is missing"

    backend = UmlsCodingBackend(concepts_path=concepts_path, min_similarity=0.5)

    entities = ClinicalEntities()
    entities.diagnoses.append(ClinicalEntity(label="DIAGNOSIS", text="The patient has type 2 diabetes."))
    entities.medications.append(ClinicalEntity(label="MEDICATION", text="Metformin 500 mg"))

    coded = backend.code(entities)

    # Expect diabetes to map to the E11 demo ICD-10 code and carry system/display
    diabetes = coded.diagnoses[0]
    assert diabetes.code == "E11"
    assert (diabetes.code_system or "").upper().startswith("ICD")
    assert "diabetes" in (diabetes.code_display or "").lower()

    # Expect metformin to map to the demo RxNorm-like code and carry system/display
    met = coded.medications[0]
    assert met.code == "860975"
    assert (met.code_system or "").lower() == "rxnorm"
    assert "metformin" in (met.code_display or "").lower()
