/**
 * Console screens end to end (routes + providers + API client) against a fake API:
 * role gating, what each role can do, and exactly what is sent to the server.
 */
import { act, fireEvent, screen, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';
import { renderRouter } from 'expo-router/testing-library';
import { Alert } from 'react-native';

import AdminLayout from '@/app/admin/_layout';
import Audit from '@/app/admin/audit';
import ShlokaList from '@/app/admin/index';
import RecordingScreen from '@/app/admin/recordings/[id]';
import Recordings from '@/app/admin/recordings/index';
import AnalysisScreen from '@/app/admin/shlokas/[slug]/analyses/[id]';
import ShlokaScreen from '@/app/admin/shlokas/[slug]/index';
import type { Morphology, Role } from '@/api/types';

import { fakeServer } from './fakeServer';
import { analysis, recording, shloka, SUMMARY, TAT_ACC, TAT_NOM } from './fixtures';

jest.mock('expo-audio', () => ({
  useAudioPlayer: () => ({ play: jest.fn(), pause: jest.fn(), seekTo: jest.fn() }),
  useAudioPlayerStatus: () => ({ playing: false, isLoaded: false, currentTime: 0, duration: 0 }),
}));

const ROUTES = {
  'admin/_layout': AdminLayout,
  'admin/index': ShlokaList,
  'admin/shlokas/[slug]/index': ShlokaScreen,
  'admin/shlokas/[slug]/analyses/[id]': AnalysisScreen,
  'admin/recordings/index': Recordings,
  'admin/recordings/[id]': RecordingScreen,
  'admin/audit': Audit,
};

function open(role: Role, url: string, routes: Record<string, unknown>) {
  const server = fakeServer(role, routes);
  renderRouter(ROUTES, { initialUrl: url, wrapper: server.Providers });
  return server;
}

/** Native confirm dialogs: press "Continue". */
function acceptConfirms() {
  return jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => {
    buttons?.find((b) => b.text === 'Continue')?.onPress?.();
  });
}

afterEach(() => jest.restoreAllMocks());

it('keeps learners out of the console', async () => {
  const server = open('learner', '/admin', { 'GET /admin/shlokas': [SUMMARY] });
  expect(await screen.findByText('No access')).toBeTruthy();
  expect(server.sent('GET', '/admin/shlokas')).toHaveLength(0);
});

it('lists shlokas with review progress', async () => {
  open('admin', '/admin', { 'GET /admin/shlokas': [SUMMARY] });
  expect(await screen.findByText('Gāyatrī Mantra')).toBeTruthy();
  expect(screen.getByText('Words reviewed 1/2')).toBeTruthy();
  expect(screen.getByText(/1 of 1 shlokas need review/)).toBeTruthy();
  expect(screen.getByText(/can edit; an advisor verifies/)).toBeTruthy();
});

it('lets admins edit but only advisors verify', async () => {
  open('admin', '/admin/shlokas/gayatri', { 'GET /admin/shlokas/gayatri': shloka() });
  expect(await screen.findByText('Save changes')).toBeTruthy();
  expect(screen.queryByText('Verify shloka')).toBeNull();
});

it('sends only the edited field and warns when it un-verifies the shloka', async () => {
  const server = open('admin', '/admin/shlokas/gayatri', {
    'GET /admin/shlokas/gayatri': shloka({ verified: true, verified_by: 'user_advisor' }),
    'PATCH /admin/shlokas/gayatri': shloka({ translation: 'That excellent glory' }),
  });
  fireEvent.changeText(await screen.findByLabelText('Translation'), 'That excellent glory');
  expect(screen.getByText('Saving will send this shloka back to review.')).toBeTruthy();
  const alert = acceptConfirms();
  fireEvent.press(screen.getByText('Save changes'));
  await waitFor(() => expect(server.sent('PATCH', '/admin/shlokas/gayatri')).toHaveLength(1));
  expect(alert).toHaveBeenCalled();
  expect(server.sent('PATCH', '/admin/shlokas/gayatri')[0]?.body).toEqual({
    translation: 'That excellent glory',
  });
});

it('advisor verifies a shloka after confirming unreviewed words', async () => {
  const server = open('advisor', '/admin/shlokas/gayatri', {
    'GET /admin/shlokas/gayatri': shloka(),
    'POST /admin/shlokas/gayatri/verify': shloka({ verified: true, verified_by: 'user_advisor' }),
  });
  expect(await screen.findByText(/1 of 2 word analyses still need review/)).toBeTruthy();
  const alert = acceptConfirms();
  fireEvent.press(screen.getByText('Verify shloka'));
  await waitFor(() => expect(server.sent('POST', '/admin/shlokas/gayatri/verify')).toHaveLength(1));
  expect(alert.mock.calls[0]?.[0]).toBe('Some words are not reviewed');
  expect(await screen.findByText(/verified by user_advisor/)).toBeTruthy();
});

it('advisor picks a reading, adds the meaning, saves, then verifies', async () => {
  let current = shloka();
  const server = open('advisor', '/admin/shlokas/gayatri/analyses/a-tat', {
    'GET /admin/shlokas/gayatri': () => current,
    'PATCH /admin/word-analyses/a-tat': (body: unknown) => {
      const b = body as { meaning: string; morphology: Morphology };
      const saved = analysis({ meaning: b.meaning, morphology: b.morphology });
      current = shloka({ words: [{ ...current.words[0]!, analyses: [saved] }, current.words[1]!] });
      return { id: 'a-tat', verified: false };
    },
    'POST /admin/word-analyses/a-tat/verify': { id: 'a-tat', verified: true },
  });

  expect(await screen.findByText('3 candidate readings', { exact: false })).toBeTruthy();
  expect(screen.getByText(/Choose a reading .* before verifying/)).toBeTruthy();

  fireEvent.press(screen.getByText(TAT_ACC.label));
  fireEvent.changeText(screen.getByLabelText('Meaning (short)'), 'that');
  fireEvent.press(screen.getByText('Save'));

  await waitFor(() => expect(server.sent('PATCH', '/admin/word-analyses/a-tat')).toHaveLength(1));
  const body = server.sent('PATCH', '/admin/word-analyses/a-tat')[0]?.body as Record<
    string,
    unknown
  >;
  expect(body.meaning).toBe('that');
  expect((body.morphology as { chosen: unknown }).chosen).toEqual(TAT_ACC);
  expect(body).not.toHaveProperty('lemma'); // same lemma as before

  await waitFor(() => expect(screen.queryByText('Save your changes before verifying.')).toBeNull());
  expect(screen.queryByText(/Choose a reading .* before verifying/)).toBeNull();
  fireEvent.press(await screen.findByText('Verify'));
  await waitFor(() =>
    expect(server.sent('POST', '/admin/word-analyses/a-tat/verify')).toHaveLength(1),
  );
});

it('labels a word in a recording as ground truth', async () => {
  const server = open('advisor', '/admin/recordings/rec-1', {
    'GET /admin/audio/rec-1': recording(),
    'PUT /admin/word-labels': undefined,
  });
  expect(await screen.findByText('Word labels (0/2)')).toBeTruthy();
  expect(screen.getByText('Verify recording')).toBeTruthy();

  fireEvent.press(screen.getAllByText('Needs work')[1]!);
  fireEvent.press(screen.getByText('Long vowel said short'));
  fireEvent.press(screen.getAllByText('Save label')[1]!);

  await waitFor(() => expect(server.sent('PUT', '/admin/word-labels')).toHaveLength(1));
  expect(server.sent('PUT', '/admin/word-labels')[0]?.body).toEqual({
    audio_asset_id: 'rec-1',
    shloka_word_id: 'w1',
    ok: false,
    issue_code: 'vowel_length_short',
    note: null,
  });
  expect(await screen.findByText('Word labels (1/2)')).toBeTruthy();
});

it('cannot activate a reference before an advisor verifies it', async () => {
  open('admin', '/admin/recordings/rec-1', { 'GET /admin/audio/rec-1': recording() });
  expect(await screen.findByText('Make active reference')).toBeTruthy();
  expect(screen.queryByText('Verify recording')).toBeNull();
  expect(screen.getByText(/must verify this recording before it can be made active/)).toBeTruthy();
});

it('shows fresh progress when going back after verifying a word', async () => {
  let current = shloka();
  open('advisor', '/admin/shlokas/gayatri', {
    'GET /admin/shlokas/gayatri': () => current,
    'POST /admin/word-analyses/a-savitur/verify': { id: 'a-savitur', verified: true },
    'POST /admin/word-analyses/a-tat/verify': () => {
      const tat = analysis({ meaning: 'that', verified: true });
      current = shloka({ words: [{ ...current.words[0]!, analyses: [tat] }, current.words[1]!] });
      return { id: 'a-tat', verified: true };
    },
  });
  expect(await screen.findByText('Words (1/2 reviewed)')).toBeTruthy();
  current = shloka({
    words: [
      {
        ...current.words[0]!,
        analyses: [
          analysis({ meaning: 'that', morphology: { ...analysis().morphology, chosen: TAT_NOM } }),
        ],
      },
      current.words[1]!,
    ],
  });
  fireEvent.press(screen.getAllByText('tat').at(-1)!); // the analysis link (pada), not the word heading
  fireEvent.press(await screen.findByText('Verify'));
  await waitFor(() => expect(screen.queryByText('Verify')).toBeNull());
  act(() => router.back());
  expect(await screen.findByText('Words (2/2 reviewed)')).toBeTruthy();
});

it('does not let an advisor verify the analyser proposal without choosing it', async () => {
  const proposalOnly = analysis({ meaning: 'that' }); // meaning set, no explicit choice
  open('advisor', '/admin/shlokas/gayatri/analyses/a-tat', {
    'GET /admin/shlokas/gayatri': shloka({
      words: [{ ...shloka().words[0]!, analyses: [proposalOnly] }, shloka().words[1]!],
    }),
  });
  expect(await screen.findByText(/Choose a reading .* before verifying/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Verify' })).toBeDisabled();
});
