import test from 'node:test';
import assert from 'node:assert/strict';
import { applyTheme, curatedThemes, presets } from '../app/ui/personalization.mjs';

test('all curated appearances apply without changing behavior', () => {
  const before = JSON.stringify(presets);
  for (const theme of Object.values(curatedThemes)) {
    const properties = new Map();
    const element = { style: { setProperty: (key, value) => properties.set(key, value) }, dataset: {} };
    applyTheme(element, theme);
    assert.equal(properties.get('--background'), theme.background);
    assert.equal(properties.get('--size'), '16px');
    assert.equal(element.dataset.density, 'comfortable');
  }
  assert.equal(JSON.stringify(presets), before);
});
