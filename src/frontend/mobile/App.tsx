import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  TextInput,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import axios from 'axios';
import { StatusBar } from 'expo-status-bar';
import { Audio } from 'expo-av';
import * as FileSystem from 'expo-file-system/legacy';
import * as WebBrowser from 'expo-web-browser';
import {
  ClerkProvider,
  useAuth,
  useClerk,
} from '@clerk/expo';
import { useSignIn } from '@clerk/expo/legacy';
import { tokenCache } from './tokenCache';

// Base URL for the backend API. Can be overridden via EXPO_PUBLIC_API_BASE_URL at build time.
const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

const configuredClerkPublishableKey = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY;

if (!configuredClerkPublishableKey) {
  throw new Error('Missing EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY');
}
const CLERK_PUBLISHABLE_KEY: string = configuredClerkPublishableKey;

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
  target_language?: string | null;
  result_text?: string | null;
  translated_text?: string | null;
  [key: string]: unknown;
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
  status: 'pending' | 'delivered' | 'failed';
  retry_count: number;
  last_error?: string | null;
}

interface SmartAuthorizationStatus {
  authorized: boolean;
  practitioner_id?: string | null;
}

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
      if (result.status === 'needs_second_factor') {
        const factors = result.supportedSecondFactors ?? [];
        const factor =
          factors.find((item: any) => item.strategy === 'totp') ??
          factors.find((item: any) => item.strategy === 'phone_code') ??
          factors.find((item: any) => item.strategy === 'backup_code');
        if (!factor) {
          throw new Error('No supported second-factor method is available for this account.');
        }
        if (factor.strategy === 'phone_code') {
          await result.prepareSecondFactor({
            strategy: 'phone_code',
            phoneNumberId: factor.phoneNumberId,
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
        <Text style={styles.title}>AI Medical Transcription</Text>
        <Text style={styles.subtitle}>Sign in with your individual clinic account</Text>
        {secondFactorStrategy ? (
          <>
            <Text style={styles.label}>Verification code</Text>
            <Text style={styles.hint}>
              Enter the code from your {secondFactorStrategy.replace('_', ' ')} method.
            </Text>
            <TextInput
              style={styles.input}
              value={verificationCode}
              onChangeText={setVerificationCode}
              autoCapitalize="none"
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
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
            />
            <Text style={styles.label}>Password</Text>
            <TextInput
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
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);

  const [audioUrl, setAudioUrl] = useState('s3://bucket/demo.wav');
  const [languageCode, setLanguageCode] = useState('en-US');
  const [targetLanguage, setTargetLanguage] = useState('es-ES');

  const [job, setJob] = useState<TranscriptJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [jobLoading, setJobLoading] = useState<boolean>(false);

  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState<boolean>(false);

  // HTTP upload recording state
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [recordingStatus, setRecordingStatus] = useState<'idle' | 'recording' | 'uploading'>('idle');
  const [uploadResult, setUploadResult] = useState<IngestAudioResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

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
  const patientLookupRequest = useRef(0);
  const encounterConfirmRequest = useRef(0);

  // WebSocket live transcription state
  const [liveWs, setLiveWs] = useState<any | null>(null);
  const [liveRecording, setLiveRecording] = useState<Audio.Recording | null>(null);
  const [liveStatus, setLiveStatus] = useState<'idle' | 'connecting' | 'recording' | 'sending'>('idle');
  const [livePartialText, setLivePartialText] = useState<string | null>(null);
  const [liveTotalBytes, setLiveTotalBytes] = useState<number>(0);
  const [liveError, setLiveError] = useState<string | null>(null);

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
      await WebBrowser.openAuthSessionAsync(response.data.authorization_url, 'aimedicaltranscription://smart-complete');
      await refreshSmartStatus();
    } catch (err: any) {
      setPatientError(String(err?.response?.data?.detail || err?.message || 'Unable to authorize OCHIN.'));
    } finally {
      setSmartAuthorizing(false);
    }
  };

  const resetPatientWorkflow = () => {
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
    setPatientId(value);
    resetPatientWorkflow();
  };

  const lookupPatient = async () => {
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
    if (!patient || !patientConfirmed || !selectedExternalEncounterId || !recordingConsent) {
      setPatientError('Confirm the patient, choose an active encounter, and document recording consent first.');
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
          consent_version: 'mobile-recording-consent-v1',
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
    };

    fetchHealth();
    refreshSmartStatus().catch(() => setSmartStatus({ authorized: false }));
  }, [getToken]);

  const uploadRecording = async (uri: string) => {
    if (!localEncounterId) {
      setUploadError('Confirm the patient, active encounter, and recording consent before uploading.');
      return;
    }
    setUploadError(null);
    setUploadResult(null);
    try {
      const formData = new FormData();
      formData.append('file', {
        uri,
        name: 'recording.m4a',
        type: 'audio/m4a',
      } as any);
      // This is the backend-created encounter, never an external ID or clinician-controlled value.
      formData.append('encounter_id', localEncounterId);

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
          ...authHeaders,
        },
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Upload failed with status ${res.status}`);
      }

      const json = (await res.json()) as IngestAudioResponse;
      setUploadResult(json);
      setJob(json.job);
    } catch (err: any) {
      setUploadError(err?.message ?? 'Failed to upload recording');
    }
  };

  const startRecording = async () => {
    if (!localEncounterId) {
      setUploadError('Recording is locked until the patient and encounter are confirmed with consent.');
      return;
    }
    setUploadError(null);
    setUploadResult(null);
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        setUploadError('Microphone permission not granted');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await rec.startAsync();
      setRecording(rec);
      setRecordingStatus('recording');
    } catch (err: any) {
      setUploadError(err?.message ?? 'Failed to start recording');
      setRecording(null);
      setRecordingStatus('idle');
    }
  };

  const stopRecordingAndUpload = async () => {
    if (!recording) return;
    try {
      setRecordingStatus('uploading');
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(null);
      if (!uri) {
        throw new Error('No recording URI available');
      }
      await uploadRecording(uri);
      setRecordingStatus('idle');
    } catch (err: any) {
      setUploadError(err?.message ?? 'Failed to stop or upload recording');
      setRecordingStatus('idle');
    }
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

  const buildWsUrl = () => {
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
    const query = params.length ? `?${params.join('&')}` : '';
    return `${base}/api/v1/audio/ws${query}`;
  };

  const startLiveTranscription = async () => {
    if (!localEncounterId) {
      setLiveError('Recording is locked until the patient and encounter are confirmed with consent.');
      return;
    }
    setLiveError(null);
    setLivePartialText(null);
    setLiveTotalBytes(0);

    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        setLiveError('Microphone permission not granted');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const wsUrl = buildWsUrl();
      const token = await getToken({ skipCache: true });
      if (!token) throw new Error('Your session has expired. Please sign in again.');
      const ws = new (WebSocket as any)(
        wsUrl,
        [],
        { headers: { Authorization: `Bearer ${token}` } },
      );

      setLiveStatus('connecting');

      ws.onopen = async () => {
        try {
          const rec = new Audio.Recording();
          await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
          await rec.startAsync();
          setLiveRecording(rec);
          setLiveStatus('recording');
        } catch (err: any) {
          setLiveError(err?.message ?? 'Failed to start live recording');
          setLiveStatus('idle');
          setLiveRecording(null);
          ws.close();
        }
      };

      ws.onmessage = (event: any) => {
        try {
          const data = JSON.parse(event.data);
          if (typeof data.partial_text === 'string') {
            setLivePartialText(data.partial_text);
          }
          if (typeof data.total_bytes === 'number') {
            setLiveTotalBytes(data.total_bytes);
          }
          if (data.type === 'final' && data.job) {
            setJob(data.job as TranscriptJob);
          }
        } catch {
          // ignore JSON parse errors
        }
      };

      ws.onerror = () => {
        setLiveError('WebSocket error');
      };

      ws.onclose = () => {
        setLiveStatus('idle');
        setLiveRecording(null);
        setLiveWs(null);
      };

      setLiveWs(ws);
    } catch (err: any) {
      setLiveError(err?.message ?? 'Failed to start live transcription');
      setLiveStatus('idle');
      setLiveRecording(null);
      if (liveWs) {
        try {
          liveWs.close();
        } catch {
          // ignore
        }
      }
      setLiveWs(null);
    }
  };

  const stopLiveTranscription = async () => {
    if (!liveRecording || !liveWs) return;
    try {
      setLiveStatus('sending');
      await liveRecording.stopAndUnloadAsync();
      const uri = liveRecording.getURI();
      setLiveRecording(null);
      if (!uri) {
        throw new Error('No recording URI available');
      }
      const base64Data = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      });
      liveWs.send(`AUDIO_BASE64:${base64Data}`);
      liveWs.send('stop');
    } catch (err: any) {
      setLiveError(err?.message ?? 'Failed to stop or send live recording');
      setLiveStatus('idle');
      if (liveWs) {
        try {
          liveWs.close();
        } catch {
          // ignore
        }
      }
      setLiveWs(null);
    }
  };

  const handleToggleLive = async () => {
    if (liveStatus === 'recording' || liveStatus === 'connecting') {
      await stopLiveTranscription();
    } else {
      await startLiveTranscription();
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="auto" />
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <Text style={styles.title}>AI Medical Transcription</Text>
        <Text style={styles.subtitle}>Mobile Client (Android / iOS)</Text>

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
          <TouchableOpacity style={styles.buttonSecondary} onPress={() => signOut()}>
            <Text style={styles.buttonSecondaryText}>Sign out</Text>
          </TouchableOpacity>
        </View>

        {/* Backend health */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Backend Health</Text>
          {healthLoading && <ActivityIndicator size="small" color="#007AFF" />}
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
              <Text style={styles.label}>Source language</Text>
              <TextInput
                style={styles.input}
                value={languageCode}
                onChangeText={setLanguageCode}
                placeholder="en-US"
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
                placeholder="Enter patient ID"
                autoCapitalize="none"
              />
              <TouchableOpacity style={styles.button} onPress={lookupPatient} disabled={patientLoading}>
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
              <TouchableOpacity style={styles.buttonSecondary} onPress={resetPatientWorkflow}>
                <Text style={styles.buttonSecondaryText}>Change Patient</Text>
              </TouchableOpacity>

              {patientConfirmed && (
                <>
                  <Text style={styles.label}>Choose active encounter</Text>
                  {encounters.map((encounter) => (
                    <TouchableOpacity
                      key={encounter.id}
                      style={[styles.encounterOption, selectedExternalEncounterId === encounter.id && styles.encounterOptionSelected]}
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
                  {selectedExternalEncounterId && (
                    <TouchableOpacity
                      style={styles.checkboxRow}
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
                      <Text style={styles.checkboxLabel}>The patient gave consent for this recording.</Text>
                    </TouchableOpacity>
                  )}
                  {recordingConsent && !localEncounterId && (
                    <TouchableOpacity style={styles.button} onPress={confirmEncounterForRecording} disabled={confirmLoading}>
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
            disabled={recordingStatus === 'uploading' || !localEncounterId}
          >
            {recordingStatus === 'recording' ? (
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

          {uploadError && <Text style={styles.errorText}>{uploadError}</Text>}

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
            disabled={liveStatus === 'sending' || !localEncounterId}
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
                <ActivityIndicator color="#007AFF" />
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
                {exportStatus?.status === 'failed' && (
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
          <ActivityIndicator size="large" color="#007AFF" />
        </View>
      </SafeAreaView>
    );
  }
  return isSignedIn ? <AuthenticatedApp /> : <MobileSignIn />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  scrollContent: {
    padding: 24,
    paddingBottom: 48,
  },
  signInContainer: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: '#555',
    marginBottom: 16,
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
    borderColor: '#ccc',
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
    borderColor: '#007AFF',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
  },
  checkboxChecked: {
    backgroundColor: '#007AFF',
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
    borderColor: '#ccc',
    borderRadius: 8,
    borderWidth: 1,
    padding: 12,
    marginTop: 8,
  },
  encounterOptionSelected: {
    borderColor: '#007AFF',
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
    backgroundColor: '#007AFF',
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
    borderColor: '#007AFF',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
  },
  buttonSecondaryText: {
    color: '#007AFF',
    fontWeight: '600',
  },
});
