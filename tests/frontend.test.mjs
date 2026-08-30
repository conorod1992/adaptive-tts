import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.value = "";
    this.textContent = "";
    this.disabled = false;
    this.placeholder = "";
    this.type = "";
    this.step = "";
    this.className = "";
    if (this.tagName === "SELECT") this.options = [];
  }

  append(child) {
    this.children.push(child);
    if (this.tagName === "SELECT") {
      this.options.push(child);
      if (this.options.length === 1) this.value = child.value;
    }
  }

  replaceChildren(...children) {
    this.children = [];
    if (this.tagName === "SELECT") this.options = [];
    this.value = "";
    for (const child of children) this.append(child);
  }

  replaceWith(element) {
    this._root.replace(this.id, element);
  }

  pause() {}
  load() {}
  removeAttribute() {}
}

class FakeShadowRoot {
  constructor(ids = []) {
    this.elements = new Map();
    for (const id of ids) this.add(id, new FakeElement(this._tagFor(id)));
  }

  _tagFor(id) {
    if (["pipeline", "engine", "language", "voice", "override-engine", "override-language", "override-voice", "override-duration"].includes(id)) return "select";
    if (["set-override", "clear-override", "generate"].includes(id)) return "button";
    if (id === "audio") return "audio";
    return "div";
  }

  add(id, element) {
    element.id = id;
    element._root = this;
    this.elements.set(id, element);
    return element;
  }

  replace(id, element) {
    this.add(id, element);
  }

  getElementById(id) {
    if (!this.elements.has(id)) this.add(id, new FakeElement(this._tagFor(id)));
    return this.elements.get(id);
  }

  querySelectorAll(selector) {
    if (selector !== "[data-option]") return [];
    const options = this.getElementById("options");
    return options.children.flatMap((label) => label.children).filter((item) => item.dataset.option);
  }
}

globalThis.HTMLElement = class {};
globalThis.document = {
  createElement(tagName) {
    return new FakeElement(tagName);
  },
};
let PanelClass;
globalThis.customElements = {
  define(_name, cls) {
    PanelClass = cls;
  },
};

const source = fs.readFileSync(
  path.join(process.cwd(), "custom_components/adaptive_tts/frontend/adaptive-tts-panel.js"),
  "utf8",
);
vm.runInThisContext(source, { filename: "adaptive-tts-panel.js" });

function panelWith(ids) {
  const panel = new PanelClass();
  panel.shadowRoot = new FakeShadowRoot(ids);
  return panel;
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test("failed initial load is retryable", async () => {
  const panel = panelWith([
    "pipeline", "engine", "language", "voice", "override-engine",
    "override-language", "override-voice", "options", "set-override",
    "clear-override", "generate", "error", "override-error", "override-success",
  ]);
  let attempts = 0;
  panel._hass = {
    async callWS() {
      attempts += 1;
      if (attempts === 1) throw new Error("temporary failure");
      return {
        pipelines: [],
        engines: [{ engine_id: "tts.source", name: "Source", is_adaptive: false }],
      };
    },
  };
  panel._engineChanged = async () => {};

  await panel._load();
  assert.equal(panel._loaded, false);
  assert.equal(panel._loading, false);

  await panel._load();
  assert.equal(panel._loaded, true);
  assert.equal(panel._loading, false);
  assert.equal(attempts, 2);
  assert.deepEqual(
    panel.shadowRoot.getElementById("engine").options.map((item) => item.value),
    ["tts.source"],
  );
});

test("late engine metadata cannot overwrite a newer selection", async () => {
  const panel = panelWith(["engine", "language", "generate", "error"]);
  const engine = panel.shadowRoot.getElementById("engine");
  const requests = new Map();
  panel._hass = {
    callWS({ engine_id: engineId }) {
      const request = deferred();
      requests.set(engineId, request);
      return request.promise;
    },
  };
  panel._languageChanged = async () => {};

  engine.value = "tts.first";
  const first = panel._engineChanged();
  engine.value = "tts.second";
  const second = panel._engineChanged();

  requests.get("tts.second").resolve({
    engine_id: "tts.second",
    supported_languages: ["en-GB"],
    default_language: "en-GB",
  });
  await second;
  requests.get("tts.first").resolve({
    engine_id: "tts.first",
    supported_languages: ["en-US"],
    default_language: "en-US",
  });
  await first;

  assert.equal(panel._engineInfo.engine_id, "tts.second");
  assert.deepEqual(
    panel.shadowRoot.getElementById("language").options.map((item) => item.value),
    ["en-GB"],
  );
});

test("late language metadata cannot overwrite newer voices", async () => {
  const panel = panelWith([
    "override-engine", "override-language", "override-voice", "set-override",
    "override-error", "override-success",
  ]);
  panel.shadowRoot.getElementById("override-engine").value = "tts.adaptive";
  const language = panel.shadowRoot.getElementById("override-language");
  const requests = new Map();
  panel._hass = {
    callWS({ language: requestedLanguage }) {
      const request = deferred();
      requests.set(requestedLanguage, request);
      return request.promise;
    },
  };

  language.value = "en-US";
  const first = panel._overrideLanguageChanged();
  language.value = "en-GB";
  const second = panel._overrideLanguageChanged();

  requests.get("en-GB").resolve({
    voices_enumerated: true,
    voices: [{ voice_id: "british", name: "British" }],
  });
  await second;
  requests.get("en-US").resolve({
    voices_enumerated: true,
    voices: [{ voice_id: "american", name: "American" }],
  });
  await first;

  assert.equal(panel._overrideEngineInfoLanguage, "en-GB");
  assert.deepEqual(
    panel.shadowRoot.getElementById("override-voice").options.map((item) => item.value),
    ["british"],
  );
});

test("provider option controls preserve known value types", () => {
  const panel = panelWith(["options"]);
  panel._engineInfo = {
    supported_options: ["voice", "rate", "enabled", "metadata", "style"],
    default_options: {
      rate: 1.25,
      enabled: true,
      metadata: { emphasis: 2 },
      style: "warm",
    },
  };

  panel._renderOptionInputs();
  const inputs = panel.shadowRoot.querySelectorAll("[data-option]");
  const byName = Object.fromEntries(inputs.map((item) => [item.dataset.option, item]));

  assert.equal(panel._readOptionInput(byName.rate), 1.25);
  assert.equal(panel._readOptionInput(byName.enabled), true);
  assert.deepEqual(panel._readOptionInput(byName.metadata), { emphasis: 2 });
  assert.equal(panel._readOptionInput(byName.style), "warm");
  assert.equal(byName.rate.type, "number");
  assert.equal(byName.enabled.tagName, "SELECT");
  assert.equal(byName.metadata.tagName, "TEXTAREA");
});

test("non-enumerable providers get a free-text voice control", () => {
  const panel = panelWith(["voice"]);
  const voice = panel._replaceVoiceControl("voice", [], false, true);
  assert.equal(voice.tagName, "INPUT");
  assert.equal(voice.type, "text");
});
