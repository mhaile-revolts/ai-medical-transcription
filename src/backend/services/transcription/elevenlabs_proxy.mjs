import { ReplitConnectors } from '@replit/connectors-sdk';

async function readInput() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

async function main() {
  const input = await readInput();
  const audio = Buffer.from(input.audio_base64, 'base64');
  if (!audio.length) throw new Error('Audio file is empty');

  const form = new FormData();
  form.append('model_id', input.model_id || 'scribe_v2_medical');
  form.append(
    'file',
    new Blob([audio], { type: input.content_type || 'application/octet-stream' }),
    input.file_name || 'recording.audio',
  );
  if (input.language_code) form.append('language_code', input.language_code);

  // Zero Retention Mode is enforced by the provider for eligible Enterprise
  // accounts; startup separately requires the operator's BAA/ZRM confirmation.
  const client = new ReplitConnectors();
  const response = await client.proxy(
    'elevenlabs',
    '/v1/speech-to-text?enable_logging=false',
    { method: 'POST', body: form },
  );
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(`ElevenLabs returned an unreadable response (${response.status})`);
  }
  if (!response.ok) {
    throw new Error(`ElevenLabs transcription failed (${response.status})`);
  }

  process.stdout.write(JSON.stringify({
    text: body.text,
    language_code: body.language_code,
    language_probability: body.language_probability,
  }));
}

main().catch((error) => {
  process.stdout.write(JSON.stringify({ error: error?.message || 'ElevenLabs transcription failed' }));
  process.exitCode = 1;
});
