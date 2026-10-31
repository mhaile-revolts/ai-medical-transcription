# Mobile clinician validation

Use only sandbox/test patients and encounters. Do not enter patient names, medical record numbers, dates of birth, or other protected health information in this document.

Complete this sheet once on a current physical iPhone and once on a current physical Android phone using the internal preview builds.

## Current preview build status

Status recorded on 2026-10-30 UTC:

| Platform | EAS build ID | Status |
| --- | --- | --- |
| Android | `ef60a082-90c0-4d8a-acc7-af6ff9e004b1` | `FINISHED`; clinician reports full checklist passed on Pixel 9a / Android 15 |
| iPhone | `37cd8dfe-ea42-4558-af96-5368bbe96cee` | `DEFERRED` at user request; stored Apple distribution certificate is invalid/revoked; no replacement build or clinician test |

Both Android previews (`3a6af3fe-875f-4b44-9cf3-3a52d541444e` and
`e326b0a1-8a42-4e07-9128-2ee61d83f09e`) were reported to close immediately after
launch on a Pixel 9a running Android 15. The crash log identified an
`UnsatisfiedLinkError` in `libexpo-av.so` for an unavailable React Native JSI
symbol. The legacy native module has been replaced with SDK-matched
`expo-audio`. Build `8897c117-cc06-4123-996e-74ac4955cb68` completed with that
native-module change but was not device-tested. Build
`32c03c35-90c9-486b-aade-612acea5d060` opened on the Pixel 9a, but only launch
was tested. Build `ef60a082-90c0-4d8a-acc7-af6ff9e004b1` adds Clerk Device
Trust email/SMS code verification. On 2026-10-30, the user reported that a
clinician completed the full checklist on this build on Android. Per-scenario
notes, clinician initials, and sandbox encounter reference were not supplied.

The user requested that iOS packaging and testing be held for now; iOS is not
clinically validated. When resuming, the Apple account holder must run
`npx eas-cli credentials --platform ios` from `src/frontend/mobile`, sign in
through the EAS prompt, replace the invalid distribution certificate and
provisioning profile, and confirm that the test iPhone is included in the
profile. A refresh attempt from this session stopped at the required interactive
Apple sign-in; no certificate was changed. Do not enter Apple credentials in
this document or in chat.

The preview builds currently use the supervised Replit development backend. Keep
the `Start application` workflow running throughout testing. Demo-mode
idempotency claims are process-local, so preview testing can check network retry
while the server stays running but does not establish restart durability.
Rebuild against the published backend before production use.

## Test record

| Field | iPhone | Android |
| --- | --- | --- |
| Clinician initials |  |  |
| Device model |  | Pixel 9a |
| OS version |  | Android 15 |
| App build ID/version |  | `ef60a082-90c0-4d8a-acc7-af6ff9e004b1` (`0.1.0`, build `3`); clinician reports full checklist passed |
| Test date (UTC) |  | 2026-10-30 |
| Sandbox encounter reference |  |  |

The latest tested Android build page is
https://expo.dev/accounts/mhaile12865/projects/ai-medical-transcription-mobile/builds/ef60a082-90c0-4d8a-acc7-af6ff9e004b1.
The earlier build `2` page (launch test only) is
https://expo.dev/accounts/mhaile12865/projects/ai-medical-transcription-mobile/builds/32c03c35-90c9-486b-aade-612acea5d060.
The earlier, untested `expo-audio` build page is
https://expo.dev/accounts/mhaile12865/projects/ai-medical-transcription-mobile/builds/8897c117-cc06-4123-996e-74ac4955cb68.
The current Android preview APK (build 3) is
https://expo.dev/artifacts/eas/oZpbKHWdIg4F7J-xI59PO_9V3mznWEXLI7UwOUq3ey8.apk.
Its build page is
https://expo.dev/accounts/mhaile12865/projects/ai-medical-transcription-mobile/builds/ef60a082-90c0-4d8a-acc7-af6ff9e004b1.
Install this build on the Pixel 9a and complete the Android checklist before
recording results. Do not use the older failing APKs for additional tests.
Record a replacement successful iOS build ID above before beginning the iPhone
test.

## Pass/fail matrix

Record `PASS`, `FAIL`, or `BLOCKED`, plus a short note for any result other than `PASS`.

| Scenario | iPhone result/notes | Android result/notes |
| --- | --- | --- |
| Install and launch the preview build |  | `PASS`: clinician reports build `3` installed and launched |
| Clerk sign-in succeeds |  | `PASS`: clinician reports full checklist passed |
| Clerk MFA challenge and completion succeed |  | `PASS`: clinician reports full checklist passed |
| Clerk Device Trust new-device challenge sends and accepts an email or SMS code |  | `PASS`: clinician reports full checklist passed |
| OCHIN SMART authorization returns through `aimedicaltranscription://smart-complete` |  | `PASS`: clinician reports full checklist passed |
| Patient and active encounter can be selected and confirmed |  | `PASS`: clinician reports full checklist passed |
| Recording remains locked until consent is checked and the encounter is confirmed |  | `PASS`: clinician reports full checklist passed |
| Recording consent displays the configured transcription provider and external-processing disclosure |  | `PASS`: clinician reports full checklist passed |
| ElevenLabs is not selected for clinical use unless the BAA and Zero Retention Mode are confirmed |  | `PASS`: clinician reports full checklist passed |
| Deny microphone permission; app explains how to retry |  | `PASS`: clinician reports full checklist passed |
| Permanently deny permission; app opens system Settings |  | `PASS`: clinician reports full checklist passed |
| Approve permission in Settings; recording can start afterward |  | `PASS`: clinician reports full checklist passed |
| Start/stop/upload a normal recording |  | `PASS`: clinician reports full checklist passed |
| Leave source language on auto-detect and transcribe a supported non-English sandbox recording |  | `PASS`: clinician reports full checklist passed |
| Record a sandbox conversation that switches between supported languages; confirm transcription detects it after upload |  | `PASS`: clinician reports full checklist passed |
| Confirm detected language and confidence are visible after transcription completes |  | `PASS`: clinician reports full checklist passed |
| Begin recording, receive a call or audio interruption, then return |  | `PASS`: clinician reports full checklist passed |
| Begin recording, lock/unlock the screen, then return |  | `PASS`: clinician reports full checklist passed |
| Begin recording, background/foreground the app, then return |  | `PASS`: clinician reports full checklist passed |
| Lose network during upload; retry uploads exactly once to the original encounter |  | `PASS`: clinician reports full checklist passed |
| Discard a retained interrupted recording; it is not uploaded |  | `PASS`: clinician reports full checklist passed |
| Start live transcription, interrupt it, then retry the retained audio |  | `PASS`: clinician reports full checklist passed |
| Lose network during live transcription; recovery is clear and remains encounter-bound |  | `PASS`: clinician reports full checklist passed |
| Patient, encounter, and consent controls stay locked during capture/upload |  | `PASS`: clinician reports full checklist passed |
| Sign-out does not leave a recording or upload running |  | `PASS`: clinician reports full checklist passed |
| Final transcript/job is attached only to the originally confirmed encounter |  | `PASS`: clinician reports full checklist passed |

The mobile custom sign-in supports Device Trust email-code and SMS-code
challenges. If an account is configured for email-link-only Device Trust, record
that scenario as `BLOCKED`; this build does not complete email-link challenges.
Android outcomes above are reported by the user as a full checklist pass; no
per-scenario notes were provided.

## Required evidence

- Record the EAS build IDs above.
- For each non-pass result, record exact reproduction steps and the visible error message.
- Confirm in the sandbox that each successful upload created one job on the originally confirmed encounter.
- Verify that retrying after an unknown upload outcome does not create a second job.
- Do not attach screenshots containing protected health information.

## Sign-off

| Platform | Clinician initials | Result | Date (UTC) |
| --- | --- | --- | --- |
| iPhone |  |  |  |
| Android |  |  |  |