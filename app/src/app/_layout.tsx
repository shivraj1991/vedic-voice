/** Root: configuration check, auth, API client, navigation stack. */
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Text } from 'react-native';

import { ApiProvider } from '@/api/ApiProvider';
import { AuthRoot } from '@/auth/AuthRoot';
import { apiUrlFromEnv, authModeFromEnv } from '@/auth/config';
import { Screen } from '@/ui/components';
import { colors, styles } from '@/ui/theme';

const authMode = authModeFromEnv();
const apiUrl = apiUrlFromEnv();

export default function RootLayout() {
  if (authMode.kind === 'missing' || !apiUrl) {
    return (
      <Screen>
        <Text style={styles.h1}>Vedic Voice is not configured</Text>
        <Text style={styles.text}>
          {authMode.kind === 'missing'
            ? authMode.reason
            : 'Set EXPO_PUBLIC_API_URL (see app/.env.example).'}
        </Text>
      </Screen>
    );
  }
  return (
    <AuthRoot mode={authMode}>
      <ApiProvider baseUrl={apiUrl}>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.bg },
            headerTintColor: colors.text,
            contentStyle: { backgroundColor: colors.bg },
          }}
        >
          <Stack.Screen name="index" options={{ title: 'Vedic Voice' }} />
          <Stack.Screen name="sign-in" options={{ title: 'Sign in' }} />
          <Stack.Screen name="admin" options={{ headerShown: false }} />
        </Stack>
      </ApiProvider>
    </AuthRoot>
  );
}
