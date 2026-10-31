import React, { useEffect, useRef, useState } from 'react';
import {
  AppState,
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
  AppStateStatus,
  Linking,
} from 'react-native';
import axios from 'axios';
import { StatusBar } from 'expo-status-bar';
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import * as FileSystem from 'expo-file-system/legacy';
import * as WebBrowser from 'expo-web-browser';
import {
  ClerkProvider,
  useAuth,
  useClerk,
} from '@clerk/expo';
import { useSignIn } from '@clerk/expo/legacy';
import { tokenCache } from './tokenCache';
import { BrandMark } from './components';

// Base URL for the backend API. Can be overridden via EXPO_PUBLIC_API_BASE_URL at build time.
const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

const configuredClerkPublishableKey = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY;

if (!configuredClerkPublishableKey) {
  throw new Error('Missing EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY');
}
const CLERK_PUBLISHABLE_KEY: string = configuredClerkPublishableKey;

async function discardUnsubmittedRecording(recording: MobileAudioRecorder | null) {
  if (!recording) return;
  try {
    await recording.stop();
  } catch {
    // The native recorder may already have stopped after an OS interruption.
  }
  const uri = recording.uri;
  if (uri) {
    try {
      await FileSystem.deleteAsync(uri, { idempotent: true });
    } catch {
      // Keep interruption handling reliable even if temporary-file cleanup fails.
    }
  }
}

interface HealthResponse {
  status?: string;
  detail?: string;
  [key: string]: unknown;
}

interface TranscriptJob {
  id: string;
  status: string;
  audio_url: string;
  language_code?: string | null;
  language_probability?: number | null;
  target_language?: string | null;
  result_text?: string | null;
  translated_text?: string | null;
  [key: string]: unknown;
}

interface AudioCapabilities {
  provider: string;
  provider_label: string;
  external_processing: boolean;
  automatic_language_detection: boolean;
  consent_version: string;
  consent_disclosure: string;
}

interface AnalyzeResponse {
  entities: unknown;
  soap_note: unknown;
}

interface IngestAudioResponse {
  job: TranscriptJob;
  encounter_id?: string | null;
}

interface SmartPatient {
  id: string;
  display_name: string;
  birth_date?: string | null;
  sex?: string | null;
  source: string;
}

interface SmartEncounter {
  id: string;
  status: string;
  type?: string | null;
  period_start?: string | null;
}

interface ConfirmedEncounter {
  id: string;
}

interface EHRExportStatus {
  id: string;
  status: 'pending' | 'processing' | 'delivered' | 'failed' | 'terminal';
  retry_count: number;
  last_error?: string | null;
}

interface SmartAuthorizationStatus {
  authorized: boolean;
  practitioner_id?: string | null;
}

interface CaptureContext {
  captureId: string;
  patientId: string;
  externalEncounterId: string;
  localEncounterId: string;
  consentVersion: string;
}

interface PendingRecording {
  uri: string;
  context: CaptureContext;
}

const CONSENT_VERSION = 'mobile-recording-consent-v1';
const RECORDING_OPTIONS = RecordingPresets.HIGH_QUALITY;
type MobileAudioRecorder = ReturnType<typeof useAudioRecorder>;
type RecordingPermissionResponse = Awaited<
  ReturnType<typeof AudioModule.requestRecordingPermissionsAsync>
>;

const makeCaptureContext = (
  patient: SmartPatient | null,
  externalEncounterId: string | null,
  localEncounterId: string | null,
): CaptureContext | null => {
  if (!patient || !externalEncounterId || !localEncounterId) return null;
  return {
    captureId: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    patientId: patient.id,
    externalEncounterId,
    localEncounterId,
    consentVersion: CONSENT_VERSION,
  };
};

function MobileSignIn() {
  const { signIn, setActive, isLoaded } = useSignIn();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [secondFactorStrategy, setSecondFactorStrategy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!isLoaded) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await signIn.create({ identifier: email, password });
      if (
        result.status === 'needs_second_factor' ||
        result.status === 'needs_client_trust'
      ) {
        const factors = result.supportedSecondFactors ?? [];
        const preferredStrategies =
          result.status === 'needs_client_trust'
            ? ['email_code', 'phone_code']
            : ['totp', 'phone_code', 'backup_code', 'email_code'];
        const factor = preferredStrategies
          .map((strategy) => factors.find((item) => item.strategy === strategy))
          .find((item) => item !== undefined);
        if (!factor) {
          if (factors.some((item) => item.strategy === 'email_link')) {
            throw new Error(
              'This account requires email-link verification for this device. This mobile sign-in supports email and SMS codes; use web sign-in or ask your administrator to enable a code-based method.',
            );
          }
          throw new Error(
            result.status === 'needs_client_trust'
              ? 'This device needs verification, but no supported email or SMS code method is configured for this account. Contact your administrator.'
              : 'No supported second-factor method is available for this account.',
          );
        }

        if (factor.strategy === 'phone_code') {
          await result.prepareSecondFactor({
            strategy: 'phone_code',
            phoneNumberId: factor.phoneNumberId,
          });
        } else if (factor.strategy === 'email_code') {
          await result.prepareSecondFactor({
            strategy: 'email_code',
            emailAddressId: factor.emailAddressId,
          });
        }

        setSecondFactorStrategy(factor.strategy);
        return;
      }
      if (result.status !== 'complete') {
        throw new Error(`Unable to complete sign-in (${result.status}).`);
      }
      await setActive({ session: result.createdSessionId });
    } catch (err: any) {
      setError(err?.errors?.[0]?.longMessage ?? err?.message ?? 'Unable to sign in');
    } finally {
      setSubmitting(false);
    }
  };

  const verifySecondFactor = async () => {
    if (!isLoaded || !secondFactorStrategy) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await signIn.attemptSecondFactor({
        strategy: secondFactorStrategy,
        code: verificationCode,
      } as any);
      if (result.status !== 'complete') {
        throw new Error('The verification challenge is not complete.');
      }
      await setActive({ session: result.createdSessionId });
    } catch (err: any) {
      setError(err?.errors?.[0]?.longMessage ?? err?.message ?? 'Unable to verify code');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="auto" />
      <View style={styles.signInContainer}>
        <BrandMark />
        <Text style={styles.eyebrow}>OCHIN · CLINICAL DOCUMENTATION</Text>
        <Text style={styles.title}>A quieter way to document care.</Text>
        <Text style={styles.subtitle}>Sign in to Clinic Scribe with your individual clinician account. Patient recording stays locked until every safety check is complete.</Text>
        {secondFactorStrategy ? (
          <>
            <Text style={styles.label}>Verification code</Text>
            <Text style={styles.hint}>
              {secondFactorStrategy === 'email_code'
                ? 'Check your registered email for a verification code.'
                : secondFactorStrategy === 'phone_code'
                  ? 'Check your registered phone for a text verification code.'
                  : secondFactorStrategy === 'totp'
                    ? 'Enter the code from your authenticator app.'
                    : 'Enter one of your backup codes.'}
            </Text>
            <TextInput
              accessibilityLabel="Verification code"
              style={styles.input}
              value={verificationCode}
              onChangeText={setVerificationCode}
              autoCapitalize="none"
              autoComplete="one-time-code"
              keyboardType={secondFactorStrategy === 'backup_code' ? 'default' : 'number-pad'}
            />
            <TouchableOpacity
              style={styles.button}
              onPress={verifySecondFactor}
              disabled={submitting || !isLoaded}
            >
              {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Verify</Text>}
            </TouchableOpacity>
          </>
        ) : (
          <>
            <Text style={styles.label}>Email</Text>
            <TextInput
              accessibilityLabel="Email address"
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
            />
            <Text style={styles.label}>Password</Text>
            <TextInput
              accessibilityLabel="Password"
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="current-password"
            />
            <TouchableOpacity style={styles.button} onPress={submit} disabled={submitting || !isLoaded}>
              {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Sign in</Text>}
            </TouchableOpacity>
          </>
        )}
        {error && <Text style={styles.errorText}>{error}</Text>}
      </View>
    </SafeAreaView>
  );
}

function AuthenticatedApp() {
  const { getToken } = useAuth();
  const { signOut } = useClerk();
  const audioRecorder = useAudioRecorder(RECORDING_OPTIONS);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);
  const [audioCapabilities, setAudioCapabilities] = useState<AudioCapabilities | null>(null);
  const [audioCapabilitiesError, setAudioCapabilitiesError] = useState<string | null>(null);

  const [audioUrl, setAudioUrl] = useState('s3://bucket/demo.wav');
  const [languageCode, setLanguageCode] = useState('');
  const [targetLanguage, setTargetLanguage] = useState('es-ES');

  const [job, setJob] = useState<TranscriptJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [jobLoading, setJobLoading] = useState<boolean>(false);

  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState<boolean>(false);

  // HTTP upload recording state
  const [recording, setRecording] = useState<MobileAudioRecorder | null>(null);
  const recordingRef = useRef<MobileAudioRecorder | null>(null);
  const [recordingStatus, setRecordingStatus] = useState<'idle' | 'starting' | 'recording' | 'uploading'>('idle');
  const [uploadResult, setUploadResult] = useState<IngestAudioResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [pendingRecording, setPendingRecording] = useState<PendingRecording | null>(null);
  const [retryingUpload, setRetryingUpload] = useState(false);

  // Patient and encounter confirmation must complete before audio capture.
  const [patientId, setPatientId] = useState('');
  const [patient, setPatient] = useState<SmartPatient | null>(null);
  const [encounters, setEncounters] = useState<SmartEncounter[]>([]);
  const [patientConfirmed, setPatientConfirmed] = useState(false);
  const [selectedExternalEncounterId, setSelectedExternalEncounterId] = useState<string | null>(null);
  const [recordingConsent, setRecordingConsent] = useState(false);
  const [localEncounterId, setLocalEncounterId] = useState<string | null>(null);
  const [patientLoading, setPatientLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [patientError, setPatientError] = useState<string | null>(null);
  const [smartStatus, setSmartStatus] = useState<SmartAuthorizationStatus>({ authorized: false });
  const [smartAuthorizing, setSmartAuthorizing] = useState(false);
  const [doctorApproval, setDoctorApproval] = useState(false);
  const [exportStatus, setExportStatus] = useState<EHRExportStatus | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const patientLookupRequest = useRef(0);
  const encounterConfirmRequest = useRef(0);

  // WebSocket live transcription state
  const [liveWs, setLiveWs] = useState<any | null>(null);
  const [liveRecording, setLiveRecording] = useState<MobileAudioRecorder | null>(null);
  const [liveStatus, setLiveStatus] = useState<'idle' | 'connecting' | 'recording' | 'sending'>('idle');
  const [livePartialText, setLivePartialText] = useState<string | null>(null);
  const [liveTotalBytes, setLiveTotalBytes] = useState<number>(0);
  const [liveError, setLiveError] = useState<string | null>(null);
  const liveRecordingRef = useRef<MobileAudioRecorder | null>(null);
  const liveStopInProgressRef = useRef(false);
  const recorderOwnerRef = useRef<'upload' | 'live' | null>(null);
  const liveWsRef = useRef<any | null>(null);
  const captureContextRef = useRef<CaptureContext | null>(null);
  const liveCaptureContextRef = useRef<CaptureContext | null>(null);
  const liveRunRef = useRef(0);
  const captureRunRef = useRef(0);
  const recordingOwnerRunRef = useRef(0);
  const liveOwnerRunRef = useRef(0);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const uploadPromiseRef = useRef<Promise<boolean> | null>(null);
  const pendingRecordingRef = useRef<PendingRecording | null>(null);
  const captureActive = recordingStatus !== 'idle' || liveStatus !== 'idle' || retryingUpload;
  const workflowLocked = captureActive || pendingRecording !== null || pendingRecordingRef.current !== null;

  const authorizationHeaders = async () => {
    const token = await getToken({ skipCache: true });
    if (!token) throw new Error('Your session has expired. Please sign in again.');
    return { Authorization: `Bearer ${token}` };
  };

  const refreshSmartStatus = async () => {
    const response = await axios.get<SmartAuthorizationStatus>(
      `${API_BASE_URL}/api/v1/ehr/smart/status`, { headers: await authorizationHeaders() },
    );
    setSmartStatus(response.data);
  };

  const authorizeOchin = async () => {
    setSmartAuthorizing(true);
    setPatientError(null);
    try {
      const response = await axios.post<{ authorization_url: string }>(
        `${API_BASE_URL}/api/v1/ehr/smart/authorize`, {}, { headers: await authorizationHeaders() },
      );
      const result = await WebBrowser.openAuthSessionAsync(
        response.data.authorization_url,
        'aimedicaltranscription://smart-complete',
      );
      const returnedUrl = result.type === 'success' ? result.url : null;
      if (!returnedUrl) {
        throw new Error(result.type === 'cancel' ? 'OCHIN authorization was cancelled.' : 'OCHIN authorization did not return to Clinic Scribe.');
      }
      const parsed = new URL(returnedUrl);
      if (parsed.protocol !== 'aimedicaltranscription:' || parsed.hostname !== 'smart-complete') {
        throw new Error('Rejected an unexpected OCHIN authorization return URL.');
      }
      if (parsed.searchParams.get('status') !== 'authorized') {
        throw new Error('OCHIN authorization was not completed. Please try again.');
      }
      await refreshSmartStatus();
    } catch (err: any) {
      setPatientError(String(err?.response?.data?.detail || err?.message || 'Unable to authorize OCHIN.'));
    } finally {
      setSmartAuthorizing(false);
    }
  };

  const resetPatientWorkflow = () => {
    if (workflowLocked) {
      setPatientError('Finish or discard the stopped recording before changing the patient or encounter.');
      return;
    }
    patientLookupRequest.current += 1;
    encounterConfirmRequest.current += 1;
    setPatient(null);
    setEncounters([]);
    setPatientConfirmed(false);
    setSelectedExternalEncounterId(null);
    setRecordingConsent(false);
    setLocalEncounterId(null);
    setPatientError(null);
    setPatientLoading(false);
    setConfirmLoading(false);
    setUploadError(null);
    setDoctorApproval(false);
    setExportStatus(null);
    setExportError(null);
  };

  const handlePatientIdChange = (value: string) => {
    if (workflowLocked) {
      setPatientError('Patient details are locked while a recording, upload, or retained recording is active.');
      return;
    }
    setPatientId(value);
    resetPatientWorkflow();
  };

  const lookupPatient = async () => {
    if (workflowLocked) {
      setPatientError('Patient lookup is locked while a recording, upload, or retained recording is active.');
      return;
    }
    const normalizedPatientId = patientId.trim();
    if (!normalizedPatientId) {
      setPatientError('Enter a patient ID before looking up the patient.');
      return;
    }
    resetPatientWorkflow();
    const requestId = patientLookupRequest.current;
    setPatientLoading(true);
    try {
      const headers = await authorizationHeaders();
      const patientResponse = await axios.get(
        `${API_BASE_URL}/api/v1/ehr/smart/patients/${encodeURIComponent(normalizedPatientId)}`,
        { headers },
      );
      const encounterResponse = await axios.get(
        `${API_BASE_URL}/api/v1/ehr/smart/patients/${encodeURIComponent(normalizedPatientId)}/encounters`,
        { headers: await authorizationHeaders() },
      );
      const activeEncounters = (encounterResponse.data as SmartEncounter[]).filter((encounter) =>
        ['active', 'in-progress', 'arrived', 'triaged', 'onleave'].includes(encounter.status.toLowerCase()),
      );
      if (patientLookupRequest.current !== requestId) return;
      setPatient(patientResponse.data as SmartPatient);
      setEncounters(activeEncounters);
      if (activeEncounters.length === 0) {
        setPatientError('No active encounters are available for this patient. Recording cannot begin.');
      }
    } catch (err: any) {
      if (patientLookupRequest.current !== requestId) return;
      const msg = err?.response?.data?.detail || err?.message || 'Unable to look up patient information.';
      setPatientError(String(msg));
    } finally {
      if (patientLookupRequest.current === requestId) setPatientLoading(false);
    }
  };

  const confirmEncounterForRecording = async () => {
    if (workflowLocked) {
      setPatientError('Encounter confirmation is locked while a recording, upload, or retained recording is active.');
      return;
    }
    if (!patient || !patientConfirmed || !selectedExternalEncounterId || !recordingConsent) {
      setPatientError('Confirm the patient, choose an active encounter, and document recording consent first.');
      return;
    }
    if (!audioCapabilities) {
      setPatientError('Transcription privacy details are unavailable. Recording cannot be unlocked yet.');
      return;
    }
    setPatientError(null);
    const requestId = encounterConfirmRequest.current + 1;
    encounterConfirmRequest.current = requestId;
    setConfirmLoading(true);
    try {
      const response = await axios.post<ConfirmedEncounter>(
        `${API_BASE_URL}/api/v1/ehr/smart/confirm`,
        {
          patient_id: patient.id,
          external_encounter_id: selectedExternalEncounterId,
          consent_obtained: true,
          consent_method: 'mobile_checkbox',
          consent_version: audioCapabilities.consent_version,
        },
        { headers: await authorizationHeaders() },
      );
      if (!response.data?.id) {
        throw new Error('The backend did not return a local encounter ID.');
      }
      if (encounterConfirmRequest.current !== requestId) return;
      setLocalEncounterId(response.data.id);
    } catch (err: any) {
      if (encounterConfirmRequest.current !== requestId) return;
      const msg = err?.response?.data?.detail || err?.message || 'Unable to confirm encounter for recording.';
      setPatientError(String(msg));
    } finally {
      if (encounterConfirmRequest.current === requestId) setConfirmLoading(false);
    }
  };

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const headers = await authorizationHeaders();
        const response = await axios.get(`${API_BASE_URL}/api/v1/health`, {
          headers,
        });
        setHealth(response.data);
      } catch (err: any) {
        setHealthError(err?.message ?? 'Failed to reach backend');
      } finally {
        setHealthLoading(false);
      }
      try {
        const response = await axios.get<AudioCapabilities>(
          `${API_BASE_URL}/api/v1/audio/capabilities`,
          { headers: await authorizationHeaders() },
        );
        setAudioCapabilities(response.data);
        setAudioCapabilitiesError(null);
      } catch (err: any) {
        setAudioCapabilities(null);
        setAudioCapabilitiesError(
          err?.response?.data?.detail || err?.message || 'Unable to load transcription privacy details.',
        );
      }
    };

    fetchHealth();
    refreshSmartStatus().catch(() => setSmartStatus({ authorized: false }));
  }, [getToken]);

  const uploadRecording = (pending: PendingRecording): Promise<boolean> => {
    if (uploadPromiseRef.current) {
      setUploadError('An upload is already in progress. Wait for it to finish before retrying or discarding.');
      return uploadPromiseRef.current;
    }
    const operation = (async (): Promise<boolean> => {
    setRetryingUpload(true);
    const { uri, context } = pending;
    setUploadError(null);
    setUploadResult(null);
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 60_000);
    try {
      const formData = new FormData();
      formData.append('file', {
        uri,
        name: 'recording.m4a',
        type: 'audio/m4a',
      } as any);
      // This is the backend-created encounter, never an external ID or clinician-controlled value.
      // Use only the context captured at record start. Workflow state may have
      // changed while an upload was pending, but this audio must never follow it.
      formData.append('encounter_id', context.localEncounterId);

      const queryParts: string[] = [];
      if (languageCode) {
        queryParts.push(`language_code=${encodeURIComponent(languageCode)}`);
      }
      if (targetLanguage) {
        queryParts.push(`target_language=${encodeURIComponent(targetLanguage)}`);
      }
      const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';

      const authHeaders = await authorizationHeaders();
      const res = await fetch(`${API_BASE_URL}/api/v1/audio/upload${queryString}`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Idempotency-Key': context.captureId,
          ...authHeaders,
        },
        body: formData,
        signal: controller.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Upload failed with status ${res.status}`);
      }

      const json = (await res.json()) as IngestAudioResponse;
      setUploadResult(json);
      setJob(json.job);
      setPendingRecording(null);
      pendingRecordingRef.current = null;
      await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => undefined);
      return true;
    } catch (err: any) {
      const message = err?.name === 'AbortError'
        ? 'Upload timed out after 60 seconds.'
        : (err?.message ?? 'Failed to upload recording');
      setUploadError(`${message} The stopped recording is retained for retry or discard.`);
      setPendingRecording(pending);
      pendingRecordingRef.current = pending;
      return false;
    } finally {
      clearTimeout(timeout);
      if (uploadAbortRef.current === controller) uploadAbortRef.current = null;
      setRetryingUpload(false);
    }
    })();
    uploadPromiseRef.current = operation;
    void operation.finally(() => {
      if (uploadPromiseRef.current === operation) uploadPromiseRef.current = null;
    });
    return operation;
  };

  const explainMicrophonePermission = async (permission: RecordingPermissionResponse, setError: (message: string) => void) => {
    if (permission.granted) return true;
    if (!permission.canAskAgain) {
      setError('Microphone access is disabled for Clinic Scribe. Open Settings, enable Microphone, then return to this confirmed encounter.');
      Alert.alert('Microphone access required', 'Enable Microphone for Clinic Scribe in Settings before recording.', [
        { text: 'Not now', style: 'cancel' },
        { text: 'Open Settings', onPress: () => { Linking.openSettings().catch(() => setError('Unable to open Settings. Enable Microphone for Clinic Scribe manually.')); } },
      ]);
    } else {
      setError('Microphone permission was denied. Allow Microphone access when prompted before recording.');
    }
    return false;
  };

  const startRecording = async () => {
    const run = captureRunRef.current + 1;
    captureRunRef.current = run;
    const context = makeCaptureContext(patient, selectedExternalEncounterId, localEncounterId);
    if (!context) {
      setUploadError('Recording is locked until the patient and encounter are confirmed with consent.');
      return;
    }
    if (
      captureActive ||
      pendingRecordingRef.current ||
      recorderOwnerRef.current ||
      liveRecordingRef.current ||
      liveWsRef.current
    ) {
      setUploadError('Another recording session is active or stopping. Finish it before starting a new recording.');
      return;
    }
    recorderOwnerRef.current = 'upload';
    setUploadError(null);
    setUploadResult(null);
    setRecordingStatus('starting');
    let rec: MobileAudioRecorder | null = null;
    let recordingStarted = false;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (run !== captureRunRef.current || appStateRef.current !== 'active') return;
      if (!(await explainMicrophonePermission(permission, setUploadError))) return;
      if (run !== captureRunRef.current || appStateRef.current !== 'active') return;

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });
      if (run !== captureRunRef.current || appStateRef.current !== 'active') return;

      rec = audioRecorder;
      await rec.prepareToRecordAsync();
      if (run !== captureRunRef.current || appStateRef.current !== 'active') {
        await rec.stop().catch(() => undefined);
        return;
      }
      rec.record();
      if (
        run !== captureRunRef.current ||
        appStateRef.current !== 'active' ||
        AppState.currentState !== 'active'
      ) {
        await discardUnsubmittedRecording(rec);
        if (run === captureRunRef.current) {
          setUploadError('Recording did not start because the app is not active. Return to Clinic Scribe and try again.');
        }
        return;
      }
      captureContextRef.current = context;
      recordingRef.current = rec;
      recordingOwnerRunRef.current = run;
      setRecording(rec);
      setRecordingStatus('recording');
      recordingStarted = true;
    } catch (err: any) {
      if (run !== captureRunRef.current) {
        if (rec) await rec.stop().catch(() => undefined);
        return;
      }
      if (rec && recordingRef.current !== rec) {
        await rec.stop().catch(() => undefined);
      }
      setUploadError(err?.message ?? 'Failed to start recording');
      recordingRef.current = null;
      setRecording(null);
      if (recordingOwnerRunRef.current === run) {
        recordingRef.current = null;
        captureContextRef.current = null;
      }
      setRecordingStatus('idle');
    } finally {
      if (!recordingStarted && recorderOwnerRef.current === 'upload') {
        recorderOwnerRef.current = null;
      }
      if (!recordingStarted && run === captureRunRef.current) {
        setRecordingStatus('idle');
      }
    }
  };

  const stopRecordingAndUpload = async () => {
    const activeRecording = recordingRef.current;
    const context = captureContextRef.current;
    if (!activeRecording || !context) return;
    let stoppedUri: string | null = null;
    try {
      setRecordingStatus('uploading');
      await activeRecording.stop();
      stoppedUri = activeRecording.uri;
      setRecording(null);
      recordingRef.current = null;
      captureContextRef.current = null;
      recordingOwnerRunRef.current = 0;
      if (!stoppedUri) {
        throw new Error('No recording URI available');
      }
      await uploadRecording({ uri: stoppedUri, context });
      setRecordingStatus('idle');
    } catch (err: any) {
      stoppedUri = stoppedUri || activeRecording.uri;
      if (stoppedUri) {
        const pending = { uri: stoppedUri, context };
        setPendingRecording(pending);
        pendingRecordingRef.current = pending;
      }
      setUploadError(stoppedUri
        ? `${err?.message ?? 'Failed to stop or upload recording'} The stopped recording is retained for retry or discard.`
        : `${err?.message ?? 'Failed to stop or upload recording'} No local recording file could be retained.`);
      recordingRef.current = null;
      captureContextRef.current = null;
      setRecording(null);
      setRecordingStatus('idle');
    } finally {
      recorderOwnerRef.current = null;
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
    }
  };

  const discardPendingRecording = async () => {
    if (!pendingRecording) return;
    if (uploadPromiseRef.current) {
      setUploadError('Wait for the active upload to finish before discarding this recording.');
      return;
    }
    if (liveStatus !== 'idle') {
      setUploadError('Wait for the live transcription connection to close before discarding this recording.');
      return;
    }
    try {
      await FileSystem.deleteAsync(pendingRecording.uri, { idempotent: true });
    } catch {
      // The recording might already have been removed by the OS.
    }
    setPendingRecording(null);
    pendingRecordingRef.current = null;
    setUploadError(null);
  };

  const handleToggleRecording = async () => {
    if (recording) {
      await stopRecordingAndUpload();
    } else {
      await startRecording();
    }
  };

  const handleCreateTranscription = async () => {
    setJobError(null);
    setJob(null);
    setAnalysis(null);
    setAnalysisError(null);
    setJobLoading(true);
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/v1/transcriptions/`,
        {
          audio_url: audioUrl,
          language_code: languageCode || null,
          target_language: targetLanguage || null,
        },
        {
          headers: await authorizationHeaders(),
        },
      );
      setJob(response.data as TranscriptJob);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to create transcription job';
      setJobError(String(msg));
    } finally {
      setJobLoading(false);
    }
  };

  const handleAnalyzeTranscription = async () => {
    if (!job?.id) return;
    setAnalysisError(null);
    setAnalysis(null);
    setAnalysisLoading(true);
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/v1/transcriptions/${job.id}/analyze`,
        undefined,
        {
          headers: await authorizationHeaders(),
        },
      );
      setAnalysis(response.data as AnalyzeResponse);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to analyze transcription';
      setAnalysisError(String(msg));
    } finally {
      setAnalysisLoading(false);
    }
  };

  const approveAndExportNote = async () => {
    if (!localEncounterId || !doctorApproval) return;
    setExportLoading(true);
    setExportError(null);
    try {
      await axios.post(
        `${API_BASE_URL}/api/v1/encounters/${localEncounterId}/finalize`,
        { review_comment: 'Doctor approved in mobile review workflow' },
        { headers: await authorizationHeaders() },
      );
      const response = await axios.post<EHRExportStatus>(
        `${API_BASE_URL}/api/v1/ehr/encounters/${localEncounterId}/approved-note`,
        {},
        { headers: await authorizationHeaders() },
      );
      setExportStatus(response.data);
    } catch (err: any) {
      setExportError(String(err?.response?.data?.detail || err?.message || 'Unable to export approved note.'));
    } finally {
      setExportLoading(false);
    }
  };

  const retryExport = async () => {
    if (!exportStatus?.id) return;
    setExportLoading(true);
    setExportError(null);
    try {
      const response = await axios.post<EHRExportStatus>(
        `${API_BASE_URL}/api/v1/ehr/messages/${exportStatus.id}/retry`,
        {},
        { headers: await authorizationHeaders() },
      );
      setExportStatus(response.data);
    } catch (err: any) {
      setExportError(String(err?.response?.data?.detail || err?.message || 'Unable to retry export.'));
    } finally {
      setExportLoading(false);
    }
  };

  useEffect(() => {
    if (!exportStatus?.id || exportStatus.status === 'delivered' || exportStatus.status === 'terminal') {
      return;
    }
    const timer = setInterval(async () => {
      try {
        const response = await axios.get<EHRExportStatus>(
          `${API_BASE_URL}/api/v1/ehr/messages/${exportStatus.id}`,
          { headers: await authorizationHeaders() },
        );
        setExportStatus(response.data);
      } catch {
        // Keep the last known delivery state; explicit actions still surface errors.
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [exportStatus?.id, exportStatus?.status]);

  const buildWsUrl = (context: CaptureContext) => {
    let base = API_BASE_URL;
    if (base.startsWith('https://')) {
      base = 'wss://' + base.slice('https://'.length);
    } else if (base.startsWith('http://')) {
      base = 'ws://' + base.slice('http://'.length);
    }

    const params: string[] = [];
    if (languageCode) {
      params.push(`language_code=${encodeURIComponent(languageCode)}`);
    }
    if (targetLanguage) {
      params.push(`target_language=${encodeURIComponent(targetLanguage)}`);
    }
    params.push(`encounter_id=${encodeURIComponent(context.localEncounterId)}`);
    params.push(`capture_id=${encodeURIComponent(context.captureId)}`);
    const query = params.length ? `?${params.join('&')}` : '';
    return `${base}/api/v1/audio/ws${query}`;
  };

  const startLiveTranscription = async () => {
    const run = liveRunRef.current + 1;
    liveRunRef.current = run;
    const context = makeCaptureContext(patient, selectedExternalEncounterId, localEncounterId);
    if (!context) {
      setLiveError('Recording is locked until the patient and encounter are confirmed with consent.');
      return;
    }
    if (
      captureActive ||
      pendingRecordingRef.current ||
      recorderOwnerRef.current ||
      recordingRef.current
    ) {
      setLiveError('Another recording session is active or stopping. Finish it before starting live transcription.');
      return;
    }
    recorderOwnerRef.current = 'live';
    setLiveError(null);
    setLivePartialText(null);
    setLiveTotalBytes(0);
    setLiveStatus('connecting');
    liveStopInProgressRef.current = false;

    let ws: any | null = null;
    let keepRecorderClaim = false;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (run !== liveRunRef.current || appStateRef.current !== 'active') return;
      if (!(await explainMicrophonePermission(permission, setLiveError))) return;
      if (run !== liveRunRef.current || appStateRef.current !== 'active') return;

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });
      if (run !== liveRunRef.current || appStateRef.current !== 'active') return;

      const wsUrl = buildWsUrl(context);
      const token = await getToken({ skipCache: true });
      if (run !== liveRunRef.current || appStateRef.current !== 'active') return;
      if (!token) throw new Error('Your session has expired. Please sign in again.');
      ws = new (WebSocket as any)(
        wsUrl,
        [],
        { headers: { Authorization: `Bearer ${token}` } },
      );
      liveCaptureContextRef.current = context;
      liveWsRef.current = ws;
      liveOwnerRunRef.current = run;

      setLiveStatus('connecting');

      ws.onopen = async () => {
        if (
          run !== liveRunRef.current ||
          liveWsRef.current !== ws ||
          appStateRef.current !== 'active' ||
          AppState.currentState !== 'active' ||
          ws.readyState !== WebSocket.OPEN
        ) {
          ws.close();
          return;
        }
        let rec: MobileAudioRecorder | null = null;
        try {
          rec = audioRecorder;
          await rec.prepareToRecordAsync();
          if (run !== liveRunRef.current || appStateRef.current !== 'active' || liveWsRef.current !== ws) {
            await rec.stop().catch(() => undefined);
            ws.close();
            return;
          }
          rec.record();
          if (
            run !== liveRunRef.current ||
            liveWsRef.current !== ws ||
            appStateRef.current !== 'active' ||
            AppState.currentState !== 'active' ||
            ws.readyState !== WebSocket.OPEN
          ) {
            await discardUnsubmittedRecording(rec);
            ws.close();
            return;
          }
          liveRecordingRef.current = rec;
          liveOwnerRunRef.current = run;
          setLiveRecording(rec);
          setLiveStatus('recording');
        } catch (err: any) {
          if (run !== liveRunRef.current || liveWsRef.current !== ws) {
            await discardUnsubmittedRecording(rec);
            return;
          }
          await discardUnsubmittedRecording(rec);
          setLiveError(err?.message ?? 'Failed to start live recording');
          setLiveStatus('idle');
          liveRecordingRef.current = null;
          setLiveRecording(null);
          liveCaptureContextRef.current = null;
          liveOwnerRunRef.current = 0;
          ws.close();
        }
      };

      ws.onmessage = (event: any) => {
        if (run !== liveRunRef.current || liveWsRef.current !== ws) return;
        try {
          const data = JSON.parse(event.data);
          if (typeof data.error === 'string') {
            setLiveError(`${data.error} The local recording is retained for retry or discard.`);
            try { ws.close(); } catch { /* already closed */ }
            return;
          }
          if (typeof data.partial_text === 'string') {
            setLivePartialText(data.partial_text);
          }
          if (typeof data.total_bytes === 'number') {
            setLiveTotalBytes(data.total_bytes);
          }
          if (data.type === 'final') {
            const liveContext = liveCaptureContextRef.current;
            if (
              !data.job
              || !liveContext
              || data.capture_id !== liveContext.captureId
              || data.encounter_id !== liveContext.localEncounterId
            ) {
              setLiveError('The server did not confirm this recording for its original encounter. The local audio is retained.');
              return;
            }
            setJob(data.job as TranscriptJob);
            setLiveError(null);
            const pending = pendingRecordingRef.current;
            if (pending && pending.context.captureId === data.capture_id) {
              pendingRecordingRef.current = null;
              setPendingRecording(null);
              void FileSystem.deleteAsync(pending.uri, { idempotent: true }).catch(() => undefined);
            }
          }
        } catch {
          // ignore JSON parse errors
        }
      };

      ws.onerror = () => {
        if (run !== liveRunRef.current || liveWsRef.current !== ws) return;
        setLiveError('Live transcription connection was lost. The recording is being stopped and retained for review.');
        try { ws.close(); } catch { /* already closed */ }
      };

      ws.onclose = () => {
        if (liveWsRef.current !== ws || liveOwnerRunRef.current !== run) return;
        const activeRecording = liveRecordingRef.current;
        const liveContext = liveCaptureContextRef.current;
        liveWsRef.current = null;
        liveCaptureContextRef.current = null;
        liveOwnerRunRef.current = 0;
        setLiveWs(null);

        if (activeRecording) {
          if (liveStopInProgressRef.current) return;
          setLiveStatus('sending');
          void (async () => {
            let stopFailed = false;
            try {
              await activeRecording.stop();
            } catch {
              stopFailed = true;
            }
            const uri = activeRecording.uri;
            if (uri && liveContext) {
              const pending = { uri, context: liveContext };
              setPendingRecording(pending);
              pendingRecordingRef.current = pending;
              setLiveError('Live connection was interrupted. The stopped recording is retained for explicit retry or discard.');
            } else {
              setLiveError(stopFailed
                ? 'Live connection was interrupted and no complete recording file could be retained.'
                : 'Live connection was interrupted before a complete recording file was available. Audio was not uploaded.');
            }
            if (liveRecordingRef.current === activeRecording) {
              liveRecordingRef.current = null;
              setLiveRecording(null);
              setLiveStatus('idle');
              recorderOwnerRef.current = null;
              await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
            }
          })();
        } else {
          setLiveStatus('idle');
          setLiveRecording(null);
          const pending = pendingRecordingRef.current;
          if (pending && liveContext?.captureId === pending.context.captureId) {
            setLiveError('Live connection closed before the server confirmed a result. The stopped recording is retained for retry or discard.');
          }
          recorderOwnerRef.current = null;
          void setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
        }
      };

      liveWsRef.current = ws;
      setLiveWs(ws);
      keepRecorderClaim = true;
    } catch (err: any) {
      if (run !== liveRunRef.current || (ws && liveWsRef.current !== ws)) {
        if (ws) { try { ws.close(); } catch { /* already closed */ } }
        return;
      }
      setLiveError(err?.message ?? 'Failed to start live transcription');
      setLiveStatus('idle');
      if (liveRecordingRef.current && liveOwnerRunRef.current === run) {
        await discardUnsubmittedRecording(liveRecordingRef.current);
      }
      liveRecordingRef.current = null;
      setLiveRecording(null);
      if (ws && liveWsRef.current === ws) {
        try {
          liveWsRef.current.close();
        } catch {
          // ignore
        }
      }
      setLiveWs(null);
      if (liveWsRef.current === ws) {
        liveWsRef.current = null;
        liveCaptureContextRef.current = null;
        liveOwnerRunRef.current = 0;
      }
    } finally {
      if (!keepRecorderClaim) {
        if (recorderOwnerRef.current === 'live') recorderOwnerRef.current = null;
        if (run === liveRunRef.current) setLiveStatus('idle');
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
      }
    }
  };

  const stopLiveTranscription = async () => {
    const activeRecording = liveRecordingRef.current;
    const ws = liveWsRef.current;
    if (!ws) {
      liveRunRef.current += 1;
      const context = liveCaptureContextRef.current;
      if (activeRecording) {
        try {
          await activeRecording.stop();
        } catch {
          // The recorder may already have been stopped by the OS.
        }
        const uri = activeRecording.uri;
        if (uri && context) {
          const pending = { uri, context };
          setPendingRecording(pending);
          pendingRecordingRef.current = pending;
          setLiveError('The live connection closed. The stopped recording is retained for retry or discard.');
        } else {
          setLiveError('The live connection closed and no complete recording file could be retained.');
        }
        liveRecordingRef.current = null;
        liveCaptureContextRef.current = null;
        setLiveRecording(null);
      } else {
        setLiveError('Live transcription was cancelled before the connection started.');
      }
      recorderOwnerRef.current = null;
      setLiveStatus('idle');
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
      return;
    }
    const context = liveCaptureContextRef.current;
    let stoppedUri: string | null = null;
    liveStopInProgressRef.current = true;
    try {
      setLiveStatus('sending');
      if (!activeRecording) {
        ws.close();
        return;
      }
      await activeRecording.stop();
      stoppedUri = activeRecording.uri;
      setLiveRecording(null);
      liveRecordingRef.current = null;
      if (!stoppedUri) {
        throw new Error('No recording URI available');
      }
      if (!context) {
        throw new Error('The original encounter context is unavailable. Audio was not uploaded.');
      }
      const pending = { uri: stoppedUri, context };
      setPendingRecording(pending);
      pendingRecordingRef.current = pending;
      if (ws.readyState !== 1) {
        throw new Error('Live connection closed before the recording was confirmed. The audio is retained for retry or discard.');
      }
      const base64Data = await FileSystem.readAsStringAsync(stoppedUri, {
        encoding: FileSystem.EncodingType.Base64,
      });
      if (ws.readyState !== 1) {
        throw new Error('Live connection closed before the recording was confirmed. The audio is retained for retry or discard.');
      }
      ws.send(`AUDIO_BASE64:${base64Data}`);
      ws.send('stop');
    } catch (err: any) {
      stoppedUri = stoppedUri || activeRecording?.uri || null;
      if (stoppedUri && context) {
        const pending = { uri: stoppedUri, context };
        setPendingRecording(pending);
        pendingRecordingRef.current = pending;
      }
      liveRecordingRef.current = null;
      setLiveRecording(null);
      setLiveError(err?.message ?? 'Failed to stop or send live recording');
      setLiveStatus('idle');
      try { ws.close(); } catch { /* already closed */ }
    } finally {
      liveStopInProgressRef.current = false;
      if (!liveRecordingRef.current) {
        if (ws.readyState === 3) {
          recorderOwnerRef.current = null;
          setLiveStatus('idle');
        }
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
      }
    }
  };

  const handleToggleLive = async () => {
    if (liveStatus === 'recording' || liveStatus === 'connecting') {
      await stopLiveTranscription();
    } else {
      await startLiveTranscription();
    }
  };

  const safelyAbortActiveCapture = async (reason: string) => {
    captureRunRef.current += 1;
    liveRunRef.current += 1;
    uploadAbortRef.current?.abort();
    if (uploadPromiseRef.current) await uploadPromiseRef.current.catch(() => false);
    const activeRecording = recordingRef.current ?? liveRecordingRef.current;
    const isLiveRecording = !!activeRecording && liveRecordingRef.current === activeRecording;
    const context = isLiveRecording ? liveCaptureContextRef.current : captureContextRef.current;
    if (activeRecording) {
      try {
        await activeRecording.stop();
      } catch {
        // Inspect the URI after stop as the OS may have already closed the recorder.
      }
      const uri = activeRecording.uri;
      const retained = !!uri && !!context;
      if (uri && context) {
        const pending = { uri, context };
        setPendingRecording(pending);
        pendingRecordingRef.current = pending;
      }
      if (isLiveRecording) {
        liveRecordingRef.current = null;
        liveCaptureContextRef.current = null;
        setLiveRecording(null);
        setLiveError(retained
          ? `${reason} Live recording was stopped and retained for explicit retry or discard.`
          : `${reason} Live recording stopped, but no file was available to retain.`);
      } else {
        recordingRef.current = null;
        captureContextRef.current = null;
        setRecording(null);
        setUploadError(retained
          ? `${reason} Recording was stopped and retained for explicit retry or discard; it was not attached to a new encounter.`
          : `${reason} Recording stopped, but no file was available to retain.`);
      }
      recorderOwnerRef.current = null;
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => undefined);
    }
    if (!activeRecording && liveWsRef.current) {
      setLiveError(`${reason} The live session ended before recording began. Start again when the app is active.`);
    }
    recordingRef.current = null;
    captureContextRef.current = null;
    liveRecordingRef.current = null;
    liveCaptureContextRef.current = null;
    liveOwnerRunRef.current = 0;
    setRecording(null);
    setLiveRecording(null);
    setRecordingStatus('idle');
    setLiveStatus('idle');
    const activeWs = liveWsRef.current;
    liveWsRef.current = null;
    liveOwnerRunRef.current = 0;
    setLiveWs(null);
    if (activeWs) {
      try { activeWs.close(); } catch { /* already closed */ }
      if (!activeRecording) recorderOwnerRef.current = null;
    }
  };

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      const wasActive = appStateRef.current === 'active';
      appStateRef.current = nextState;
      if (wasActive && nextState !== 'active') {
        void safelyAbortActiveCapture('App was backgrounded or interrupted.');
      }
    });
    return () => {
      subscription.remove();
      void safelyAbortActiveCapture('Capture was closed.');
    };
  }, []);

  const handleSignOut = async () => {
    if (captureActive || uploadPromiseRef.current) await safelyAbortActiveCapture('Signing out.');
    const pending = pendingRecordingRef.current;
    if (pending) {
      setUploadError('The stopped recording is retained. Retry upload or explicitly discard it before signing out.');
      return;
    }
    await signOut();
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="auto" />
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <View style={styles.topbar}>
          <View style={styles.brandLine}><BrandMark /><View><Text style={styles.brandName}>Clinic Scribe</Text><Text style={styles.brandMeta}>OCHIN Epic companion</Text></View></View>
          <TouchableOpacity accessibilityRole="button" accessibilityLabel="Sign out" style={styles.signOutCompact} onPress={handleSignOut}><Text style={styles.signOutText}>Sign out</Text></TouchableOpacity>
        </View>
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>SAFE DOCUMENTATION · {smartStatus.authorized ? 'CONNECTED' : 'ACTION NEEDED'}</Text>
          <Text style={styles.title}>Ready for the visit</Text>
          <Text style={styles.subtitle}>Each step protects patient identity and keeps recording under your control.</Text>
          <View style={styles.progress}>{[smartStatus.authorized, !!patient, !!localEncounterId, !!localEncounterId, recordingStatus === 'recording'].map((done, index) => <View key={index} style={[styles.progressBar, done && styles.progressDone]} />)}</View>
        </View>

        {/* Individual session */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Clinic account</Text>
          <Text style={styles.hint}>Requests use your short-lived Clerk session token.</Text>
          <Text style={styles.hint}>
            OCHIN SMART: {smartStatus.authorized ? `Authorized as Practitioner ${smartStatus.practitioner_id}` : 'Not authorized'}
          </Text>
          {!smartStatus.authorized && (
            <TouchableOpacity style={styles.button} onPress={authorizeOchin} disabled={smartAuthorizing}>
              {smartAuthorizing ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Authorize OCHIN Epic</Text>}
            </TouchableOpacity>
          )}
          <TouchableOpacity style={styles.buttonSecondary} onPress={handleSignOut}>
            <Text style={styles.buttonSecondaryText}>Sign out</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity accessibilityRole="button" accessibilityLabel="Toggle diagnostics" style={styles.diagnosticsToggle} onPress={() => setDiagnosticsOpen(!diagnosticsOpen)}>
          <View><Text style={styles.diagnosticsTitle}>Diagnostics & developer tools</Text><Text style={styles.hint}>Backend health, audio URL jobs, and raw payloads</Text></View>
          <Text style={styles.chevron}>{diagnosticsOpen ? '−' : '+'}</Text>
        </TouchableOpacity>
        {diagnosticsOpen && <>
        {/* Backend health */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Backend Health</Text>
          {healthLoading && <ActivityIndicator size="small" color="#176F64" />}
          {!healthLoading && healthError && <Text style={styles.errorText}>{healthError}</Text>}
          {!healthLoading && !healthError && health && (
            <View style={styles.card}>
              <Text style={styles.cardBody}>{JSON.stringify(health, null, 2)}</Text>
            </View>
          )}
        </View>

        {/* Create transcription job from audio URL */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Create Transcription Job</Text>

          <Text style={styles.label}>API Base URL</Text>
          <Text style={styles.hint}>{API_BASE_URL}</Text>

          <Text style={styles.label}>Audio URL</Text>
          <TextInput
            style={styles.input}
            value={audioUrl}
            onChangeText={setAudioUrl}
            placeholder="s3://bucket/demo.wav or file path"
          />

          <View style={styles.row}>
            <View style={styles.rowItem}>
              <Text style={styles.label}>Source language override (optional)</Text>
              <TextInput
                style={styles.input}
                value={languageCode}
                onChangeText={setLanguageCode}
                placeholder="Auto-detect multilingual"
              />
            </View>
            <View style={styles.rowItem}>
              <Text style={styles.label}>Target language</Text>
              <TextInput
                style={styles.input}
                value={targetLanguage}
                onChangeText={setTargetLanguage}
                placeholder="es-ES"
              />
            </View>
          </View>
          <Text style={styles.hint}>
            {audioCapabilities?.automatic_language_detection
              ? 'Leave the source override blank. Supported languages are detected automatically from the finished recording, including conversations that switch languages. The detected language appears after transcription completes.'
              : 'Leave the source override blank to let the configured transcription backend choose its default language.'}
          </Text>

          <TouchableOpacity style={styles.button} onPress={handleCreateTranscription} disabled={jobLoading}>
            {jobLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Create Job</Text>}
          </TouchableOpacity>

          {jobError && <Text style={styles.errorText}>{jobError}</Text>}

          {job && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Job</Text>
              <Text style={styles.label}>Status: <Text style={styles.mono}>{job.status}</Text></Text>
              <Text style={styles.label}>ID: <Text style={styles.mono}>{job.id}</Text></Text>
              {job.language_code && (
                <Text style={styles.label}>Source language: <Text style={styles.mono}>{job.language_code}</Text></Text>
              )}
              {typeof job.language_probability === 'number' && (
                <Text style={styles.hint}>Language detection confidence: {Math.round(job.language_probability * 100)}%</Text>
              )}
              {job.target_language && (
                <Text style={styles.label}>Target language: <Text style={styles.mono}>{job.target_language}</Text></Text>
              )}
              {job.result_text && (
                <View style={{ marginTop: 8 }}>
                  <Text style={styles.cardTitle}>Transcript</Text>
                  <Text style={styles.cardBody}>{job.result_text}</Text>
                </View>
              )}
              {job.translated_text && (
                <View style={{ marginTop: 8 }}>
                  <Text style={styles.cardTitle}>Translated Transcript</Text>
                  <Text style={styles.cardBody}>{job.translated_text}</Text>
                </View>
              )}
            </View>
          )}
        </View>

        </>}

        {/* Record & upload audio from device */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Patient & Recording Authorization</Text>
          <View style={styles.warningCard}>
            <Text style={styles.warningTitle}>Wrong-patient prevention</Text>
            <Text style={styles.warningText}>
              Verify the patient’s identity with the patient before continuing. Recording remains locked until
              the patient, an active encounter, and recording consent are explicitly confirmed.
            </Text>
          </View>

          {!patient ? (
            <>
              <Text style={styles.label}>Patient ID</Text>
              <TextInput
                style={styles.input}
                value={patientId}
                onChangeText={handlePatientIdChange}
                editable={!workflowLocked}
                placeholder="Enter patient ID"
                autoCapitalize="none"
              />
              <TouchableOpacity style={styles.button} onPress={lookupPatient} disabled={patientLoading || workflowLocked}>
                {patientLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Look Up Patient</Text>}
              </TouchableOpacity>
            </>
          ) : (
            <>
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Confirm this patient before recording</Text>
                <Text style={styles.cardBody}>Name: {patient.display_name}</Text>
                <Text style={styles.cardBody}>Date of birth: {patient.birth_date || 'Not available'}</Text>
                <Text style={styles.cardBody}>Sex: {patient.sex || 'Not available'}</Text>
                <Text style={styles.cardBody}>Source: {patient.source}</Text>
                <TouchableOpacity
                  style={styles.checkboxRow}
                  disabled={workflowLocked}
                  onPress={() => {
                    encounterConfirmRequest.current += 1;
                    setPatientConfirmed(!patientConfirmed);
                    setSelectedExternalEncounterId(null);
                    setRecordingConsent(false);
                    setLocalEncounterId(null);
                    setConfirmLoading(false);
                    setPatientError(null);
                  }}
                >
                  <View style={[styles.checkbox, patientConfirmed && styles.checkboxChecked]}>
                    {patientConfirmed && <Text style={styles.checkboxMark}>✓</Text>}
                  </View>
                  <Text style={styles.checkboxLabel}>I verified this is the correct patient.</Text>
                </TouchableOpacity>
              </View>
              <TouchableOpacity style={styles.buttonSecondary} onPress={resetPatientWorkflow} disabled={workflowLocked}>
                <Text style={styles.buttonSecondaryText}>Change Patient</Text>
              </TouchableOpacity>

              {patientConfirmed && (
                <>
                  <Text style={styles.label}>Choose active encounter</Text>
                  {encounters.map((encounter) => (
                    <TouchableOpacity
                      key={encounter.id}
                      style={[styles.encounterOption, selectedExternalEncounterId === encounter.id && styles.encounterOptionSelected]}
                      disabled={workflowLocked}
                      onPress={() => {
                        encounterConfirmRequest.current += 1;
                        setSelectedExternalEncounterId(encounter.id);
                        setRecordingConsent(false);
                        setLocalEncounterId(null);
                        setConfirmLoading(false);
                        setPatientError(null);
                      }}
                    >
                      <Text style={styles.cardTitle}>{encounter.type || 'Encounter'}</Text>
                      <Text style={styles.hint}>Status: {encounter.status}{encounter.period_start ? ` · ${encounter.period_start}` : ''}</Text>
                    </TouchableOpacity>
                  ))}
                  {selectedExternalEncounterId && !audioCapabilities && (
                    <Text style={audioCapabilitiesError ? styles.errorText : styles.hint}>
                      {audioCapabilitiesError || 'Loading transcription privacy details…'}
                    </Text>
                  )}
                  {selectedExternalEncounterId && audioCapabilities && (
                    <>
                      <TouchableOpacity
                        style={styles.checkboxRow}
                        disabled={workflowLocked}
                        onPress={() => {
                          encounterConfirmRequest.current += 1;
                          setRecordingConsent(!recordingConsent);
                          setLocalEncounterId(null);
                          setConfirmLoading(false);
                          setPatientError(null);
                        }}
                      >
                        <View style={[styles.checkbox, recordingConsent && styles.checkboxChecked]}>
                          {recordingConsent && <Text style={styles.checkboxMark}>✓</Text>}
                        </View>
                        <Text style={styles.checkboxLabel}>The patient consents to recording and AI transcription.</Text>
                      </TouchableOpacity>
                      <Text style={styles.hint}>
                        {audioCapabilities.provider_label}: {audioCapabilities.consent_disclosure}
                      </Text>
                    </>
                  )}
                  {recordingConsent && !localEncounterId && (
                    <TouchableOpacity style={styles.button} onPress={confirmEncounterForRecording} disabled={confirmLoading || workflowLocked}>
                      {confirmLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Confirm & Unlock Recording</Text>}
                    </TouchableOpacity>
                  )}
                  {localEncounterId && <Text style={styles.successText}>Patient, encounter, and consent confirmed. Recording is unlocked.</Text>}
                </>
              )}
            </>
          )}
          {patientError && <Text style={styles.errorText}>{patientError}</Text>}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Record & Upload Audio</Text>
          <Text style={styles.hint}>
            Uses your microphone and uploads to /api/v1/audio/upload.
          </Text>

          <TouchableOpacity
            style={styles.button}
            onPress={handleToggleRecording}
            disabled={recordingStatus === 'starting' || recordingStatus === 'uploading' || !localEncounterId || liveStatus !== 'idle' || !!pendingRecording || retryingUpload}
          >
            {recordingStatus === 'starting' ? (
              <ActivityIndicator color="#fff" />
            ) : recordingStatus === 'recording' ? (
              <Text style={styles.buttonText}>Stop & Upload</Text>
            ) : recordingStatus === 'uploading' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>{localEncounterId ? 'Start Recording' : 'Confirm patient to record'}</Text>
            )}
          </TouchableOpacity>

          {recordingStatus === 'recording' && (
            <Text style={styles.hint}>Recording… tap again to stop and upload.</Text>
          )}
          {recordingStatus === 'starting' && (
            <Text style={styles.hint}>Preparing the microphone…</Text>
          )}

          {uploadError && <Text style={styles.errorText}>{uploadError}</Text>}
          {pendingRecording && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Stopped recording awaiting your decision</Text>
              <Text style={styles.hint}>Bound to encounter {pendingRecording.context.localEncounterId}; retry will use this original encounter, not the current selection.</Text>
              <TouchableOpacity style={styles.button} disabled={retryingUpload || liveStatus !== 'idle'} onPress={() => { void uploadRecording(pendingRecording); }}>
                <Text style={styles.buttonText}>Retry Upload</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.buttonSecondary} disabled={retryingUpload || liveStatus !== 'idle'} onPress={() => { void discardPendingRecording(); }}>
                <Text style={styles.buttonSecondaryText}>Discard Recording</Text>
              </TouchableOpacity>
            </View>
          )}

          {uploadResult && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Uploaded Job</Text>
              <Text style={styles.cardBody}>{JSON.stringify(uploadResult, null, 2)}</Text>
            </View>
          )}
        </View>

        {/* Live transcription over WebSocket */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Live Transcription (WebSocket)</Text>
          <Text style={styles.hint}>
            Records audio, sends it to /api/v1/audio/ws, and shows partial transcripts.
          </Text>

          <TouchableOpacity
            style={styles.button}
            onPress={handleToggleLive}
            disabled={liveStatus === 'sending' || !localEncounterId || recordingStatus !== 'idle' || !!pendingRecording || retryingUpload}
          >
            {liveStatus === 'recording' || liveStatus === 'connecting' ? (
              <Text style={styles.buttonText}>Stop & Send</Text>
            ) : liveStatus === 'sending' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>{localEncounterId ? 'Start Live Session' : 'Confirm patient to record'}</Text>
            )}
          </TouchableOpacity>

          {livePartialText && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Partial Transcript</Text>
              <Text style={styles.cardBody}>{livePartialText}</Text>
              <Text style={styles.hint}>Total bytes: {liveTotalBytes}</Text>
            </View>
          )}

          {liveError && <Text style={styles.errorText}>{liveError}</Text>}
        </View>

        {/* Analyze transcription */}
        {job && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Analyze Transcription</Text>
            <TouchableOpacity
              style={styles.buttonSecondary}
              onPress={handleAnalyzeTranscription}
              disabled={analysisLoading}
            >
              {analysisLoading ? (
                <ActivityIndicator color="#176F64" />
              ) : (
                <Text style={styles.buttonSecondaryText}>Analyze Job</Text>
              )}
            </TouchableOpacity>

            {analysisError && <Text style={styles.errorText}>{analysisError}</Text>}

            {analysis && (
              <>
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Analysis</Text>
                {/* Try to render SOAP-style sections if present */}
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {(() => {
                  const a: any = analysis;
                  const soap = a?.soap_note || {};
                  const subj = soap?.subjective?.text ?? null;
                  const obj = soap?.objective?.text ?? null;
                  const assess = soap?.assessment?.text ?? null;
                  const plan = soap?.plan?.text ?? null;
                  return (
                    <>
                      {subj && (
                        <View style={{ marginTop: 6 }}>
                          <Text style={styles.cardTitle}>Subjective</Text>
                          <Text style={styles.cardBody}>{subj}</Text>
                        </View>
                      )}
                      {obj && (
                        <View style={{ marginTop: 6 }}>
                          <Text style={styles.cardTitle}>Objective</Text>
                          <Text style={styles.cardBody}>{obj}</Text>
                        </View>
                      )}
                      {assess && (
                        <View style={{ marginTop: 6 }}>
                          <Text style={styles.cardTitle}>Assessment</Text>
                          <Text style={styles.cardBody}>{assess}</Text>
                        </View>
                      )}
                      {plan && (
                        <View style={{ marginTop: 6 }}>
                          <Text style={styles.cardTitle}>Plan</Text>
                          <Text style={styles.cardBody}>{plan}</Text>
                        </View>
                      )}
                    </>
                  );
                })()}
              </View>
              <View style={styles.warningCard}>
                <Text style={styles.warningTitle}>Doctor review required</Text>
                <Text style={styles.warningText}>
                  Review every section above. Nothing is sent to Epic until you explicitly approve the final note.
                </Text>
                <TouchableOpacity style={styles.checkboxRow} onPress={() => setDoctorApproval(!doctorApproval)}>
                  <View style={[styles.checkbox, doctorApproval && styles.checkboxChecked]}>
                    {doctorApproval && <Text style={styles.checkboxMark}>✓</Text>}
                  </View>
                  <Text style={styles.checkboxLabel}>I am the doctor and approve this note as final.</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.button}
                  onPress={approveAndExportNote}
                  disabled={!doctorApproval || !localEncounterId || exportLoading || exportStatus?.status === 'delivered'}
                >
                  {exportLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Approve & Send to Epic</Text>}
                </TouchableOpacity>
                {exportStatus && (
                  <Text style={exportStatus.status === 'delivered' ? styles.successText : styles.hint}>
                    Epic delivery: {exportStatus.status} · attempts: {exportStatus.retry_count + 1}
                  </Text>
                )}
                {(exportStatus?.status === 'failed' || exportStatus?.status === 'terminal') && (
                  <TouchableOpacity style={styles.buttonSecondary} onPress={retryExport} disabled={exportLoading}>
                    <Text style={styles.buttonSecondaryText}>Retry safely</Text>
                  </TouchableOpacity>
                )}
                {(exportError || exportStatus?.last_error) && (
                  <Text style={styles.errorText}>{exportError || exportStatus?.last_error}</Text>
                )}
              </View>
              </>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} tokenCache={tokenCache}>
      <MobileAuthGate />
    </ClerkProvider>
  );
}

function MobileAuthGate() {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.signInContainer}>
          <ActivityIndicator size="large" color="#176F64" />
        </View>
      </SafeAreaView>
    );
  }
  return isSignedIn ? <AuthenticatedApp /> : <MobileSignIn />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F4F9F7',
  },
  scrollContent: {
    padding: 18,
    paddingBottom: 56,
    maxWidth: 760,
    alignSelf: 'center',
    width: '100%',
  },
  signInContainer: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
    maxWidth: 520,
    alignSelf: 'center',
    width: '100%',
    backgroundColor: '#F4F9F7',
  },
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 },
  brandLine: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  brandName: { color: '#173A35', fontSize: 15, fontWeight: '800' },
  brandMeta: { color: '#6C8780', fontSize: 10, marginTop: 2 },
  signOutCompact: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 8 },
  signOutText: { color: '#176F64', fontSize: 12, fontWeight: '800' },
  hero: { marginBottom: 18 },
  progress: { flexDirection: 'row', gap: 4, marginTop: 15 },
  progressBar: { height: 4, flex: 1, borderRadius: 4, backgroundColor: '#DCEAE5' },
  progressDone: { backgroundColor: '#23796D' },
  eyebrow: { color: '#6C8780', fontSize: 10, fontWeight: '800', letterSpacing: 1.1, marginTop: 17, marginBottom: 8 },
  title: {
    fontSize: 28,
    fontWeight: '700',
    marginBottom: 4,
    color: '#173A35',
  },
  subtitle: {
    fontSize: 14,
    color: '#6C8780',
    marginBottom: 16,
    lineHeight: 21,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 8,
  },
  label: {
    fontSize: 12,
    fontWeight: '500',
    marginTop: 8,
    marginBottom: 4,
  },
  hint: {
    fontSize: 12,
    color: '#666',
  },
  input: {
    borderWidth: 1,
    borderColor: '#D8E9E3',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    backgroundColor: '#fff',
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  rowItem: {
    flex: 1,
  },
  card: {
    width: '100%',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    marginTop: 8,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  cardTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  cardBody: {
    fontFamily: 'Courier',
    fontSize: 11,
  },
  warningCard: {
    backgroundColor: '#fff3cd',
    borderColor: '#d39e00',
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  warningTitle: {
    color: '#7a5600',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 4,
  },
  warningText: {
    color: '#5c4300',
    fontSize: 12,
    lineHeight: 18,
  },
  checkboxRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 12,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: '#176F64',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
  },
  checkboxChecked: {
    backgroundColor: '#176F64',
  },
  checkboxMark: {
    color: '#fff',
    fontWeight: '700',
  },
  checkboxLabel: {
    flex: 1,
    fontSize: 13,
    color: '#222',
  },
  encounterOption: {
    backgroundColor: '#fff',
    borderColor: '#D8E9E3',
    borderRadius: 8,
    borderWidth: 1,
    padding: 12,
    marginTop: 8,
  },
  encounterOptionSelected: {
    borderColor: '#176F64',
    borderWidth: 2,
  },
  successText: {
    color: '#16803c',
    fontSize: 13,
    fontWeight: '600',
    marginTop: 12,
  },
  mono: {
    fontFamily: 'Courier',
    fontSize: 11,
  },
  errorText: {
    color: '#ff3b30',
    marginTop: 8,
  },
  button: {
    marginTop: 16,
    backgroundColor: '#176F64',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontWeight: '600',
  },
  buttonSecondary: {
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#176F64',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
  },
  buttonSecondaryText: {
    color: '#176F64',
    fontWeight: '600',
  },
  lockLine: { color: '#6C8780', fontSize: 11, marginTop: 14, lineHeight: 16 },
  diagnosticsToggle: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 16, borderTopWidth: 1, borderBottomWidth: 1, borderColor: '#D8E9E3', marginBottom: 15 },
  diagnosticsTitle: { color: '#173A35', fontWeight: '800', fontSize: 13 },
  chevron: { color: '#176F64', fontSize: 24, fontWeight: '300', paddingHorizontal: 10 },
});
