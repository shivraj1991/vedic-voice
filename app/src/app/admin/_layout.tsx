/**
 * Console gate: only admin and advisor roles (from the server-verified `/me`).
 * The API refuses staff routes to anyone else anyway; this keeps learners out of
 * screens that would only show errors.
 */
import { Redirect, Stack } from 'expo-router';
import { Text } from 'react-native';

import { isStaff, useMe } from '@/api/ApiProvider';
import { describeError } from '@/api/client';
import { useSession } from '@/auth/session';
import { ErrorBox, Loading, Screen } from '@/ui/components';
import { colors, styles } from '@/ui/theme';

export default function AdminLayout() {
  const session = useSession();
  const me = useMe();

  if (session.status === 'loading') return <Loading />;
  if (session.status === 'signedOut') return <Redirect href="/sign-in" />;
  if (me.loading && !me.data) return <Loading />;
  if (me.error) {
    return (
      <Screen>
        <ErrorBox message={describeError(me.error)} onRetry={me.reload} />
      </Screen>
    );
  }
  if (!isStaff(me.data?.role)) {
    return (
      <Screen>
        <Text style={styles.h1}>No access</Text>
        <Text style={styles.text}>
          The console is for advisors and admins. Ask an admin to set your role.
        </Text>
      </Screen>
    );
  }
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerTintColor: colors.text,
        contentStyle: { backgroundColor: colors.bg },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Shlokas' }} />
      <Stack.Screen name="shlokas/[slug]/index" options={{ title: 'Shloka' }} />
      <Stack.Screen name="shlokas/[slug]/analyses/[id]" options={{ title: 'Word analysis' }} />
      <Stack.Screen name="recordings/index" options={{ title: 'Recordings' }} />
      <Stack.Screen name="recordings/[id]" options={{ title: 'Recording' }} />
      <Stack.Screen name="audit" options={{ title: 'Change history' }} />
    </Stack>
  );
}
