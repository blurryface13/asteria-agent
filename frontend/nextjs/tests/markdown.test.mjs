import assert from 'node:assert/strict';
import test from 'node:test';
import { markdownToHtml } from '../helpers/markdownHelper.ts';

test('renders parsed inline and block math, including heading math', async () => {
  const output = await markdownToHtml('# Why $\\sqrt{d_k}$?\n\n$$\n\\frac{x}{y}\n$$');
  assert.match(output, /class="katex"/);
  assert.match(output, /katex-display/);
  assert.doesNotMatch(output, /<code class="language-math/);
});

test('code stays literal and untrusted HTML is sanitized', async () => {
  const output = await markdownToHtml('`$x$`\n\n```tex\n$x$\n```\n\n<img src=x onerror="alert(1)"><script>alert(1)</script>');
  assert.match(output, /<code>\$x\$<\/code>/);
  assert.doesNotMatch(output, /class="katex"/);
  assert.doesNotMatch(output, /onerror|<script/);
});

test('math cannot authorize external HTML or javascript links', async () => {
  const output = await markdownToHtml('$\\href{javascript:alert(1)}{bad}$');
  assert.doesNotMatch(output, /href="javascript:/);
});
