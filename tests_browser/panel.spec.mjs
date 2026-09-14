import { expect, test } from "@playwright/test";

test("routing panel loads real web component and tests a rule", async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/tests_browser/harness.html");
  await page.waitForFunction(() => customElements.get("adaptive-tts-root-panel"));

  await page.evaluate(() => {
    window.__adaptiveTtsCalls = [];
    const panel = document.getElementById("panel");
    panel.hass = {
      callWS: async (message) => {
        window.__adaptiveTtsCalls.push(structuredClone(message));
        if (message.type === "adaptive_tts/info") {
          return {
            engines: [
              {
                engine_id: "tts.browser_adaptive",
                name: "Browser Adaptive TTS",
                is_adaptive: true,
                available: true,
              },
            ],
          };
        }
        if (message.type === "adaptive_tts/routing_get") {
          return {
            rules: [
              {
                id: "evening",
                name: "Evening voice",
                enabled: true,
                conditions: [
                  {
                    condition: "state",
                    entity_id: "input_boolean.evening",
                    state: "on",
                  },
                ],
                language: "en-GB",
                voice: "browser-voice",
              },
            ],
          };
        }
        if (message.type === "adaptive_tts/engine") {
          return {
            engine_id: "tts.browser_adaptive",
            default_language: "en-US",
            supported_languages: ["en-US", "en-GB"],
            voices: [
              { voice_id: "browser-voice", name: "Browser Voice" },
              { voice_id: "other-voice", name: "Other Voice" },
            ],
          };
        }
        if (message.type === "adaptive_tts/routing_test") {
          return {
            matches: true,
            enabled: true,
            would_win: true,
            winner_index: 0,
            winner_name: "Evening voice",
          };
        }
        throw new Error(`Unexpected WebSocket request: ${message.type}`);
      },
    };
  });

  await expect(page.locator("#routing-status")).toHaveText("Rules loaded.");
  await expect(page.locator("#routing-engine")).toHaveValue("tts.browser_adaptive");
  await expect(page.locator(".rule-name")).toHaveValue("Evening voice");
  await expect(page.locator(".rule-language")).toHaveValue("en-GB");
  await expect(page.locator(".rule-voice")).toHaveValue("browser-voice");

  await page.locator(".test-conditions").click();
  await expect(page.locator(".test-condition-result")).toHaveText(
    "Matches now — this rule would be selected."
  );
  await expect(page.locator(".test-condition-result")).toHaveClass(/success/);

  const calls = await page.evaluate(() => window.__adaptiveTtsCalls);
  expect(calls.map((call) => call.type)).toContain("adaptive_tts/info");
  expect(calls.map((call) => call.type)).toContain("adaptive_tts/routing_get");
  expect(calls.map((call) => call.type)).toContain("adaptive_tts/engine");
  expect(calls.at(-1)).toEqual({
    type: "adaptive_tts/routing_test",
    target_index: 0,
    rules: [
      {
        name: "Evening voice",
        enabled: true,
        conditions: [
          {
            condition: "state",
            entity_id: "input_boolean.evening",
            state: "on",
          },
        ],
      },
    ],
  });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("routing panel edits, reorders, and saves the exact visible rules", async ({
  page,
}) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/tests_browser/harness.html");
  await page.waitForFunction(() => customElements.get("adaptive-tts-root-panel"));

  await page.evaluate(() => {
    window.__adaptiveTtsCalls = [];
    const panel = document.getElementById("panel");
    panel.hass = {
      callWS: async (message) => {
        window.__adaptiveTtsCalls.push(structuredClone(message));
        if (message.type === "adaptive_tts/info") {
          return {
            engines: [
              {
                engine_id: "tts.browser_adaptive",
                name: "Browser Adaptive TTS",
                is_adaptive: true,
                available: true,
              },
            ],
          };
        }
        if (message.type === "adaptive_tts/routing_get") {
          return {
            rules: [
              {
                id: "quiet",
                name: "Quiet voice",
                enabled: true,
                conditions: [
                  {
                    condition: "state",
                    entity_id: "input_boolean.quiet",
                    state: "on",
                  },
                ],
                language: "en-US",
                voice: "normal-us",
              },
              {
                id: "evening",
                name: "Evening voice",
                enabled: true,
                conditions: [
                  {
                    condition: "state",
                    entity_id: "input_boolean.evening",
                    state: "on",
                  },
                ],
                language: "en-GB",
                voice: "browser-voice",
              },
            ],
          };
        }
        if (message.type === "adaptive_tts/engine") {
          const voices =
            message.language === "en-US"
              ? [
                  { voice_id: "normal-us", name: "Normal US" },
                  { voice_id: "alternate-us", name: "Alternate US" },
                ]
              : [
                  { voice_id: "browser-voice", name: "Browser Voice" },
                  { voice_id: "other-voice", name: "Other Voice" },
                ];
          return {
            engine_id: "tts.browser_adaptive",
            default_language: "en-US",
            supported_languages: ["en-US", "en-GB"],
            voices,
          };
        }
        if (message.type === "adaptive_tts/routing_save") {
          return { saved: true, rules: structuredClone(message.rules) };
        }
        throw new Error(`Unexpected WebSocket request: ${message.type}`);
      },
    };
  });

  await expect(page.locator("#routing-status")).toHaveText("Rules loaded.");
  await expect(page.locator(".rule")).toHaveCount(2);

  await page.locator(".rule").nth(1).locator(".move-up").click();
  await expect(page.locator(".rule-name").first()).toHaveValue("Evening voice");
  await expect(page.locator("#routing-status")).toHaveText(
    "Priority changed. Save to apply the new order."
  );

  await page.locator(".rule-name").first().fill("  Evening preferred  ");
  await expect(page.locator("#routing-status")).toHaveText("Unsaved changes.");

  await page.locator(".rule-language").first().selectOption("en-US");
  await expect(page.locator(".rule-voice").first()).toHaveValue("normal-us");
  await page.locator(".rule-voice").first().selectOption("alternate-us");

  await page.locator("#save-rules").click();
  await expect(page.locator("#routing-status")).toHaveText(
    "Routing rules saved. The Adaptive TTS entity is reloading with the new policy."
  );
  await expect(page.locator("#routing-status")).toHaveClass(/success/);

  const saveCall = await page.evaluate(() =>
    window.__adaptiveTtsCalls.findLast(
      (call) => call.type === "adaptive_tts/routing_save"
    )
  );
  expect(saveCall).toEqual({
    type: "adaptive_tts/routing_save",
    entity_id: "tts.browser_adaptive",
    rules: [
      {
        id: "evening",
        name: "Evening preferred",
        enabled: true,
        conditions: [
          {
            condition: "state",
            entity_id: "input_boolean.evening",
            state: "on",
          },
        ],
        language: "en-US",
        voice: "alternate-us",
      },
      {
        id: "quiet",
        name: "Quiet voice",
        enabled: true,
        conditions: [
          {
            condition: "state",
            entity_id: "input_boolean.quiet",
            state: "on",
          },
        ],
        language: "en-US",
        voice: "normal-us",
      },
    ],
  });

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
