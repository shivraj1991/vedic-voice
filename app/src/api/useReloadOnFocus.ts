/**
 * Reload a screen's data when the user comes back to it (e.g. after verifying a
 * word on the next screen). Stack screens stay mounted, so without this they
 * would show what they loaded the first time.
 */
import { useFocusEffect } from 'expo-router';
import { useCallback, useRef } from 'react';

export function useReloadOnFocus(reload: () => void): void {
  const firstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (firstFocus.current) {
        firstFocus.current = false; // the initial load already ran
        return;
      }
      reload();
    }, [reload]),
  );
}
