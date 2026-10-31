# AI Medical Transcription Mobile Client

This directory contains the Expo React Native client targeting both Android and iOS.

## Recording safety model

- Audio capture is unlocked only after the clinician selects a patient, confirms an
  active encounter, and records consent.
- Every recording and live session snapshots an immutable patient, encounter,
  consent version, and capture ID. A retry always uses that original context.
- Calls, screen locks, backgrounding, and network loss stop capture and retain
  the local audio for an explicit retry or discard decision.
- Patient, encounter, consent, and sign-out actions cannot race an active capture
  or upload; a retained recording must be retried or explicitly discarded before
  changing encounters or signing out.
- Direct uploads and live WebSocket sessions share a capture idempotency key. The
  production backend durably tracks pending, complete, and failed claims so a
  network timeout or server restart cannot create a second job or attach audio
  to a different encounter. Live audio remains on-device until the server
  confirms the job and its encounter. Demo-mode claims are process-local, so
  preview testing does not establish production restart durability.
- SMART authorization accepts only a successful return to
  `aimedicaltranscription://smart-complete` followed by an authorized server
  status.

## Sign-in verification

The mobile sign-in flow supports Clerk MFA using authenticator codes, SMS codes,
email codes, and backup codes. When Clerk Device Trust requires verification on
a new device (`needs_client_trust`), the app sends a code to the clinician's
registered email or phone and activates the session only after that code is
verified. Device Trust configured for email-link-only verification is not
supported by this custom mobile flow; the app reports that limitation instead
of treating it as a successful sign-in.

## Native audio module

Audio capture uses the Expo SDK-matched `expo-audio` package. Do not restore
`expo-av`: its native library crashed during Android startup with an unresolved
React Native JSI symbol. Background recording and playback remain disabled;
the app stops capture on interruption or backgrounding.

## Multilingual transcription

The source-language override is optional. Leave it blank for automatic
language detection; Scribe v2 Medical can transcribe supported languages in a
recording without requiring the clinician to restart capture after a language
change. The detected language and confidence appear when transcription
completes. The current Expo recorder sends the finalized recording for
transcription, so the app does not update language labels continuously while
someone is speaking.

The backend uses the already-connected ElevenLabs integration when configured
with `ASR_BACKEND=elevenlabs`. It selects `scribe_v2_medical` by default and
requests Zero Retention Mode on every transcription request. Before selecting
this backend for clinical audio, the organization must verify an active
ElevenLabs Enterprise Business Associate Agreement and Zero Retention Mode.
Then configure:

- `ELEVENLABS_BAA_CONFIRMED=true`
- `ELEVENLABS_ZERO_RETENTION_ENABLED=true`
- `ASR_BACKEND=elevenlabs`
- Optionally, `ELEVENLABS_SCRIBE_MODEL=scribe_v2_medical`

If either compliance confirmation is missing, backend startup is rejected.
Provider consent details are shown before the clinician can unlock recording.
A clinician must review the transcript before clinical use. Never test with
real patient audio until the organization's compliance and privacy requirements
are confirmed.

## Build matrix

Profiles are defined in `eas.json` and map to environments and platforms as follows:

- **preview (internal / staging)**
  - Platform: **Android**
    - Artifact: **APK** (sideload / internal testing)
    - Command: `eas build --platform android --profile preview`
    - Configuration: EAS `preview` environment
  - Platform: **iOS**
    - Artifact: device build (for internal/TestFlight)
    - Command: `eas build --platform ios --profile preview`
    - Configuration: EAS `preview` environment

- **production (store / production)**
  - Platform: **Android**
    - Artifact: **AAB** (Play Store)
    - Command: `eas build --platform android --profile production`
    - Configuration: EAS `production` environment
  - Platform: **iOS**
    - Artifact: device build (App Store / TestFlight)
    - Command: `eas build --platform ios --profile production`
    - Configuration: EAS `production` environment

Configure `EXPO_PUBLIC_API_BASE_URL` and `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY`
in the named EAS environment for each profile. Do not put the Clerk secret key
in EAS public variables or the mobile bundle.

The iOS build targets iOS 17 because the current native Clerk package requires
iOS 17 or later. The internal iOS provisioning profile must include each test
device, and the stored Apple distribution certificate must be valid.

### Preview build prerequisites

1. Confirm the backend URL is reachable from the physical devices. A Replit
   development URL is acceptable only for a supervised preview test while the
   `Start application` workflow remains running; production builds must use the
   published backend URL.
2. Configure the EAS `preview` environment:
   - `EXPO_PUBLIC_API_BASE_URL`
   - `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY`
3. Verify Expo access with `npx eas-cli whoami`.
4. Verify dependencies with `npm ci`, `npx expo-doctor`, and
   `npx tsc --noEmit`.
5. If iOS reports an invalid or revoked signing certificate, run
   `npx eas-cli credentials --platform ios` as the Apple account holder and
   replace the distribution certificate and provisioning profile. Never share
   Apple credentials or an Expo token in chat.

This repository is not currently declared as an npm monorepo workspace. If EAS
archives the repository root or installs the root package instead of this mobile
package, export this directory to an isolated build directory, generate its
lockfile from the public npm registry, and run EAS there. Confirm with
`eas build:inspect` that the archive contains this package and excludes
`node_modules`.

## Physical-device acceptance

Code checks and cloud compilation do not replace device testing. Before clinical
use, a clinician must complete `docs/mobile-clinician-validation.md` on at least
one current physical iPhone and one current physical Android phone. Use only
sandbox/test encounters and do not record protected health information in the
validation document.

## Local development

- Install dependencies:
  - `npm install`
- Run the Expo dev server:
  - `npm run start`

Set `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY` before starting Expo. By default, the
app uses `EXPO_PUBLIC_API_BASE_URL` if provided; otherwise it falls back to
`http://localhost:8000` for the backend API.
