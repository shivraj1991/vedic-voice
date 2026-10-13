/** Change history (content_audit): who changed or verified what, newest first. */
import { Text, View } from 'react-native';

import { useApi } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import type { AuditEntry } from '@/api/types';
import { useResource } from '@/api/useResource';
import { describeDiff } from '@/console/audit';
import { Badge, ErrorBox, formatDate, Loading, Screen } from '@/ui/components';
import { styles } from '@/ui/theme';

const TONE: Record<string, 'ok' | 'info' | 'warn'> = {
  verify: 'ok',
  create: 'info',
  activate: 'ok',
};

function Entry({ e }: { e: AuditEntry }) {
  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Badge text={e.action} tone={TONE[e.action] ?? 'warn'} />
        <Text style={styles.text}>{e.entity.replace('_', ' ')}</Text>
        <Text style={styles.muted}>
          by {e.actor} · {formatDate(e.at)}
        </Text>
      </View>
      {describeDiff(e.diff).map((line) => (
        <Text key={line} style={styles.muted}>
          {line}
        </Text>
      ))}
    </View>
  );
}

export default function Audit() {
  const api = useApi();
  const log = useResource(() => api.audit(undefined, 200), [api]);
  return (
    <Screen>
      {log.error ? <ErrorBox message={describeError(log.error)} onRetry={log.reload} /> : null}
      {log.loading && !log.data ? <Loading /> : null}
      {log.data && log.data.length === 0 ? <Text style={styles.muted}>No changes yet.</Text> : null}
      {log.data?.map((e) => (
        <Entry key={e.id} e={e} />
      ))}
    </Screen>
  );
}
