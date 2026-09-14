import { expect, test } from "@playwright/test";

test("routing panel creates, updates conditions, deletes, and saves only visible rules", async ({ page }) => {
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
                engine_id: "tts.create_delete_adaptive",
                name: "Create/Delete Adaptive TTS",
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
                id: "existing",
                name: "Existing rule",
                enabled: true,
                conditions: [
                  {
                    condition: "state",
                    entity_id: "input_boolean.existing",
                    state: "on",
                  },
                ],
                language: "en-US",
                voice: "normal",
              },
            ],
          };
        }
        if (message.type === "adaptive_tts/engine") {
          return {
            engine_id: "tts.create_delete_adaptive",
            default_language: "en-US",
            supported_languages: ["en-US", "en-GB"],
            voices: [
              { voice_id: "normal", name: "Normal" },
              { voice_id: "whisper", name: "Whisper" },
            ],
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
  await expect(page.locator(".rule")).toHaveCount(1);

  await page.locator("#add-rule").click();
  await expect(page.locator(".rule")).toHaveCount(2);
  await expect(page.locator("#routing-status")).toContainText("New rule added.");

  const newRule = page.locator(".rule").nth(1);
  await expect(newRule.locator(".rule-name")).toHaveValue("Routing rule 2");
  await expect(newRule.locator(".rule-language")).toHaveValue("en-US");
  await expect(newRule.locator(".rule-voice")).toHaveValue("normal");

  await newRule.locator(".rule-name").fill("Created rule");
  await newRule.locator(".rule-language").selectOption("en-GB");
  await newRule.locator(".rule-voice").selectOption("whisper");

  await newRule.locator("ha-selector").evaluate((selector) => {
    selector.dispatchEvent(
      new CustomEvent("value-changed", {
        detail: {
          value: [
            {
              condition: "state",
              entity_id: "binary_sensor.created_rule",
              state: "on",
            },
          ],
        },
        bubbles: true,
        composed: true,
      })
    );
  });
  await expect(page.locator("#routing-status")).toHaveText("Unsaved changes.");

  await page.locator(".rule").first().locator(".delete-rule").click();
  await expect(page.locator(".rule")).toHaveCount(1);
  await expect(page.locator(".rule-name")).toHaveValue("Created rule");
  await expect(page.locator("#routing-status")).toHaveText(
    "Rule removed. Save to apply this change."
  );

  await page.locator("#save-rules").click();
  await expect(page.locator("#routing-status")).toHaveText(
    "Routing rules saved. The Adaptive TTS entity is reloading with the new policy."
  );

  const calls = await page.evaluate(() => window.__adaptiveTtsCalls);
  const saveCalls = calls.filter((call) => call.type === "adaptive_tts/routing_save");
  expect(saveCalls).toHaveLength(1);
  expect(saveCalls[0].entity_id).toBe("tts.create_delete_adaptive");
  expect(saveCalls[0].rules).toHaveLength(1);
  expect(saveCalls[0].rules[0]).toMatchObject({
    name: "Created rule",
    enabled: true,
    conditions: [
      {
        condition: "state",
        entity_id: "binary_sensor.created_rule",
        state: "on",
      },
    ],
    language: "en-GB",
    voice: "whisper",
  });
  expect(saveCalls[0].rules[0].id).toEqual(expect.any(String));
  expect(saveCalls[0].rules[0].id).not.toBe("");
  expect(saveCalls[0].rules.some((rule) => rule.id === "existing")).toBe(false);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
