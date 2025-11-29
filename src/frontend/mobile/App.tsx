import React, { useEffect, useState } from 'react';
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
import * as FileSystem from 'expo-file-system';

// Base URL for the backend API. Can be overridden via EXPO_PUBLIC_API_BASE_URL at build time.
const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

// Authentication is controlled via an API key sent as X-API-Key. The value
// is provided by the user at runtime via the UI, not hard-coded.

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

export default function App() {
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

  const [authToken, setAuthToken] = useState<string>('');

  // HTTP upload recording state
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [recordingStatus, setRecordingStatus] = useState<'idle' | 'recording' | 'uploading'>('idle');
  const [uploadResult, setUploadResult] = useState<IngestAudioResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // WebSocket live transcription state
  const [liveWs, setLiveWs] = useState<any | null>(null);
  const [liveRecording, setLiveRecording] = useState<Audio.Recording | null>(null);
  const [liveStatus, setLiveStatus] = useState<'idle' | 'connecting' | 'recording' | 'sending'>('idle');
  const [livePartialText, setLivePartialText] = useState<string | null>(null);
  const [liveTotalBytes, setLiveTotalBytes] = useState<number>(0);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/v1/health`, {
          headers: authToken ? { 'X-API-Key': authToken } : undefined,
        });
        setHealth(response.data);
      } catch (err: any) {
        setHealthError(err?.message ?? 'Failed to reach backend');
      } finally {
        setHealthLoading(false);
      }
    };

    fetchHealth();
  }, [authToken]);

  const uploadRecording = async (uri: string) => {
    setUploadError(null);
    setUploadResult(null);
    try {
      const formData = new FormData();
      formData.append('file', {
        uri,
        name: 'recording.m4a',
        type: 'audio/m4a',
      } as any);

      const queryParts: string[] = [];
      if (languageCode) {
        queryParts.push(`language_code=${encodeURIComponent(languageCode)}`);
      }
      if (targetLanguage) {
        queryParts.push(`target_language=${encodeURIComponent(targetLanguage)}`);
      }
      const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';

      const res = await fetch(`${API_BASE_URL}/api/v1/audio/upload${queryString}`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          ...(authToken ? { 'X-API-Key': authToken } : {}),
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
          headers: authToken ? { 'X-API-Key': authToken } : undefined,
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
          headers: authToken ? { 'X-API-Key': authToken } : undefined,
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
      const ws = new (WebSocket as any)(
        wsUrl,
        [],
        authToken
          ? {
              headers: { 'X-API-Key': authToken },
            }
          : undefined,
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

        {/* Authentication */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Authentication</Text>
          <Text style={styles.label}>API Key (X-API-Key)</Text>
          <TextInput
            style={styles.input}
            value={authToken}
            onChangeText={setAuthToken}
            placeholder="Enter API key or leave blank"
            secureTextEntry
          />
          <Text style={styles.hint}>
            Used for authenticated backend calls when API key auth is enabled.
          </Text>
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
          <Text style={styles.sectionTitle}>Record & Upload Audio</Text>
          <Text style={styles.hint}>
            Uses your microphone and uploads to /api/v1/audio/upload.
          </Text>

          <TouchableOpacity
            style={styles.button}
            onPress={handleToggleRecording}
            disabled={recordingStatus === 'uploading'}
          >
            {recordingStatus === 'recording' ? (
              <Text style={styles.buttonText}>Stop & Upload</Text>
            ) : recordingStatus === 'uploading' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Start Recording</Text>
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
            disabled={liveStatus === 'sending'}
          >
            {liveStatus === 'recording' || liveStatus === 'connecting' ? (
              <Text style={styles.buttonText}>Stop & Send</Text>
            ) : liveStatus === 'sending' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Start Live Session</Text>
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
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
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
