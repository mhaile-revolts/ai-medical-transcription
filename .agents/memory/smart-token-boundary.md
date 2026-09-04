---
name: SMART token boundary
description: Security boundary between application identity and OCHIN SMART authorization.
---

OCHIN SMART authorization must remain a separate clinician-scoped grant from Clerk application authentication. SMART tokens must never be returned to or stored by a frontend; encrypt them server-side and bind every use to both tenant and clinician.

**Why:** Clerk proves access to this application, while OCHIN independently authorizes clinical FHIR access. Combining the credentials or accepting a SMART grant across tenants or roles would create a serious PHI access-control failure.

**How to apply:** Any future OCHIN read/write flow must require the clinician role, resolve credentials by tenant plus clinician, validate SMART issuer/audience/nonce/Practitioner identity, and keep token values out of logs and client responses.