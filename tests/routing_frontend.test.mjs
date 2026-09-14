import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../custom_components/adaptive_tts/frontend/adaptive-tts-root-panel.js", import.meta.url),
  "utf8",
);

test("routing UI explains priority and manual override precedence", () => {
  assert.match(source, /first matching enabled rule/i);
  assert.match(source, /manual next-response or continuous voice override always wins/i);
  assert.match(source, /Priority/);
  assert.match(source, /Enabled/);
});

test("routing UI uses Home Assistant native condition selector", () => {
  assert.match(source, /document\.createElement\("ha-selector"\)/);
  assert.match(source, /selector\.selector = \{ condition: \{\} \}/);
  assert.match(source, /AND \/ OR \/ NOT building blocks/);
});

test("routing UI exposes ordering, language, voice and save controls", () => {
  assert.match(source, /move-up/);
  assert.match(source, /move-down/);
  assert.match(source, /rule-language/);
  assert.match(source, /rule-voice/);
  assert.match(source, /Save routing rules/);
});
