import { expect, test } from "@playwright/test";

async function setupPanel(page) {
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
    window.__rejectNextSave = false;
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
        if (message.type === "adaptive_tts/routing_save") {
          if (window.__rejectNextSave) {
            window.__rejectNextSave = false;
            const error = new Error("Condition is no longer valid");
            error.body = { message: "Condition is no longer valid" };
            throw error;
          }
          return { saved: true, rules: message.rules };
        }
        throw new Error(`Unexpected WebSocket request: ${message.type}`);
      },
    };
  });

  await expect(page.locator("#routing-status")).toHaveText("Rules loaded.");
  return { pageErrors, consoleErrors };
}

test("invalid routing draft is blocked before any save request", async ({ page }) => {
  const { pageErrors, consoleErrors } = await setupPanel(page);

  await page.locator(".rule-name").fill("");
  await expect(page.locator("#routing-status")).toHaveText("Unsaved changes.");

  const savesBefore = await page.evaluate(
    () => window.__adaptiveTtsCalls.filter((call) => call.type === "adaptive_tts/routing_save").length
  );
  await page.locator("#save-rules").click();

  await expect(page.locator("#routing-status")).toHaveText("Rule 1 needs a name.");
  await expect(page.locator("#routing-status")).toHaveClass(/error/);
  const savesAfter = await page.evaluate(
    () => window.__adaptiveTtsCalls.filter((call) => call.type === "adaptive_tts/routing_save").length
  );
  expect(savesAfter).toBe(savesBefore);
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("backend save rejection preserves the user's draft for retry", async ({ page }) => {
  const { pageErrors, consoleErrors } = await setupPanel(page);

  await page.locator(".rule-name").fill("Edited evening voice");
  await page.locator(".rule-voice").selectOption("other-voice");
  await expect(page.locator("#routing-status")).toHaveText("Unsaved changes.");

  await page.evaluate(() => {
    window.__rejectNextSave = true;
  });
  await page.locator("#save-rules").click();

  await expect(page.locator("#routing-status")).toHaveText("Condition is no longer valid");
  await expect(page.locator("#routing-status")).toHaveClass(/error/);
  await expect(page.locator(".rule-name")).toHaveValue("Edited evening voice");
  await expect(page.locator(".rule-voice")).toHaveValue("other-voice");
  await expect(page.locator("#save-rules")).toBeEnabled();

  await page.locator("#save-rules").click();
  await expect(page.locator("#routing-status")).toHaveText(
    "Routing rules saved. The Adaptive TTS entity is reloading with the new policy."
  );
  await expect(page.locator("#routing-status")).toHaveClass(/success/);

  const saveCalls = await page.evaluate(() =>
    window.__adaptiveTtsCalls.filter((call) => call.type === "adaptive_tts/routing_save")
  );
  expect(saveCalls).toHaveLength(2);
  expect(saveCalls[0].rules[0]).toMatchObject({
    id: "evening",
    name: "Edited evening voice",
    voice: "other-voice",
  });
  expect(saveCalls[1]).toEqual(saveCalls[0]);
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
