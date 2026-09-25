const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const box = {exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('helpers/researchFigures.ts', 'utf8'), {
  compilerOptions: {module:ts.ModuleKind.CommonJS},
}).outputText, box);
const resolve = box.exports.resolveResearchFigure;
const path = 'outputs/review_' + 'a'.repeat(32) + '/figures/method-map.png';
test('report figures require exact current-run artifact registration', () => {
  assert.equal(resolve('figures/method-map.png', {'chart_method-map': path}), path);
  assert.equal(resolve('figures/method-map.png', {}), null);
  for (const invalid of ['../../private.png', 'https://attacker.test/image.png', 'figures/../method-map.png'])
    assert.equal(resolve(invalid, {'chart_method-map': path}), null);
  for (const invalid of ['https://attacker.test/image.png', path.replace('/figures/', '/../figures/'), path.replace('method-map.png', 'other.png')])
    assert.equal(resolve('figures/method-map.png', {'chart_method-map': invalid}), null);
});
