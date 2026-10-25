import test from 'node:test';
import assert from 'node:assert/strict';
import {translate} from '../coach-i18n.js';
test('locale changes labels but preserves numerical evidence and IDs', () => {
  assert.equal(translate('Feasibility index','zh'),'可行性指数');
  const text = 'Pass to H02\nValue gain = 0.069 × 0.1949';
  assert.equal(translate(text,'en'),text);
  assert.equal(translate(text,'zh'),'传给 H02\n价值增益 = 0.069 × 0.1949');
});
test('hypothesis labels remain explicitly hypothetical in Chinese', () => {
  const text = translate('HYPOTHESIS · quick · intercepted. Not actual match footage.','zh');
  assert.ok(text.includes('假设推演')); assert.ok(text.includes('并非实际比赛后续'));
});
