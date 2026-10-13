/** Small shared building blocks for the console screens. */
import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  type TextInputProps,
  View,
} from 'react-native';

import { colors, space, styles } from './theme';

type ButtonKind = 'primary' | 'secondary' | 'danger';

export function Button({
  title,
  onPress,
  disabled,
  kind = 'primary',
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  kind?: ButtonKind;
}) {
  const bg =
    kind === 'primary' ? colors.primary : kind === 'danger' ? colors.danger : colors.surface;
  const fg = kind === 'secondary' ? colors.text : colors.primaryText;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => ({
        backgroundColor: bg,
        borderColor: kind === 'secondary' ? colors.border : bg,
        borderWidth: 1,
        borderRadius: 8,
        paddingHorizontal: space.lg,
        paddingVertical: space.sm,
        opacity: disabled ? 0.45 : pressed ? 0.8 : 1,
      })}
    >
      <Text style={{ color: fg, fontWeight: '600', fontSize: 15 }}>{title}</Text>
    </Pressable>
  );
}

const BADGE = {
  ok: [colors.okBg, colors.ok],
  warn: [colors.warnBg, colors.warn],
  info: [colors.infoBg, colors.info],
  danger: [colors.dangerBg, colors.danger],
} as const;

export function Badge({ text, tone }: { text: string; tone: keyof typeof BADGE }) {
  const [bg, fg] = BADGE[tone];
  return (
    <View
      style={{ backgroundColor: bg, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 }}
    >
      <Text style={{ color: fg, fontSize: 12, fontWeight: '600' }}>{text}</Text>
    </View>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? <Badge text="Verified" tone="ok" /> : <Badge text="Needs review" tone="warn" />;
}

export function Screen({ children }: { children: ReactNode }) {
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {children}
    </ScrollView>
  );
}

export function Card({ children }: { children: ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function Loading() {
  return (
    <View style={{ padding: space.xl, alignItems: 'center' }}>
      <ActivityIndicator color={colors.primary} />
    </View>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={[styles.card, { backgroundColor: colors.dangerBg, borderColor: colors.dangerBg }]}>
      <Text style={styles.error}>{message}</Text>
      {onRetry ? <Button title="Try again" kind="secondary" onPress={onRetry} /> : null}
    </View>
  );
}

export function Notice({
  children,
  tone = 'info',
}: {
  children: ReactNode;
  tone?: 'info' | 'warn';
}) {
  const [bg, fg] = BADGE[tone];
  return (
    <View style={[styles.card, { backgroundColor: bg, borderColor: bg }]}>
      <Text style={{ color: fg, fontSize: 14 }}>{children}</Text>
    </View>
  );
}

export function Field({
  label,
  hint,
  ...input
}: TextInputProps & { label: string; hint?: string }) {
  return (
    <View style={{ gap: space.xs }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        style={[styles.input, input.multiline ? { minHeight: 80, textAlignVertical: 'top' } : null]}
        placeholderTextColor={colors.muted}
        {...input}
      />
      {hint ? <Text style={styles.muted}>{hint}</Text> : null}
    </View>
  );
}

export function Chip({
  text,
  selected,
  onPress,
}: {
  text: string;
  selected?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected }}
      onPress={onPress}
      style={{
        borderRadius: 999,
        borderWidth: 1,
        borderColor: selected ? colors.primary : colors.border,
        backgroundColor: selected ? colors.primary : colors.surface,
        paddingHorizontal: space.md,
        paddingVertical: 6,
      }}
    >
      <Text style={{ color: selected ? colors.primaryText : colors.text, fontSize: 14 }}>
        {text}
      </Text>
    </Pressable>
  );
}

/** Yes/no confirmation that works on web (Alert is a no-op there) and native. */
export function confirm(title: string, message: string): Promise<boolean> {
  if (Platform.OS === 'web') {
    return Promise.resolve(globalThis.confirm?.(`${title}\n\n${message}`) ?? false);
  }
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: 'Continue', onPress: () => resolve(true) },
    ]),
  );
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
