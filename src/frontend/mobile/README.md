# AI Medical Transcription Mobile Client

This directory contains the Expo React Native client targeting both Android and iOS.

## Build matrix

Profiles are defined in `eas.json` and map to environments and platforms as follows:

- **preview (internal / staging)**
  - Platform: **Android**
    - Artifact: **APK** (sideload / internal testing)
    - Command: `eas build --platform android --profile preview`
    - API base URL: `EXPO_PUBLIC_API_BASE_URL=https://staging.your-backend.example.com`
  - Platform: **iOS**
    - Artifact: device build (for internal/TestFlight)
    - Command: `eas build --platform ios --profile preview`
    - API base URL: `EXPO_PUBLIC_API_BASE_URL=https://staging.your-backend.example.com`

- **production (store / production)**
  - Platform: **Android**
    - Artifact: **AAB** (Play Store)
    - Command: `eas build --platform android --profile production`
    - API base URL: `EXPO_PUBLIC_API_BASE_URL=https://api.your-backend.example.com`
  - Platform: **iOS**
    - Artifact: device build (App Store / TestFlight)
    - Command: `eas build --platform ios --profile production`
    - API base URL: `EXPO_PUBLIC_API_BASE_URL=https://api.your-backend.example.com`

Update the actual API base URLs in `eas.json` to match your staging and production backends.

## Local development

- Install dependencies:
  - `npm install`
- Run the Expo dev server:
  - `npm run start`

By default, the app will use `EXPO_PUBLIC_API_BASE_URL` if provided, otherwise it falls back to `http://localhost:8000` for the backend API.
