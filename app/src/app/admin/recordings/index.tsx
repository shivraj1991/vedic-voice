/**
 * Reference and test recordings: list (filter by shloka) and upload.
 * Uploads go straight to private storage via a short-lived signed URL.
 */
import * as DocumentPicker from 'expo-document-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { useApi } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import type { AssetKind, AudioAsset, ShlokaSummary } from '@/api/types';
import { useReloadOnFocus } from '@/api/useReloadOnFocus';
import { useResource } from '@/api/useResource';
import { audioContentType, type PickedAudio, uploadRecording } from '@/console/audioUpload';
import {
  Badge,
  Button,
  Card,
  Chip,
  ErrorBox,
  Field,
  formatDate,
  Loading,
  Notice,
  Screen,
} from '@/ui/components';
import { space, styles } from '@/ui/theme';

function AssetRow({ a }: { a: AudioAsset }) {
  return (
    <Pressable
      accessibilityRole="link"
      onPress={() => router.push({ pathname: '/admin/recordings/[id]', params: { id: a.id } })}
      style={({ pressed }) => [styles.card, { opacity: pressed ? 0.8 : 1 }]}
    >
      <View style={styles.row}>
        <Text style={styles.h2}>{a.shloka_title}</Text>
        <Badge text={a.kind} tone="info" />
        {a.verified ? (
          <Badge text="Verified" tone="ok" />
        ) : (
          <Badge text="Needs review" tone="warn" />
        )}
        {a.is_active_reference ? <Badge text="Active reference" tone="ok" /> : null}
      </View>
      <Text style={styles.muted}>
        {[a.reciter, a.license, a.attribution].filter(Boolean).join(' · ') || 'No details'} ·{' '}
        {formatDate(a.created_at)}
      </Text>
    </Pressable>
  );
}

function UploadForm({ shlokas, onDone }: { shlokas: ShlokaSummary[]; onDone: () => void }) {
  const api = useApi();
  const [slug, setSlug] = useState<string | null>(null);
  const [kind, setKind] = useState<AssetKind>('reference');
  const [file, setFile] = useState<PickedAudio | null>(null);
  const [reciter, setReciter] = useState('');
  const [license, setLicense] = useState('');
  const [attribution, setAttribution] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick() {
    setError(null);
    const res = await DocumentPicker.getDocumentAsync({
      type: 'audio/*',
      copyToCacheDirectory: true,
    });
    const asset = res.canceled ? null : res.assets[0];
    if (!asset) return;
    if (!audioContentType(asset.name, asset.mimeType)) {
      setError('Unsupported audio format. Use m4a, aac, ogg, wav or flac.');
      return;
    }
    setFile({ name: asset.name, uri: asset.uri, mimeType: asset.mimeType, file: asset.file });
  }

  async function upload() {
    if (!slug || !file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadRecording(api, slug, kind, file, {
        reciter,
        license,
        attribution,
        source_url: sourceUrl,
      });
      setFile(null);
      onDone();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  const needsLicense = kind === 'test' && !(license.trim() && attribution.trim());
  return (
    <Card>
      <Text style={styles.h2}>Add a recording</Text>
      <Text style={styles.label}>Shloka</Text>
      <View style={styles.row}>
        {shlokas.map((s) => (
          <Chip
            key={s.slug}
            text={s.title}
            selected={slug === s.slug}
            onPress={() => setSlug(s.slug)}
          />
        ))}
      </View>
      <Text style={styles.label}>Kind</Text>
      <View style={styles.row}>
        <Chip
          text="Reference (what learners hear)"
          selected={kind === 'reference'}
          onPress={() => setKind('reference')}
        />
        <Chip
          text="Test (for scoring evaluation)"
          selected={kind === 'test'}
          onPress={() => setKind('test')}
        />
      </View>
      <Field label="Reciter" value={reciter} onChangeText={setReciter} />
      <Field
        label="License"
        value={license}
        onChangeText={setLicense}
        placeholder="e.g. CC-BY-4.0, or owned"
        hint={kind === 'test' ? 'Required for test recordings.' : undefined}
      />
      <Field
        label="Attribution"
        value={attribution}
        onChangeText={setAttribution}
        hint={kind === 'test' ? 'Required for test recordings.' : undefined}
      />
      <Field
        label="Source URL"
        value={sourceUrl}
        onChangeText={setSourceUrl}
        autoCapitalize="none"
      />
      <View style={styles.row}>
        <Button
          title={file ? 'Change file' : 'Choose audio file'}
          kind="secondary"
          onPress={pick}
          disabled={busy}
        />
        {file ? <Text style={styles.text}>{file.name}</Text> : null}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button
        title={busy ? 'Uploading…' : 'Upload'}
        onPress={upload}
        disabled={!slug || !file || needsLicense || busy}
      />
    </Card>
  );
}

export default function Recordings() {
  const params = useLocalSearchParams<{ shloka?: string }>();
  const api = useApi();
  const [filter, setFilter] = useState<string | undefined>(params.shloka);
  const [showUpload, setShowUpload] = useState(false);
  const shlokas = useResource(() => api.listShlokas(), [api]);
  const assets = useResource(() => api.listAudio(filter), [api, filter]);
  useReloadOnFocus(assets.reload);

  return (
    <Screen>
      <Notice>
        Learners hear the active reference recording of each shloka. A reference must be verified by
        an advisor before it can be made active.
      </Notice>
      <View style={[styles.row, { gap: space.xs }]}>
        <Chip text="All shlokas" selected={!filter} onPress={() => setFilter(undefined)} />
        {shlokas.data?.map((s) => (
          <Chip
            key={s.slug}
            text={s.title}
            selected={filter === s.slug}
            onPress={() => setFilter(s.slug)}
          />
        ))}
      </View>
      {showUpload && shlokas.data ? (
        <UploadForm
          shlokas={shlokas.data}
          onDone={() => {
            setShowUpload(false);
            assets.reload();
          }}
        />
      ) : (
        <Button title="Add a recording" onPress={() => setShowUpload(true)} />
      )}
      {assets.error ? (
        <ErrorBox message={describeError(assets.error)} onRetry={assets.reload} />
      ) : null}
      {assets.loading && !assets.data ? <Loading /> : null}
      {assets.data && assets.data.length === 0 ? (
        <Text style={styles.muted}>No recordings yet.</Text>
      ) : null}
      {assets.data?.map((a) => (
        <AssetRow key={a.id} a={a} />
      ))}
    </Screen>
  );
}
