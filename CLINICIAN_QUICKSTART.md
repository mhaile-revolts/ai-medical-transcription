# Clinician Quick-Start Guide

This guide describes how to use the AI medical transcription app during the clinic pilot.

Some clinics may also use human scribes or VAs behind the scenes; they see a similar view of your encounters and notes but work in a separate, access-controlled panel.

At a high level, the system can:
- Record or upload clinical audio.
- Produce draft transcripts and SOAP-style notes.
- Suggest clinical codes and highlight simple billing risk signals.
- Provide advisory decision-support hints.
- Let you review and finalize notes per encounter.
- Show timelines of a patient’s encounters and basic analytics for your clinic.

> Exact URLs and distribution details (App Store/TestFlight / Play Store / APK) will be provided by your administrator. This document focuses on *how* to use the app once you have access.

## 1. Accessing the system

You may have access to one or both of:

- **Web app** (desktop browser)
- **Mobile app** (Android and/or iOS)

Your clinic or project admin will share:

- The web or mobile app distribution link.
- An individual clinic account assigned to the correct clinic and role.

Never share your account password or approve a sign-in you did not initiate.

---

## 2. Web app (high level)

1. **Open the web URL** provided by your admin (e.g. a `https://...` link).
2. **Sign in** with your individual clinic account.
3. You can then:
   - View existing **encounters** and their notes.
   - See **transcription jobs** and their analysis.
   - Review and finalize draft notes.

(Exact web UI details depend on the current build your clinic is using.)

---

## 3. Mobile app – first-time setup

1. **Install the app**
   - Android: via Play Store or a direct APK link from your admin.
   - iOS: via TestFlight or App Store (pilot build).

2. **Open the app**
   - On first launch you will see:
     - The clinic account sign-in screen.

3. **Sign in**
   - Enter the email and password for your individual clinic account.
   - The app keeps the session in the device's secure storage and signs each
     backend request with a short-lived session token.

4. **Confirm backend is reachable**
   - Scroll to **Backend Health**.
   - If the backend is reachable and your account is authorized, you should see a small JSON block such as:
     - `{ "status": "ok", "version": "v1" }`.
   - If you see an authorization error, sign out and back in. Ask your admin to
     confirm your clinic membership and role if the problem continues.

---

## 4. Recording audio and sending for transcription (mobile)

There are two main flows:

### 4.1. Simple upload (record then upload)

1. In **Record & Upload Audio**:
   - Optionally set **Source language** (e.g. `en-US`) and **Target language** (e.g. `es-ES`).
2. Tap **Start Recording**.
   - Grant microphone permissions if prompted.
3. Speak your note or conversation into the device.
4. Tap **Stop & Upload**.
   - The app will:
     - Stop recording.
     - Upload the audio file to `/api/v1/audio/upload`.
     - Show the created **transcription job** and associated **encounter**.
5. Once uploaded, the job details appear under **Uploaded Job** and also in the **Job** card.

### 4.2. Live transcription (WebSocket)

This mode records audio and sends it to the backend in a way that allows partial transcript updates during the session.

1. In **Live Transcription (WebSocket)**:
   - Again, check **Source language** and **Target language** in the earlier section.
2. Tap **Start Live Session**.
   - The app opens a secure WebSocket to the backend and starts recording.
3. Speak normally.
   - As audio is processed, the **Partial Transcript** card will update with in-progress text.
4. When finished, tap **Stop & Send**.
   - The app sends the final audio to the backend and signals completion.
   - The backend creates a final **transcription job** linked to the session.
5. After a short delay, you should see the job appear in the **Job** card.

> Note: In early pilot builds, live partials are for clinician convenience and may not be fully accurate; always review the final text.

---

## 5. Viewing analysis, codes, and suggestions

Once a transcription job exists (from upload or live session):

1. Scroll to **Analyze Transcription**.
2. Tap **Analyze Job**.
   - The backend runs the clinical NLP pipeline on the completed transcript.
3. The **Analysis** card will display structured data such as:
   - Extracted clinical entities (problems, meds, symptoms).
   - A generated SOAP-style note.
   - Suggested clinical codes (demo ICD-10 / CPT-style) and a simple billing risk indicator.
   - A breakdown of transcript segments the system treats as clinically relevant, including a simple emotion/tone label.
4. In later iterations of the UI, this analysis will feed into a dedicated note editor where you can:
   - Review and edit the note.
   - Mark encounters as ready for review or finalized.

---

## 6. Encounter review and decision-support (web)

When using the web app, each visit is represented as an **encounter**:

- You can open an encounter to see:
  - Linked transcription jobs and their analysis.
  - The current draft or finalized note.
- Typical flow:
  1. Upload/record audio and wait for transcription.
  2. Run analysis.
  3. Edit the note as needed.
  4. Submit for review (if your clinic uses human-in-the-loop review).
  5. Finalize the encounter once you are satisfied.
- Some builds may also expose a **“decision-support”** view for an encounter that shows:
  - Non-binding suggestions (e.g., diabetes treatment reminders).
  - These are advisory only and should not replace your clinical judgment.

---

## 7. Best practices during pilot

- **Always review machine-generated content**
  - Treat transcriptions and notes as drafts.
  - Edit for accuracy and completeness before relying on them for clinical decisions.
- **Protect patient privacy**
  - Do not share screenshots or text outside authorized channels.
  - Ensure your device is locked when unattended.
- **Report issues**
  - If transcription or analysis seems incorrect, note the encounter ID and report to your pilot lead.
  - Feedback is critical for improving model performance and workflow.

---

## 8. Getting help

If you encounter login issues, errors, or unexpected behavior:

- Contact your clinic pilot lead or technical support.
- Provide:
  - Your environment (staging vs pilot).
  - Approximate time of the issue.
  - Whether it happened on web, mobile, or both.
  - The encounter or transcription job ID if available.
