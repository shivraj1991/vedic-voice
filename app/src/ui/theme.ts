/** Colours, spacing and shared styles. Plain StyleSheet: no UI library dependency. */
import { StyleSheet } from 'react-native';

export const colors = {
  bg: '#FBF8F3',
  surface: '#FFFFFF',
  text: '#1F1B16',
  muted: '#6B6259',
  border: '#E4DCD0',
  primary: '#9A3412',
  primaryText: '#FFFFFF',
  ok: '#166534',
  okBg: '#DCFCE7',
  warn: '#92400E',
  warnBg: '#FEF3C7',
  danger: '#B91C1C',
  dangerBg: '#FEE2E2',
  info: '#1E40AF',
  infoBg: '#DBEAFE',
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: space.lg, gap: space.md, maxWidth: 960, width: '100%', alignSelf: 'center' },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
    padding: space.md,
    gap: space.sm,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  h1: { fontSize: 22, fontWeight: '700', color: colors.text },
  h2: { fontSize: 17, fontWeight: '600', color: colors.text },
  text: { fontSize: 15, color: colors.text },
  muted: { fontSize: 13, color: colors.muted },
  deva: { fontSize: 20, color: colors.text },
  label: { fontSize: 13, fontWeight: '600', color: colors.muted },
  input: {
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    fontSize: 15,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  error: { color: colors.danger, fontSize: 14 },
});
