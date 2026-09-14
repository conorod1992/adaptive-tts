import { expect, test } from "@playwright/test";

test("switching routing entity protects unsaved edits", async ({ page }) => {
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
                engine_id: "tts.browser_one",
                name: "Browser One",
                is_adaptive: true,
                available: true,
              },
              {
                engine_id: "tts.browser_two",
                name: "Browser Two",
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
                id: message.entity_id === "tts.browser_one" ? "one" : "two",
                name: message.entity_id === "tts.browser_one" ? "Rule one" : "Rule two",
                enabled: true,
                conditions: [
                  {
                    condition: "state",
                    entity_id: "input_boolean.route",
                    state: "on",
                  },
                ],
                language: "en-US",
                voice: message.entity_id === "tts.browser_one" ? "voice-one" : "voice-two",
              },
            ],
          };
        }
        if (message.type === "adaptive_tts/engine") {
          return {
            engine_id: message.engine_id,
            default_language: "en-US",
            supported_languages: ["en-US"],
            voices: [
              {
                voice_id: message.engine_id === "tts.browser_one" ? "voice-one" : "voice-two",
                name: "Voice",
              },
            ],
          };
        }
        throw new Error(`Unexpected WebSocket request: ${message.type}`);
      },
    };
  });

  await expect(page.locator("#routing-engine")).toHaveValue("tts.browser_one");
  await expect(page.locator(".rule-name")).toHaveValue("Rule one");

  await page.locator(".rule-name").fill("Unsaved rule one");
  await expect(page.locator("#routing-status")).toHaveText("Unsaved changes.");

  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    expect(dialog.message()).toBe(
      "Discard unsaved routing changes and switch Adaptive TTS entity?"
    );
    await dialog.dismiss();
  });
  await page.locator("#routing-engine").selectOption("tts.browser_two");

  await expect(page.locator("#routing-engine")).toHaveValue("tts.browser_one");
  await expect(page.locator(".rule-name")).toHaveValue("Unsaved rule one");
  await expect(page.locator("#routing-status")).toHaveText("Unsaved changes.");

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.locator("#routing-engine").selectOption("tts.browser_two");

  await expect(page.locator("#routing-engine")).toHaveValue("tts.browser_two");
  await expect(page.locator(".rule-name")).toHaveValue("Rule two");
  await expect(page.locator("#routing-status")).toHaveText("Rules loaded.");

  const calls = await page.evaluate(() => window.__adaptiveTtsCalls);
  const routingGets = calls.filter((call) => call.type === "adaptive_tts/routing_get");
  expect(routingGets.map((call) => call.entity_id)).toEqual([
    "tts.browser_one",
    "tts.browser_two",
  ]);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
