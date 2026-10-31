---
name: Mobile EAS build isolation
description: Why EAS preview builds must currently use a mobile-only archive and how to validate it.
---

Build the Expo mobile app from an isolated mobile-only archive until the
repository root is explicitly configured as an npm workspace.

**Why:** Running EAS from the nested mobile directory still selected the Git
repository root, uploaded unrelated project files, and installed the root npm
package. Replit-generated lockfiles also reference an internal registry that EAS
cloud cannot reach.

**How to apply:** Export only the mobile package, generate its lockfile against
the public npm registry, exclude `node_modules`, and use `eas build:inspect` to
verify the archive before starting a cloud build. Initialize the isolated copy
as a Git repository and install its dependencies before EAS resolves Expo
plugins. `build:inspect` does not accept `--non-interactive`. Do not treat a
cloud build as device acceptance; physical iPhone and Android clinician sign-off
is still required.