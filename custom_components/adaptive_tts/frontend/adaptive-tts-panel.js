class AdaptiveTtsPanel extends HTMLElement {
  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this._loaded) this._load();
  }

  connectedCallback() {
    if (!this.shadowRoot) this._render();
    if (this._hass && !this._loaded) this._load();
  }

  _render() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 24px; color: var(--primary-text-color); }
        ha-card { max-width: 880px; margin: 0 auto; padding: 24px; }
        h1 { margin: 0 0 8px; font-size: 24px; font-weight: 500; }
        .intro { color: var(--secondary-text-color); margin: 0 0 24px; }
        .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
        label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--secondary-text-color); }
        select, input, textarea {
          box-sizing: border-box; width: 100%; padding: 10px 12px;
          color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 4px; font: inherit;
        }
        textarea { min-height: 120px; resize: vertical; }
        .full { grid-column: 1 / -1; }
        .actions { margin-top: 18px; display: flex; align-items: center; gap: 16px; }
        button {
          border: 0; border-radius: 4px; padding: 10px 18px; cursor: pointer;
          color: var(--text-primary-color); background: var(--primary-color); font: inherit;
        }
        button[disabled] { opacity: .55; cursor: default; }
        #error { color: var(--error-color); margin-top: 16px; white-space: pre-wrap; }
        #result { display: none; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--divider-color); }
        audio { width: 100%; margin: 12px 0 16px; }
        dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; margin: 0; }
        dt { color: var(--secondary-text-color); }
        dd { margin: 0; overflow-wrap: anywhere; }
        code { font-family: var(--code-font-family, monospace); }
        .hint { color: var(--secondary-text-color); font-size: 13px; }
        @media (max-width: 700px) { :host { padding: 12px; } ha-card { padding: 18px; } .grid { grid-template-columns: 1fr; } }
      </style>
      <ha-card>
        <h1>TTS Test</h1>
        <p class="intro">Compare a source TTS entity with its Adaptive TTS wrapper without changing an Assist pipeline.</p>
        <div class="grid">
          <label>Assist pipeline
            <select id="pipeline"><option value="">Direct TTS selection</option></select>
          </label>
          <label>TTS entity
            <select id="engine"></select>
          </label>
          <label>Language
            <select id="language"></select>
          </label>
          <label id="voice-label">Voice
            <select id="voice"></select>
          </label>
          <div id="options" class="full grid"></div>
          <label class="full">Test text
            <textarea id="message">This is an Adaptive TTS test.</textarea>
          </label>
        </div>
        <div class="actions">
          <button id="generate">Generate</button>
          <span class="hint">Preview audio is temporary and kept in Home Assistant's bounded in-memory TTS cache.</span>
        </div>
        <div id="error" role="alert"></div>
        <section id="result">
          <strong>Generated preview</strong>
          <audio id="audio" controls></audio>
          <dl>
            <dt>Requested entity</dt><dd><code id="used-engine"></code></dd>
            <dt>Underlying entity</dt><dd><code id="used-underlying"></code></dd>
            <dt>Language</dt><dd><code id="used-language"></code></dd>
            <dt>Options</dt><dd><code id="used-options"></code></dd>
            <dt>Quiet mode active</dt><dd id="used-quiet"></dd>
          </dl>
        </section>
      </ha-card>`;

    this.shadowRoot.getElementById("pipeline").addEventListener("change", () => this._pipelineChanged());
    this.shadowRoot.getElementById("engine").addEventListener("change", () => this._engineChanged());
    this.shadowRoot.getElementById("language").addEventListener("change", () => this._languageChanged());
    this.shadowRoot.getElementById("generate").addEventListener("click", () => this._generate());
  }

  async _load() {
    this._loaded = true;
    try {
      this._data = await this._hass.callWS({ type: "adaptive_tts/info" });
      const pipeline = this.shadowRoot.getElementById("pipeline");
      for (const item of this._data.pipelines) this._appendOption(pipeline, item.id, item.name);
      const engine = this.shadowRoot.getElementById("engine");
      for (const item of this._data.engines) {
        const suffix = item.is_adaptive ? " (Adaptive)" : " (Source)";
        this._appendOption(engine, item.engine_id, `${item.name}${suffix}`);
      }
      if (!this._data.engines.length) throw new Error("No TTS entities are currently available.");
      await this._engineChanged();
    } catch (err) {
      this._showError(err);
    }
  }

  _appendOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value ?? "";
    option.textContent = label;
    select.append(option);
  }

  async _pipelineChanged() {
    const pipelineId = this.shadowRoot.getElementById("pipeline").value;
    const pipeline = this._data.pipelines.find((item) => item.id === pipelineId);
    if (!pipeline) return;
    if (!pipeline.tts_engine || !this._data.engines.some((item) => item.engine_id === pipeline.tts_engine)) {
      this._showError("The selected pipeline does not have an available TTS entity.");
      return;
    }
    this.shadowRoot.getElementById("engine").value = pipeline.tts_engine;
    await this._engineChanged(pipeline.tts_language, pipeline.tts_voice);
  }

  async _engineChanged(preferredLanguage, preferredVoice) {
    this._clearError();
    const engineId = this.shadowRoot.getElementById("engine").value;
    try {
      this._engineInfo = await this._hass.callWS({ type: "adaptive_tts/engine", engine_id: engineId });
      const language = this.shadowRoot.getElementById("language");
      language.replaceChildren();
      for (const item of this._engineInfo.supported_languages) this._appendOption(language, item, item);
      const requested = preferredLanguage || this._engineInfo.default_language;
      if (requested && this._engineInfo.supported_languages.includes(requested)) language.value = requested;
      await this._languageChanged(preferredVoice);
    } catch (err) {
      this._showError(err);
    }
  }

  async _languageChanged(preferredVoice) {
    const engineId = this.shadowRoot.getElementById("engine").value;
    const language = this.shadowRoot.getElementById("language").value;
    try {
      this._engineInfo = await this._hass.callWS({ type: "adaptive_tts/engine", engine_id: engineId, language });
      const voice = this.shadowRoot.getElementById("voice");
      voice.replaceChildren();
      this._appendOption(voice, "", "Provider default");
      for (const item of this._engineInfo.voices) this._appendOption(voice, item.voice_id, item.name);
      const defaultVoice = preferredVoice || this._engineInfo.default_options.voice;
      if (defaultVoice && [...voice.options].some((item) => item.value === defaultVoice)) voice.value = defaultVoice;
      this.shadowRoot.getElementById("voice-label").style.display =
        this._engineInfo.supported_options.includes("voice") ? "flex" : "none";
      this._renderOptionInputs();
    } catch (err) {
      this._showError(err);
    }
  }

  _renderOptionInputs() {
    const container = this.shadowRoot.getElementById("options");
    container.replaceChildren();
    for (const name of this._engineInfo.supported_options.filter((item) => item !== "voice")) {
      const label = document.createElement("label");
      label.textContent = name;
      const input = document.createElement("input");
      input.dataset.option = name;
      input.value = this._engineInfo.default_options[name] ?? "";
      input.placeholder = "Provider default";
      label.append(input);
      container.append(label);
    }
  }

  async _generate() {
    this._clearError();
    const button = this.shadowRoot.getElementById("generate");
    button.disabled = true;
    const options = {};
    if (this._engineInfo.supported_options.includes("voice")) {
      const voice = this.shadowRoot.getElementById("voice").value;
      if (voice) options.voice = voice;
    }
    for (const input of this.shadowRoot.querySelectorAll("[data-option]")) {
      if (input.value !== "") options[input.dataset.option] = input.value;
    }
    try {
      const result = await this._hass.callWS({
        type: "adaptive_tts/generate",
        engine_id: this.shadowRoot.getElementById("engine").value,
        language: this.shadowRoot.getElementById("language").value,
        options,
        message: this.shadowRoot.getElementById("message").value,
      });
      const audio = this.shadowRoot.getElementById("audio");
      audio.src = result.url;
      audio.load();
      this.shadowRoot.getElementById("used-engine").textContent = result.engine_id;
      this.shadowRoot.getElementById("used-underlying").textContent = result.underlying_entity_id;
      this.shadowRoot.getElementById("used-language").textContent = result.language;
      this.shadowRoot.getElementById("used-options").textContent = JSON.stringify(result.options);
      this.shadowRoot.getElementById("used-quiet").textContent = result.quiet_mode_active ? "Yes" : "No";
      this.shadowRoot.getElementById("result").style.display = "block";
    } catch (err) {
      this._showError(err);
    } finally {
      button.disabled = false;
    }
  }

  _clearError() { this.shadowRoot.getElementById("error").textContent = ""; }
  _showError(err) { this.shadowRoot.getElementById("error").textContent = err?.message || String(err); }
}

customElements.define("adaptive-tts-panel", AdaptiveTtsPanel);
