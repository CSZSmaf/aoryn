import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const markdown = require(path.resolve(import.meta.dirname, "../vendor/desktop-markdown.js"));
const originalKatex = globalThis.katex;

function withKatex(mock, fn) {
  globalThis.katex = mock;
  try {
    fn();
  } finally {
    globalThis.katex = originalKatex;
  }
}

function runTest(name, fn) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

runTest("renders core markdown blocks and inline formatting", () => {
  const html = markdown.render(
    [
      "# Title",
      "",
      "A **bold** line with a [link](https://example.com).",
      "",
      "> quoted",
      "",
      "- `one`",
      "- two",
      "",
      "```js",
      "const answer = 42;",
      "```",
    ].join("\n")
  );

  assert.match(html, /<h1>Title<\/h1>/);
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<a href="https:\/\/example\.com"/);
  assert.match(html, /<blockquote>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<code>one<\/code>/);
  assert.match(html, /assistant-code/);
  assert.match(html, /const answer = 42;/);
});

runTest("renders GFM-style tables", () => {
  const html = markdown.render(
    [
      "| name | value |",
      "| :--- | ---: |",
      "| left | 12 |",
    ].join("\n")
  );

  assert.match(html, /<table>/);
  assert.match(html, /assistant-table__cell--left/);
  assert.match(html, /assistant-table__cell--right/);
  assert.match(html, /left/);
  assert.match(html, /12/);
});

runTest("renders inline and block math formulas with KaTeX", () => {
  withKatex(
    {
      renderToString(source, options) {
        return `<span class="katex-mock" data-display="${options.displayMode ? "block" : "inline"}">${source}</span>`;
      },
    },
    () => {
      const html = markdown.render(
        [
          "Inline math: $E = mc^2$ and $\\sum_{i=1}^n i = \\frac{n(n+1)}{2}$.",
          "",
          "$$",
          "\\int_0^1 x^2 dx = \\frac{1}{3}",
          "$$",
        ].join("\n")
      );

      assert.match(html, /assistant-math--inline/);
      assert.match(html, /assistant-math--block/);
      assert.match(html, /assistant-math--katex/);
      assert.match(html, /class="katex-mock" data-display="inline">E = mc\^2</);
      assert.match(html, /class="katex-mock" data-display="block">\\int_0\^1 x\^2 dx = \\frac\{1\}\{3\}</);
    }
  );
});

runTest("falls back to styled math source when KaTeX rendering fails", () => {
  withKatex(
    {
      renderToString() {
        throw new Error("bad formula");
      },
    },
    () => {
      const html = markdown.render("Broken formula: $\\bad{1}$");
      assert.match(html, /assistant-math--fallback/);
      assert.match(html, /assistant-math-fallback/);
      assert.match(html, /\\bad\{1\}/);
    }
  );
});

runTest("rejects unsafe markdown links", () => {
  const html = markdown.render("[bad](javascript:alert(1))");
  assert.doesNotMatch(html, /href=/);
  assert.match(html, /bad/);
});

runTest("keeps incomplete fenced code in the streaming tail", () => {
  const source = ["Intro paragraph.", "", "```js", "const value = 1;"].join("\n");

  const parts = markdown.splitForStreaming(source);
  assert.equal(parts.committed, "Intro paragraph.\n\n");
  assert.equal(parts.tail, "```js\nconst value = 1;");

  const html = markdown.renderStreaming(source, { cursor: true });
  assert.match(html, /<p>Intro paragraph\.<\/p>/);
  assert.match(html, /assistant-tail__text/);
  assert.match(html, /const value = 1;/);
});

runTest("keeps incomplete block math in the streaming tail", () => {
  const source = ["Math intro.", "", "$$", "\\frac{a}{b}"].join("\n");

  const parts = markdown.splitForStreaming(source);
  assert.equal(parts.committed, "Math intro.\n\n");
  assert.equal(parts.tail, "$$\n\\frac{a}{b}");
});

runTest("advanceRevealContent reveals a partial chunk for a single full delta", () => {
  const firstStep = markdown.advanceRevealContent("", "Hello markdown world");
  assert.notEqual(firstStep.content, "");
  assert.notEqual(firstStep.content, "Hello markdown world");

  const finalStep = markdown.advanceRevealContent("Hello markdown world", "Hello markdown world");
  assert.equal(finalStep.content, "Hello markdown world");
  assert.equal(finalStep.done, true);
});
