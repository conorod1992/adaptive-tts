import "./adaptive-tts-panel.js";

class AdaptiveTtsRootPanel extends HTMLElement {
  set hass(value) {
    this._hass = value;
    const existing = this.shadowRoot?.querySelector("adaptive-tts-panel");
    if (existing) existing.hass = value;
    if (this.isConnected && !this._loaded && !this._loading) void this._load();
    for (const selector of this.shadowRoot?.querySelectorAll("ha-selector") || []) {
      selector.hass = value;
    }
  }

  connectedCallback() {
    if (!this.shadowRoot) this._renderShell();
    const existing = this.shadowRoot.querySelector("adaptive-tts-panel");
    if (existing && this._hass) existing.hass = this._hass;
    if (this._hass && !this._loaded && !this._loading) void this._load();
  }

  _renderShell() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; color: var(--primary-text-color); }
        .routing-page { max-width: 880px; margin: 0 auto; padding: 24px 24px 0; }
        ha-card { padding: 24px; }
        h2 { margin: 0 0 8px; font-size: 20px; font-weight: 500; }
        h3 { margin: 0; font-size: 17px; font-weight: 500; }
        p { line-height: 1.45; }
        .intro, .help { color: var(--secondary-text-color); }
        .intro { margin: 0 0 18px; }
        .help { font-size: 13px; margin: 6px 0 0; }
        .toolbar { display: grid; grid-template-columns: minmax(220px, 1fr) auto; gap: 16px; align-items: end; }
        label.field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--secondary-text-color); }
        select, input[type="text"] {
          box-sizing: border-box; width: 100%; padding: 10px 12px;
          color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 4px; font: inherit;
        }
        button {
          border: 0; border-radius: 4px; padding: 10px 16px; cursor: pointer;
          color: var(--text-primary-color); background: var(--primary-color); font: inherit;
        }
        button.secondary {
          color: var(--primary-text-color); background: transparent;
          border: 1px solid var(--divider-color);
        }
        button.danger { color: var(--error-color); }
        button.icon { padding: 7px 10px; min-width: 40px; }
        button[disabled] { opacity: .5; cursor: default; }
        .rules { display: grid; gap: 14px; margin-top: 18px; }
        .rule {
          border: 1px solid var(--divider-color); border-radius: 8px; padding: 16px;
          display: grid; gap: 16px; background: var(--card-background-color);
        }
        .rule.disabled { opacity: .7; }
        .rule-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .priority { color: var(--secondary-text-color); font-size: 13px; min-width: 74px; }
        .rule-title { flex: 1; min-width: 180px; }
        .rule-actions { display: flex; gap: 6px; }
        .enabled { display: flex; gap: 8px; align-items: center; font-size: 13px; }
        .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
        .conditions { border-top: 1px solid var(--divider-color); padding-top: 14px; }
        .conditions-title { font-size: 14px; font-weight: 500; margin-bottom: 4px; }
        .empty {
          margin-top: 18px; padding: 18px; border: 1px dashed var(--divider-color);
          border-radius: 8px; color: var(--secondary-text-color); text-align: center;
        }
        .actions { margin-top: 18px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .status { font-size: 13px; }
        .error { color: var(--error-color); white-space: pre-wrap; }
        .success { color: var(--success-color, var(--primary-color)); }
        .precedence {
          margin: 16px 0 0; padding: 12px 14px; border-radius: 6px;
          background: var(--secondary-background-color); font-size: 13px;
        }
        @media (max-width: 700px) {
          .routing-page { padding: 12px 12px 0; }
          ha-card { padding: 18px; }
          .toolbar, .grid { grid-template-columns: 1fr; }
          .rule-actions { width: 100%; }
        }
      </style>
      <div class="routing-page">
        <ha-card>
          <h2>Conditional Voice Routing</h2>
          <p class="intro">Automatically choose a voice when Home Assistant conditions are true. Rules are checked from top to bottom and the <strong>first matching enabled rule</strong> is used.</p>
          <div class="toolbar">
            <label class="field">Adaptive TTS entity
              <select id="routing-engine"></select>
              <span class="help">Rules belong to the selected Adaptive TTS entity and use voices from its wrapped provider.</span>
            </label>
            <button id="add-rule" class="secondary">Add rule</button>
          </div>
          <div class="precedence"><strong>Priority:</strong> a manual next-response or continuous voice override always wins over Conditional Voice Routing. When the manual override ends, matching rules take effect again automatically.</div>
          <div id="rules" class="rules"></div>
          <div class="actions">
            <button id="save-rules">Save routing rules</button>
            <span id="routing-status" class="status" role="status"></span>
          </div>
        </ha-card>
      </div>
      <adaptive-tts-panel></adaptive-tts-panel>`;

    this.shadowRoot.getElementById("routing-engine").addEventListener("change", () => void this._engineChanged());
    this.shadowRoot.getElementById("add-rule").addEventListener("click", () => void this._addRule());
    this.shadowRoot.getElementById("save-rules").addEventListener("click", () => void this._save());
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    this._setStatus("Loading…");
    try {
      this._info = await this._hass.callWS({ type: "adaptive_tts/info" });
      const engines = this._info.engines.filter((item) => item.is_adaptive);
      const select = this.shadowRoot.getElementById("routing-engine");
      select.replaceChildren();
      for (const engine of engines) {
        const option = document.createElement("option");
        option.value = engine.engine_id;
        option.textContent = `${engine.name}${engine.available === false ? " — unavailable" : ""}`;
        select.append(option);
      }
      const enabled = engines.length > 0;
      select.disabled = !enabled;
      this.shadowRoot.getElementById("add-rule").disabled = !enabled;
      this.shadowRoot.getElementById("save-rules").disabled = !enabled;
      if (!enabled) {
        this._rules = [];
        this._renderRules();
        this._setStatus("Create an Adaptive TTS entity before adding routing rules.", true);
        return;
      }
      const available = engines.find((item) => item.available !== false);
      if (available) select.value = available.engine_id;
      await this._engineChanged();
      this._loaded = true;
    } catch (err) {
      this._setStatus(this._errorText(err), true);
    } finally {
      this._loading = false;
    }
  }

  async _engineChanged() {
    const entityId = this.shadowRoot.getElementById("routing-engine").value;
    if (!entityId) return;
    this._setStatus("Loading rules…");
    try {
      const [rules, metadata] = await Promise.all([
        this._hass.callWS({ type: "adaptive_tts/routing_get", entity_id: entityId }),
        this._hass.callWS({ type: "adaptive_tts/engine", engine_id: entityId }),
      ]);
      this._rules = (rules.rules || []).map((rule) => ({ ...rule, conditions: structuredClone(rule.conditions || []) }));
      this._engineMetadata = metadata;
      this._dirty = false;
      await this._renderRules();
      this._setStatus("Rules loaded.");
    } catch (err) {
      this._setStatus(this._errorText(err), true);
    }
  }

  async _addRule() {
    if (!this._engineMetadata) return;
    const language = this._engineMetadata.default_language || this._engineMetadata.supported_languages?.[0] || "";
    const voices = await this._voicesFor(language);
    this._rules.push({
      id: globalThis.crypto?.randomUUID?.() || `rule-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: `Routing rule ${this._rules.length + 1}`,
      enabled: true,
      conditions: [],
      language,
      voice: voices[0]?.voice_id || "",
    });
    this._dirty = true;
    await this._renderRules();
    this._setStatus("New rule added. Add at least one condition, choose a voice, then save.");
  }

  async _voicesFor(language) {
    if (!language) return [];
    const entityId = this.shadowRoot.getElementById("routing-engine").value;
    const info = await this._hass.callWS({ type: "adaptive_tts/engine", engine_id: entityId, language });
    return info.voices || [];
  }

  async _renderRules() {
    const container = this.shadowRoot.getElementById("rules");
    container.replaceChildren();
    if (!this._rules?.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No routing rules yet. Add a rule to choose a voice from Home Assistant conditions.";
      container.append(empty);
      return;
    }

    for (let index = 0; index < this._rules.length; index += 1) {
      const rule = this._rules[index];
      const card = document.createElement("div");
      card.className = `rule${rule.enabled === false ? " disabled" : ""}`;
      card.innerHTML = `
        <div class="rule-head">
          <span class="priority">Priority ${index + 1}</span>
          <label class="enabled"><input class="rule-enabled" type="checkbox" ${rule.enabled === false ? "" : "checked"}> Enabled</label>
          <label class="field rule-title">Rule name<input class="rule-name" type="text" maxlength="100"></label>
          <div class="rule-actions">
            <button class="secondary icon move-up" title="Move rule up" ${index === 0 ? "disabled" : ""}>↑</button>
            <button class="secondary icon move-down" title="Move rule down" ${index === this._rules.length - 1 ? "disabled" : ""}>↓</button>
            <button class="secondary danger delete-rule">Delete</button>
          </div>
        </div>
        <div class="grid">
          <label class="field">Language<select class="rule-language"></select><span class="help">The language used when this rule selects its voice.</span></label>
          <label class="field">Voice<select class="rule-voice"></select><span class="help">Applied only when this is the first enabled rule whose conditions match.</span></label>
        </div>
        <div class="conditions">
          <div class="conditions-title">Conditions</div>
          <p class="help">Use Home Assistant's native condition editor. You can add multiple conditions and AND / OR / NOT building blocks. All top-level conditions must be true.</p>
          <div class="condition-host"></div>
        </div>`;

      card.querySelector(".rule-name").value = rule.name || "";
      const enabled = card.querySelector(".rule-enabled");
      enabled.addEventListener("change", () => { rule.enabled = enabled.checked; this._dirty = true; card.classList.toggle("disabled", !enabled.checked); this._setStatus("Unsaved changes."); });
      const name = card.querySelector(".rule-name");
      name.addEventListener("input", () => { rule.name = name.value; this._dirty = true; this._setStatus("Unsaved changes."); });
      card.querySelector(".move-up").addEventListener("click", () => void this._move(index, -1));
      card.querySelector(".move-down").addEventListener("click", () => void this._move(index, 1));
      card.querySelector(".delete-rule").addEventListener("click", () => void this._delete(index));

      const language = card.querySelector(".rule-language");
      for (const item of this._engineMetadata.supported_languages || []) {
        const option = document.createElement("option");
        option.value = item;
        option.textContent = item;
        language.append(option);
      }
      language.value = rule.language || this._engineMetadata.default_language || language.options[0]?.value || "";
      rule.language = language.value;

      const voice = card.querySelector(".rule-voice");
      await this._populateVoices(voice, language.value, rule.voice);
      rule.voice = voice.value;
      language.addEventListener("change", async () => {
        rule.language = language.value;
        await this._populateVoices(voice, language.value, null);
        rule.voice = voice.value;
        this._dirty = true;
        this._setStatus("Unsaved changes.");
      });
      voice.addEventListener("change", () => { rule.voice = voice.value; this._dirty = true; this._setStatus("Unsaved changes."); });

      const selector = document.createElement("ha-selector");
      selector.hass = this._hass;
      selector.selector = { condition: {} };
      selector.value = rule.conditions || [];
      selector.addEventListener("value-changed", (event) => {
        rule.conditions = event.detail.value || [];
        this._dirty = true;
        this._setStatus("Unsaved changes.");
      });
      card.querySelector(".condition-host").append(selector);
      container.append(card);
    }
  }

  async _populateVoices(select, language, selected) {
    select.replaceChildren();
    try {
      const voices = await this._voicesFor(language);
      for (const item of voices) {
        const option = document.createElement("option");
        option.value = item.voice_id;
        option.textContent = item.name || item.voice_id;
        select.append(option);
      }
      if (selected && [...select.options].some((option) => option.value === selected)) select.value = selected;
      select.disabled = voices.length === 0;
      if (!voices.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No voices reported for this language";
        select.append(option);
      }
    } catch (err) {
      select.disabled = true;
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Could not load voices";
      select.append(option);
    }
  }

  async _move(index, delta) {
    const target = index + delta;
    if (target < 0 || target >= this._rules.length) return;
    [this._rules[index], this._rules[target]] = [this._rules[target], this._rules[index]];
    this._dirty = true;
    await this._renderRules();
    this._setStatus("Priority changed. Save to apply the new order.");
  }

  async _delete(index) {
    this._rules.splice(index, 1);
    this._dirty = true;
    await this._renderRules();
    this._setStatus("Rule removed. Save to apply this change.");
  }

  _validateBeforeSave() {
    for (let index = 0; index < this._rules.length; index += 1) {
      const rule = this._rules[index];
      if (!rule.name?.trim()) throw new Error(`Rule ${index + 1} needs a name.`);
      if (!rule.conditions?.length) throw new Error(`${rule.name}: add at least one condition.`);
      if (!rule.language) throw new Error(`${rule.name}: select a language.`);
      if (!rule.voice) throw new Error(`${rule.name}: select a voice.`);
    }
  }

  async _save() {
    const entityId = this.shadowRoot.getElementById("routing-engine").value;
    if (!entityId) return;
    const button = this.shadowRoot.getElementById("save-rules");
    try {
      this._validateBeforeSave();
      button.disabled = true;
      this._setStatus("Validating conditions and saving…");
      const result = await this._hass.callWS({
        type: "adaptive_tts/routing_save",
        entity_id: entityId,
        rules: this._rules.map((rule) => ({
          id: rule.id,
          name: rule.name.trim(),
          enabled: rule.enabled !== false,
          conditions: rule.conditions,
          language: rule.language,
          voice: rule.voice,
        })),
      });
      this._rules = result.rules || [];
      this._dirty = false;
      this._setStatus("Routing rules saved. The Adaptive TTS entity is reloading with the new policy.", false, true);
    } catch (err) {
      this._setStatus(this._errorText(err), true);
    } finally {
      button.disabled = false;
    }
  }

  _setStatus(text, error = false, success = false) {
    const status = this.shadowRoot?.getElementById("routing-status");
    if (!status) return;
    status.textContent = text || "";
    status.className = `status${error ? " error" : success ? " success" : ""}`;
  }

  _errorText(err) {
    return err?.message || err?.body?.message || String(err || "Unknown error");
  }
}

if (!customElements.get("adaptive-tts-root-panel")) {
  customElements.define("adaptive-tts-root-panel", AdaptiveTtsRootPanel);
}
