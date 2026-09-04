# AI Medical Transcription Mobile Client

This directory contains the Expo React Native client targeting both Android and iOS.

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

## Local development

- Install dependencies:
  - `npm install`
- Run the Expo dev server:
  - `npm run start`

Set `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY` before starting Expo. By default, the
app uses `EXPO_PUBLIC_API_BASE_URL` if provided; otherwise it falls back to
`http://localhost:8000` for the backend API.
