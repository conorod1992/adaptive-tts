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
        :host {
          display: block;
          color: var(--primary-text-color);
          --routing-surface: color-mix(in srgb, var(--card-background-color) 94%, var(--primary-color) 6%);
          --routing-border: color-mix(in srgb, var(--divider-color) 72%, var(--primary-color) 28%);
          --routing-accent-soft: color-mix(in srgb, var(--primary-color) 10%, transparent);
        }
        .routing-page { max-width: 1040px; margin: 0 auto; padding: 24px 24px 0; }
        ha-card { overflow: hidden; }
        .routing-shell { padding: 28px; }
        .page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 22px; }
        .eyebrow {
          margin-bottom: 5px; color: var(--primary-color); font-size: 11px;
          font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
        }
        h2 { margin: 0; font-size: 24px; line-height: 1.25; font-weight: 600; }
        h3 { margin: 0; font-size: 17px; font-weight: 600; }
        p { line-height: 1.5; }
        .intro, .help { color: var(--secondary-text-color); }
        .intro { max-width: 760px; margin: 8px 0 0; }
        .help { font-size: 13px; line-height: 1.45; margin: 6px 0 0; }
        .toolbar {
          display: grid; grid-template-columns: minmax(260px, 1fr) auto; gap: 16px;
          align-items: end; padding: 18px; border: 1px solid var(--divider-color);
          border-radius: 12px; background: var(--secondary-background-color);
        }
        label.field { display: flex; flex-direction: column; gap: 7px; font-size: 13px; color: var(--secondary-text-color); }
        .field-label { color: var(--primary-text-color); font-weight: 500; }
        select, input[type="text"] {
          box-sizing: border-box; width: 100%; min-height: 42px; padding: 10px 12px;
          color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 8px; font: inherit;
          transition: border-color .15s ease, box-shadow .15s ease;
        }
        select:focus, input[type="text"]:focus {
          outline: none; border-color: var(--primary-color);
          box-shadow: 0 0 0 2px var(--routing-accent-soft);
        }
        button {
          min-height: 40px; border: 0; border-radius: 8px; padding: 10px 16px;
          cursor: pointer; color: var(--text-primary-color); background: var(--primary-color);
          font: inherit; font-weight: 500; transition: opacity .15s ease, background .15s ease;
        }
        button.secondary {
          color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color);
        }
        button.secondary:hover:not([disabled]) { background: var(--secondary-background-color); }
        button.danger { color: var(--error-color); }
        button.icon { min-width: 40px; padding: 8px 11px; font-size: 16px; }
        button[disabled] { opacity: .45; cursor: default; }
        #add-rule { white-space: nowrap; }
        .precedence {
          display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: start;
          margin: 14px 0 0; padding: 14px 16px; border-radius: 10px;
          background: var(--routing-accent-soft); border: 1px solid var(--routing-border); font-size: 13px;
        }
        .precedence-badge {
          padding: 3px 8px; border-radius: 999px; color: var(--primary-color);
          background: var(--card-background-color); font-size: 11px; font-weight: 700;
          letter-spacing: .04em; text-transform: uppercase;
        }
        .rules { display: grid; gap: 18px; margin-top: 22px; }
        .rule {
          overflow: hidden; border: 1px solid var(--divider-color); border-radius: 14px;
          background: var(--card-background-color); box-shadow: 0 1px 2px rgba(0, 0, 0, .08);
          transition: opacity .15s ease, border-color .15s ease;
        }
        .rule.disabled { opacity: .62; }
        .rule-head {
          display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 18px;
          align-items: start; padding: 18px 20px; background: var(--routing-surface);
          border-bottom: 1px solid var(--divider-color);
        }
        .rule-identity { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 14px; align-items: start; }
        .priority {
          display: inline-flex; align-items: center; justify-content: center; min-width: 74px;
          height: 28px; padding: 0 10px; border-radius: 999px; color: var(--primary-color);
          background: var(--routing-accent-soft); font-size: 12px; font-weight: 700;
        }
        .rule-title { min-width: 0; }
        .rule-title input { margin-top: 2px; font-size: 15px; font-weight: 500; }
        .rule-head-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-end; }
        .enabled {
          display: inline-flex; align-items: center; gap: 8px; min-height: 40px; padding: 0 11px;
          border: 1px solid var(--divider-color); border-radius: 8px; background: var(--card-background-color);
          font-size: 13px; font-weight: 500;
        }
        .enabled input { width: 16px; height: 16px; accent-color: var(--primary-color); }
        .rule-actions { display: flex; gap: 6px; }
        .rule-body { display: grid; gap: 20px; padding: 20px; }
        .voice-section {
          display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px;
          padding: 16px; border-radius: 10px; background: var(--secondary-background-color);
        }
        .section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 5px; }
        .conditions {
          padding: 17px; border: 1px solid var(--divider-color); border-radius: 10px;
          background: var(--card-background-color);
        }
        .conditions-title { font-size: 15px; font-weight: 600; }
        .condition-host {
          margin-top: 14px; padding: 12px; border-radius: 8px;
          background: var(--secondary-background-color);
        }
        .empty {
          margin-top: 22px; padding: 30px 22px; border: 1px dashed var(--divider-color);
          border-radius: 12px; color: var(--secondary-text-color); text-align: center;
          background: var(--secondary-background-color);
        }
        .actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .routing-test-actions {
          margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--divider-color);
        }
        .save-bar {
          display: flex; align-items: center; justify-content: space-between; gap: 14px;
          margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--divider-color);
        }
        .save-bar .actions { margin: 0; }
        .status { font-size: 13px; color: var(--secondary-text-color); }
        .error { color: var(--error-color); white-space: pre-wrap; }
        .success { color: var(--success-color, var(--primary-color)); }
        @media (max-width: 760px) {
          .routing-page { padding: 12px 12px 0; }
          .routing-shell { padding: 18px; }
          .page-head { display: block; }
          .toolbar, .voice-section, .rule-head { grid-template-columns: 1fr; }
          .rule-head-actions { justify-content: flex-start; }
          .rule-actions { flex-wrap: wrap; }
          .save-bar { align-items: flex-start; flex-direction: column; }
        }
        @media (max-width: 480px) {
          .rule-identity { grid-template-columns: 1fr; }
          .priority { justify-self: start; }
          .rule-head-actions { display: grid; grid-template-columns: 1fr; width: 100%; }
          .rule-actions { width: 100%; }
          .rule-actions button { flex: 1; }
        }
      </style>
      <div class="routing-page">
        <ha-card>
          <div class="routing-shell">
            <div class="page-head">
              <div>
                <div class="eyebrow">Adaptive TTS</div>
                <h2>Conditional Voice Routing</h2>
                <p class="intro">Build an ordered voice policy from Home Assistant conditions. Rules are evaluated from top to bottom and the <strong>first matching enabled rule</strong> is used.</p>
              </div>
            </div>
            <div class="toolbar">
              <label class="field"><span class="field-label">Adaptive TTS entity</span>
                <select id="routing-engine"></select>
                <span class="help">Rules are stored per Adaptive TTS entity and use voices exposed by its wrapped provider.</span>
              </label>
              <button id="add-rule" class="secondary">+ Add rule</button>
            </div>
            <div class="precedence">
              <span class="precedence-badge">Priority</span>
              <span>A manual next-response or continuous voice override always wins. When that override ends, matching routing rules take effect automatically.</span>
            </div>
            <div id="rules" class="rules"></div>
            <div class="save-bar">
              <div class="actions"><button id="save-rules">Save routing rules</button></div>
              <span id="routing-status" class="status" role="status"></span>
            </div>
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
      empty.innerHTML = "<strong>No routing rules yet.</strong><br>Add a rule to automatically choose a voice from Home Assistant conditions.";
      container.append(empty);
      return;
    }

    for (let index = 0; index < this._rules.length; index += 1) {
      const rule = this._rules[index];
      const card = document.createElement("div");
      card.className = `rule${rule.enabled === false ? " disabled" : ""}`;
      card.innerHTML = `
        <div class="rule-head">
          <div class="rule-identity">
            <span class="priority">Priority ${index + 1}</span>
            <label class="field rule-title"><span class="field-label">Rule name</span><input class="rule-name" type="text" maxlength="100"></label>
          </div>
          <div class="rule-head-actions">
            <label class="enabled"><input class="rule-enabled" type="checkbox" ${rule.enabled === false ? "" : "checked"}> Enabled</label>
            <div class="rule-actions">
              <button class="secondary icon move-up" title="Move rule up" aria-label="Move rule up" ${index === 0 ? "disabled" : ""}>↑</button>
              <button class="secondary icon move-down" title="Move rule down" aria-label="Move rule down" ${index === this._rules.length - 1 ? "disabled" : ""}>↓</button>
              <button class="secondary danger delete-rule">Delete</button>
            </div>
          </div>
        </div>
        <div class="rule-body">
          <div class="voice-section">
            <label class="field"><span class="field-label">Language</span><select class="rule-language"></select><span class="help">Language used when this rule wins.</span></label>
            <label class="field"><span class="field-label">Voice</span><select class="rule-voice"></select><span class="help">Voice applied when this is the highest-priority matching rule.</span></label>
          </div>
          <div class="conditions">
            <div class="section-heading"><div class="conditions-title">Conditions</div><span class="help">All top-level conditions must be true</span></div>
            <p class="help">Use Home Assistant's native condition editor. You can add multiple conditions and AND / OR / NOT building blocks.</p>
            <div class="condition-host"></div>
          </div>
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
