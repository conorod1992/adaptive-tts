class AdaptiveTtsPanel extends HTMLElement {
  set hass(value) {
    const previousAvailability = this._selectedAvailability;
    this._hass = value;
    if (this.isConnected && !this._loaded && !this._loading) {
      this._load();
      return;
    }
    if (this.isConnected && this._loaded && !this._loading) {
      const currentAvailability = this._selectedAvailabilitySnapshot(value);
      this._selectedAvailability = currentAvailability;
      if (previousAvailability) {
        void this._handleAvailabilityTransitions(previousAvailability, currentAvailability);
      }
    }
  }

  connectedCallback() {
    if (!this.shadowRoot) this._render();
    if (this._hass && !this._loaded && !this._loading) this._load();
  }

  _render() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 24px; color: var(--primary-text-color); }
        .page { max-width: 880px; margin: 0 auto; display: grid; gap: 20px; }
        ha-card { padding: 24px; }
        h1 { margin: 0 0 8px; font-size: 24px; font-weight: 500; }
        h2 { margin: 0 0 8px; font-size: 20px; font-weight: 500; }
        .intro { color: var(--secondary-text-color); margin: 0 0 24px; }
        .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
        label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--secondary-text-color); }
        select, input, textarea {
          box-sizing: border-box; width: 100%; padding: 10px 12px;
          color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 4px; font: inherit;
        }
        textarea { min-height: 120px; resize: vertical; }
        .option-json { min-height: 72px; }
        .full { grid-column: 1 / -1; }
        .actions { margin-top: 18px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        button {
          border: 0; border-radius: 4px; padding: 10px 18px; cursor: pointer;
          color: var(--text-primary-color); background: var(--primary-color); font: inherit;
        }
        button.secondary {
          color: var(--primary-text-color); background: transparent;
          border: 1px solid var(--divider-color);
        }
        button[disabled] { opacity: .55; cursor: default; }
        .error { color: var(--error-color); margin-top: 16px; white-space: pre-wrap; }
        .success { color: var(--success-color, var(--primary-color)); margin-top: 16px; white-space: pre-wrap; }
        #result { display: none; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--divider-color); }
        audio { width: 100%; margin: 12px 0 16px; }
        dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; margin: 0; }
        dt { color: var(--secondary-text-color); }
        dd { margin: 0; overflow-wrap: anywhere; }
        code { font-family: var(--code-font-family, monospace); }
        .hint { color: var(--secondary-text-color); font-size: 13px; }
        @media (max-width: 700px) {
          :host { padding: 12px; }
          ha-card { padding: 18px; }
          .grid { grid-template-columns: 1fr; }
        }
      </style>
      <div class="page">
        <ha-card>
          <h1>Adaptive TTS</h1>
          <p class="intro">Control temporary or persistent voice overrides, or test TTS output without changing an Assist pipeline.</p>

          <h2>Voice override</h2>
          <p class="intro">Choose an Adaptive TTS entity, then select the language and one of the voices exposed by its wrapped provider.</p>
          <div class="grid">
            <label>Adaptive TTS entity
              <select id="override-engine"></select>
            </label>
            <label>Duration
              <select id="override-duration">
                <option value="next_request">Next TTS request</option>
                <option value="until_changed">Until changed again</option>
              </select>
            </label>
            <label>Language
              <select id="override-language"></select>
            </label>
            <label>Voice
              <select id="override-voice"></select>
            </label>
          </div>
          <div class="actions">
            <button id="set-override">Set voice override</button>
            <button id="clear-override" class="secondary">Clear override</button>
            <span class="hint">Persistent overrides survive Home Assistant restarts. Next-request overrides are consumed by the next synthesis request.</span>
          </div>
          <div id="override-error" class="error" role="alert"></div>
          <div id="override-success" class="success" role="status"></div>
        </ha-card>

        <ha-card>
          <h2>TTS Test</h2>
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
          <div id="error" class="error" role="alert"></div>
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
        </ha-card>
      </div>`;

    this.shadowRoot.getElementById("override-engine").addEventListener("change", () => this._overrideEngineChanged());
    this.shadowRoot.getElementById("override-language").addEventListener("change", () => this._overrideLanguageChanged());
    this.shadowRoot.getElementById("set-override").addEventListener("click", () => this._setOverride());
    this.shadowRoot.getElementById("clear-override").addEventListener("click", () => this._clearOverride());
    this.shadowRoot.getElementById("pipeline").addEventListener("change", () => this._pipelineChanged());
    this.shadowRoot.getElementById("engine").addEventListener("change", () => this._engineChanged());
    this.shadowRoot.getElementById("language").addEventListener("change", () => this._languageChanged());
    this.shadowRoot.getElementById("generate").addEventListener("click", () => this._generate());
    this.shadowRoot.getElementById("message").addEventListener("input", () => this._invalidateGeneration());
    this.shadowRoot.getElementById("audio").addEventListener("error", () => this._audioFailed());
  }

  async _load() {
    if (this._loaded || this._loading || !this._hass || !this.shadowRoot) return;
    this._loading = true;
    this._resetLoadControls();
    try {
      const data = await this._hass.callWS({ type: "adaptive_tts/info" });
      this._data = data;
      const pipeline = this.shadowRoot.getElementById("pipeline");
      for (const item of data.pipelines) this._appendOption(pipeline, item.id, item.name);

      const engine = this.shadowRoot.getElementById("engine");
      for (const item of data.engines) {
        const suffix = item.is_adaptive ? " (Adaptive)" : " (Source)";
        const availability = item.available === false ? " — unavailable" : "";
        this._appendOption(engine, item.engine_id, `${item.name}${suffix}${availability}`);
      }
      if (!data.engines.length) throw new Error("No TTS entities are configured.");
      const firstAvailableEngine = data.engines.find((item) => item.available !== false);
      if (firstAvailableEngine) engine.value = firstAvailableEngine.engine_id;

      const overrideEngine = this.shadowRoot.getElementById("override-engine");
      const adaptiveEngines = data.engines.filter((candidate) => candidate.is_adaptive);
      for (const item of adaptiveEngines) {
        const availability = item.available === false ? " — unavailable" : "";
        this._appendOption(overrideEngine, item.engine_id, `${item.name}${availability}`);
      }
      const hasAdaptive = overrideEngine.options.length > 0;
      this.shadowRoot.getElementById("set-override").disabled = !hasAdaptive;
      this.shadowRoot.getElementById("clear-override").disabled = !hasAdaptive;
      if (hasAdaptive) {
        const firstAvailableAdaptive = adaptiveEngines.find((item) => item.available !== false);
        if (firstAvailableAdaptive) overrideEngine.value = firstAvailableAdaptive.engine_id;
        await this._overrideEngineChanged();
      } else {
        this._showOverrideError("No Adaptive TTS entities are configured.");
      }

      await this._engineChanged();
      this._loaded = true;
      this._selectedAvailability = this._selectedAvailabilitySnapshot(this._hass);
    } catch (err) {
      this._loaded = false;
      this._showError(err);
      this._showOverrideError(err);
    } finally {
      this._loading = false;
    }
  }

  _resetLoadControls() {
    this._data = null;
    this._engineInfo = null;
    this._engineInfoLanguage = null;
    this._overrideEngineInfo = null;
    this._overrideEngineInfoLanguage = null;
    this._engineRequestId = (this._engineRequestId || 0) + 1;
    this._languageRequestId = (this._languageRequestId || 0) + 1;
    this._overrideEngineRequestId = (this._overrideEngineRequestId || 0) + 1;
    this._overrideLanguageRequestId = (this._overrideLanguageRequestId || 0) + 1;
    this._generationRequestId = (this._generationRequestId || 0) + 1;
    this._invalidateOverrideAction();

    const pipeline = this.shadowRoot.getElementById("pipeline");
    pipeline.replaceChildren();
    this._appendOption(pipeline, "", "Direct TTS selection");
    for (const id of ["engine", "language", "voice", "override-engine", "override-language", "override-voice"]) {
      this.shadowRoot.getElementById(id).replaceChildren();
    }
    this.shadowRoot.getElementById("options").replaceChildren();
    this.shadowRoot.getElementById("set-override").disabled = true;
    this.shadowRoot.getElementById("clear-override").disabled = true;
    this.shadowRoot.getElementById("generate").disabled = true;
    this._clearResult();
    this._clearError();
    this._clearOverrideMessages();
  }

  _appendOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value ?? "";
    option.textContent = label;
    select.append(option);
  }

  _requestIsCurrent(counterName, requestId, selectId, expectedValue) {
    return (
      this[counterName] === requestId &&
      this.shadowRoot.getElementById(selectId).value === expectedValue
    );
  }

  _generationFingerprint() {
    const voice = this.shadowRoot.getElementById("voice");
    const message = this.shadowRoot.getElementById("message");
    const options = [...this.shadowRoot.querySelectorAll("[data-option]")].map((input) => [
      input.dataset.option,
      input.dataset.optionType,
      input.value,
    ]);
    return JSON.stringify({
      engine: this.shadowRoot.getElementById("engine").value,
      language: this.shadowRoot.getElementById("language").value,
      voice: voice?.value ?? "",
      message: message?.value ?? "",
      options,
    });
  }

  _generationIsCurrent(requestId, fingerprint) {
    return (
      this._generationRequestId === requestId &&
      this._generationFingerprint() === fingerprint
    );
  }

  _invalidateGeneration() {
    this._generationRequestId = (this._generationRequestId || 0) + 1;
    this._clearResult();
  }

  _invalidateOverrideAction() {
    this._overrideActionRequestId = (this._overrideActionRequestId || 0) + 1;
  }

  _overrideActionIsCurrent(requestId, context) {
    if (this._overrideActionRequestId !== requestId) return false;
    if (this.shadowRoot.getElementById("override-engine").value !== context.entityId) return false;
    if (context.language !== undefined && this.shadowRoot.getElementById("override-language").value !== context.language) return false;
    if (context.voice !== undefined && this.shadowRoot.getElementById("override-voice").value.trim() !== context.voice) return false;
    if (context.duration !== undefined && this.shadowRoot.getElementById("override-duration").value !== context.duration) return false;
    return true;
  }

  _entityAvailability(hass, engineId) {
    if (!engineId || !hass?.states) return null;
    const state = hass.states[engineId];
    return Boolean(state && state.state !== "unavailable");
  }

  _selectedAvailabilitySnapshot(hass) {
    const engineId = this.shadowRoot?.getElementById("engine")?.value ?? "";
    const overrideEngineId = this.shadowRoot?.getElementById("override-engine")?.value ?? "";
    return {
      engineId,
      engineAvailable: this._entityAvailability(hass, engineId),
      overrideEngineId,
      overrideEngineAvailable: this._entityAvailability(hass, overrideEngineId),
    };
  }

  async _handleAvailabilityTransitions(previous, current) {
    const previewChanged =
      previous.engineId === current.engineId &&
      current.engineId &&
      previous.engineAvailable !== null &&
      current.engineAvailable !== null &&
      previous.engineAvailable !== current.engineAvailable;
    const overrideChanged =
      previous.overrideEngineId === current.overrideEngineId &&
      current.overrideEngineId &&
      previous.overrideEngineAvailable !== null &&
      current.overrideEngineAvailable !== null &&
      previous.overrideEngineAvailable !== current.overrideEngineAvailable;

    if (previewChanged) await this._engineChanged();
    if (overrideChanged) await this._overrideEngineChanged();
    this._selectedAvailability = this._selectedAvailabilitySnapshot(this._hass);
  }

  _engineAvailable(engineId, info) {
    if (!engineId) return false;
    const live = this._entityAvailability(this._hass, engineId);
    return live === null ? info?.available !== false : live;
  }

  _syncAvailabilityControls() {
    const engineId = this.shadowRoot.getElementById("engine").value;
    const language = this.shadowRoot.getElementById("language").value;
    this.shadowRoot.getElementById("generate").disabled = !(
      this._engineInfo &&
      this._engineInfoLanguage === language &&
      this._engineAvailable(engineId, this._engineInfo)
    );

    const overrideEngineId = this.shadowRoot.getElementById("override-engine").value;
    const overrideLanguage = this.shadowRoot.getElementById("override-language").value;
    const voice = this.shadowRoot.getElementById("override-voice");
    const hasVoiceChoice = voice.tagName !== "SELECT" || voice.options.length > 0;
    const actionPending = this._overrideActionPendingId != null;
    this.shadowRoot.getElementById("set-override").disabled = actionPending || !(
      this._overrideEngineInfo &&
      this._overrideEngineInfoLanguage === overrideLanguage &&
      this._engineAvailable(overrideEngineId, this._overrideEngineInfo) &&
      hasVoiceChoice
    );
    this.shadowRoot.getElementById("clear-override").disabled = actionPending || !overrideEngineId;
  }

  async _overrideEngineChanged() {
    this._clearOverrideMessages();
    this._invalidateOverrideAction();
    this._overrideEngineInfo = null;
    this._overrideEngineInfoLanguage = null;
    this._overrideLanguageRequestId = (this._overrideLanguageRequestId || 0) + 1;
    const requestId = (this._overrideEngineRequestId || 0) + 1;
    this._overrideEngineRequestId = requestId;
    const engineId = this.shadowRoot.getElementById("override-engine").value;
    const setButton = this.shadowRoot.getElementById("set-override");
    setButton.disabled = true;
    if (!engineId) {
      this._syncAvailabilityControls();
      return;
    }
    try {
      const info = await this._hass.callWS({ type: "adaptive_tts/engine", engine_id: engineId });
      if (!this._requestIsCurrent("_overrideEngineRequestId", requestId, "override-engine", engineId)) return;
      this._overrideEngineInfo = info;
      const language = this.shadowRoot.getElementById("override-language");
      language.replaceChildren();
      if (!this._engineAvailable(engineId, info)) {
        this._replaceVoiceControl("override-voice", [], true, false);
        this._showOverrideError(
          "The selected Adaptive TTS entity is currently unavailable. You can still clear an existing override.",
        );
        this._syncAvailabilityControls();
        return;
      }
      for (const item of info.supported_languages) this._appendOption(language, item, item);
      if (info.default_language && info.supported_languages.includes(info.default_language)) {
        language.value = info.default_language;
      }
      await this._overrideLanguageChanged();
    } catch (err) {
      if (this._requestIsCurrent("_overrideEngineRequestId", requestId, "override-engine", engineId)) {
        if (this._loading) throw err;
        this._showOverrideError(err);
        this._syncAvailabilityControls();
      }
    }
  }

  async _overrideLanguageChanged() {
    this._clearOverrideMessages();
    this._invalidateOverrideAction();
    this._overrideEngineInfo = null;
    this._overrideEngineInfoLanguage = null;
    const requestId = (this._overrideLanguageRequestId || 0) + 1;
    this._overrideLanguageRequestId = requestId;
    const engineId = this.shadowRoot.getElementById("override-engine").value;
    const language = this.shadowRoot.getElementById("override-language").value;
    const setButton = this.shadowRoot.getElementById("set-override");
    setButton.disabled = true;
    if (!engineId || !language) {
      this._syncAvailabilityControls();
      return;
    }
    try {
      const info = await this._hass.callWS({ type: "adaptive_tts/engine", engine_id: engineId, language });
      if (!this._requestIsCurrent("_overrideLanguageRequestId", requestId, "override-language", language)) return;
      if (this.shadowRoot.getElementById("override-engine").value !== engineId) return;
      this._overrideEngineInfo = info;
      if (!this._engineAvailable(engineId, info)) {
        this._replaceVoiceControl("override-voice", [], true, false);
        this._showOverrideError(
          "The selected Adaptive TTS entity is currently unavailable. You can still clear an existing override.",
        );
        this._syncAvailabilityControls();
        return;
      }
      this._overrideEngineInfoLanguage = language;
      const voice = this._replaceVoiceControl(
        "override-voice",
        info.voices,
        info.voices_enumerated,
        false,
      );
      if (info.voices_enumerated && voice.options.length === 0) {
        this._showOverrideError("The wrapped TTS provider exposes no selectable voices for this language.");
      }
      this._syncAvailabilityControls();
    } catch (err) {
      if (this._requestIsCurrent("_overrideLanguageRequestId", requestId, "override-language", language)) {
        if (this._loading) throw err;
        this._showOverrideError(err);
        this._syncAvailabilityControls();
      }
    }
  }

  _replaceVoiceControl(id, voices, voicesEnumerated, includeDefault) {
    const current = this.shadowRoot.getElementById(id);
    const control = document.createElement(voicesEnumerated ? "select" : "input");
    control.id = id;
    if (voicesEnumerated) {
      if (includeDefault) this._appendOption(control, "", "Provider default");
      for (const item of voices) this._appendOption(control, item.voice_id, item.name);
    } else {
      control.type = "text";
      control.placeholder = includeDefault ? "Provider default or voice ID" : "Provider voice ID";
    }
    control.addEventListener("input", () => this._invalidateGeneration());
    control.addEventListener("change", () => this._invalidateGeneration());
    current.replaceWith(control);
    return control;
  }

  async _setOverride() {
    this._clearOverrideMessages();
    const context = {
      entityId: this.shadowRoot.getElementById("override-engine").value,
      language: this.shadowRoot.getElementById("override-language").value,
      voice: this.shadowRoot.getElementById("override-voice").value.trim(),
      duration: this.shadowRoot.getElementById("override-duration").value,
    };
    const requestId = (this._overrideActionRequestId || 0) + 1;
    this._overrideActionRequestId = requestId;
    this._overrideActionPendingId = requestId;
    this._syncAvailabilityControls();
    try {
      if (!context.entityId || !context.language || !context.voice) {
        throw new Error("Choose an Adaptive TTS entity, language, and voice first.");
      }
      if (!this._engineAvailable(context.entityId, this._overrideEngineInfo)) {
        throw new Error("The selected Adaptive TTS entity is currently unavailable.");
      }
      if (!this._overrideEngineInfo || this._overrideEngineInfoLanguage !== context.language) {
        throw new Error("Voice details are still loading. Try again in a moment.");
      }
      await this._hass.callService("adaptive_tts", "set_voice_override", {
        entity_id: context.entityId,
        language: context.language,
        voice: context.voice,
        duration: context.duration,
      });
      if (!this._overrideActionIsCurrent(requestId, context)) return;
      const durationLabel = context.duration === "next_request" ? "the next TTS request" : "until changed again";
      this.shadowRoot.getElementById("override-success").textContent = `Voice override set for ${durationLabel}.`;
    } catch (err) {
      if (this._overrideActionIsCurrent(requestId, context)) this._showOverrideError(err);
    } finally {
      if (this._overrideActionPendingId === requestId) this._overrideActionPendingId = null;
      this._syncAvailabilityControls();
    }
  }

  async _clearOverride() {
    this._clearOverrideMessages();
    const context = {
      entityId: this.shadowRoot.getElementById("override-engine").value,
    };
    const requestId = (this._overrideActionRequestId || 0) + 1;
    this._overrideActionRequestId = requestId;
    this._overrideActionPendingId = requestId;
    this._syncAvailabilityControls();
    try {
      if (!context.entityId) throw new Error("Choose an Adaptive TTS entity first.");
      await this._hass.callService("adaptive_tts", "clear_voice_override", {
        entity_id: context.entityId,
        scope: "all",
      });
      if (!this._overrideActionIsCurrent(requestId, context)) return;
      this.shadowRoot.getElementById("override-success").textContent = "Voice override cleared.";
    } catch (err) {
      if (this._overrideActionIsCurrent(requestId, context)) this._showOverrideError(err);
    } finally {
      if (this._overrideActionPendingId === requestId) this._overrideActionPendingId = null;
      this._syncAvailabilityControls();
    }
  }

  async _pipelineChanged() {
    const pipelineId = this.shadowRoot.getElementById("pipeline").value;
    const pipeline = this._data?.pipelines.find((item) => item.id === pipelineId);
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
    this._invalidateGeneration();
    this._engineInfo = null;
    this._engineInfoLanguage = null;
    this._languageRequestId = (this._languageRequestId || 0) + 1;
    const requestId = (this._engineRequestId || 0) + 1;
    this._engineRequestId = requestId;
    const engineId = this.shadowRoot.getElementById("engine").value;
    this.shadowRoot.getElementById("generate").disabled = true;
    if (!engineId) return;
    try {
      const info = await this._hass.callWS({ type: "adaptive_tts/engine", engine_id: engineId });
      if (!this._requestIsCurrent("_engineRequestId", requestId, "engine", engineId)) return;
      this._engineInfo = info;
      const language = this.shadowRoot.getElementById("language");
      language.replaceChildren();
      if (!this._engineAvailable(engineId, info)) {
        this._replaceVoiceControl("voice", [], true, true);
        this.shadowRoot.getElementById("options").replaceChildren();
        this._showError("The selected TTS entity is currently unavailable.");
        this._syncAvailabilityControls();
        return;
      }
      for (const item of info.supported_languages) this._appendOption(language, item, item);
      const requested = preferredLanguage || info.default_language;
      if (requested && info.supported_languages.includes(requested)) language.value = requested;
      await this._languageChanged(preferredVoice);
    } catch (err) {
      if (this._requestIsCurrent("_engineRequestId", requestId, "engine", engineId)) {
        if (this._loading) throw err;
        this._showError(err);
        this._syncAvailabilityControls();
      }
    }
  }

  async _languageChanged(preferredVoice) {
    this._invalidateGeneration();
    this._engineInfo = null;
    this._engineInfoLanguage = null;
    const requestId = (this._languageRequestId || 0) + 1;
    this._languageRequestId = requestId;
    const engineId = this.shadowRoot.getElementById("engine").value;
    const language = this.shadowRoot.getElementById("language").value;
    const generate = this.shadowRoot.getElementById("generate");
    generate.disabled = true;
    if (!engineId || !language) return;
    try {
      const info = await this._hass.callWS({ type: "adaptive_tts/engine", engine_id: engineId, language });
      if (!this._requestIsCurrent("_languageRequestId", requestId, "language", language)) return;
      if (this.shadowRoot.getElementById("engine").value !== engineId) return;
      this._engineInfo = info;
      if (!this._engineAvailable(engineId, info)) {
        this._replaceVoiceControl("voice", [], true, true);
        this.shadowRoot.getElementById("options").replaceChildren();
        this._showError("The selected TTS entity is currently unavailable.");
        this._syncAvailabilityControls();
        return;
      }
      this._engineInfoLanguage = language;
      const voice = this._replaceVoiceControl(
        "voice",
        info.voices,
        info.voices_enumerated,
        true,
      );
      const defaultVoice = preferredVoice || info.default_options.voice;
      if (defaultVoice) {
        if (voice.tagName === "SELECT") {
          if ([...voice.options].some((item) => item.value === defaultVoice)) voice.value = defaultVoice;
        } else {
          voice.value = defaultVoice;
        }
      }
      this.shadowRoot.getElementById("voice-label").style.display =
        info.supported_options.includes("voice") ? "flex" : "none";
      this._renderOptionInputs();
      this._syncAvailabilityControls();
    } catch (err) {
      if (this._requestIsCurrent("_languageRequestId", requestId, "language", language)) {
        if (this._loading) throw err;
        this._showError(err);
        this._syncAvailabilityControls();
      }
    }
  }

  _renderOptionInputs() {
    const container = this.shadowRoot.getElementById("options");
    container.replaceChildren();
    for (const name of this._engineInfo.supported_options.filter((item) => item !== "voice")) {
      const label = document.createElement("label");
      label.textContent = name;
      const defaultValue = this._engineInfo.default_options[name];
      let input;
      if (typeof defaultValue === "boolean") {
        input = document.createElement("select");
        this._appendOption(input, "true", "True");
        this._appendOption(input, "false", "False");
        input.value = String(defaultValue);
        input.dataset.optionType = "boolean";
      } else if (typeof defaultValue === "number") {
        input = document.createElement("input");
        input.type = "number";
        input.step = "any";
        input.value = String(defaultValue);
        input.dataset.optionType = "number";
      } else if (defaultValue !== null && typeof defaultValue === "object") {
        input = document.createElement("textarea");
        input.className = "option-json";
        input.value = JSON.stringify(defaultValue);
        input.dataset.optionType = "json";
      } else {
        input = document.createElement("input");
        input.type = "text";
        input.value = defaultValue ?? "";
        input.placeholder = "Provider default";
        input.dataset.optionType = "string";
      }
      input.dataset.option = name;
      input.addEventListener("input", () => this._invalidateGeneration());
      input.addEventListener("change", () => this._invalidateGeneration());
      label.append(input);
      container.append(label);
    }
  }

  _readOptionInput(input) {
    if (input.value === "") return undefined;
    if (input.dataset.optionType === "boolean") return input.value === "true";
    if (input.dataset.optionType === "number") {
      const value = Number(input.value);
      if (!Number.isFinite(value)) throw new Error(`${input.dataset.option} must be a number.`);
      return value;
    }
    if (input.dataset.optionType === "json") {
      try {
        return JSON.parse(input.value);
      } catch {
        throw new Error(`${input.dataset.option} must contain valid JSON.`);
      }
    }
    return input.value;
  }

  async _generate() {
    this._clearError();
    this._clearResult();
    const button = this.shadowRoot.getElementById("generate");
    button.disabled = true;
    const requestId = (this._generationRequestId || 0) + 1;
    this._generationRequestId = requestId;
    const engineId = this.shadowRoot.getElementById("engine").value;
    const language = this.shadowRoot.getElementById("language").value;
    const fingerprint = this._generationFingerprint();
    try {
      if (!this._engineInfo || this._engineInfoLanguage !== language) {
        throw new Error("Provider details are still loading. Try again in a moment.");
      }
      if (!this._engineAvailable(engineId, this._engineInfo)) {
        throw new Error("The selected TTS entity is currently unavailable.");
      }
      const options = {};
      if (this._engineInfo.supported_options.includes("voice")) {
        const voice = this.shadowRoot.getElementById("voice").value.trim();
        if (voice) options.voice = voice;
      }
      for (const input of this.shadowRoot.querySelectorAll("[data-option]")) {
        const value = this._readOptionInput(input);
        if (value !== undefined) options[input.dataset.option] = value;
      }
      const result = await this._hass.callWS({
        type: "adaptive_tts/generate",
        engine_id: engineId,
        language,
        options,
        message: this.shadowRoot.getElementById("message").value,
      });
      if (!this._generationIsCurrent(requestId, fingerprint)) return;
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
      if (this._generationIsCurrent(requestId, fingerprint)) {
        this._clearResult();
        this._showError(err);
      }
    } finally {
      if (this._generationIsCurrent(requestId, fingerprint)) {
        button.disabled =
          !this._engineInfo ||
          this._engineInfoLanguage !== language ||
          !this._engineAvailable(engineId, this._engineInfo);
      }
    }
  }

  _clearResult() {
    const result = this.shadowRoot.getElementById("result");
    result.style.display = "none";
    const audio = this.shadowRoot.getElementById("audio");
    audio.pause();
    audio.removeAttribute("src");
    for (const id of ["used-engine", "used-underlying", "used-language", "used-options", "used-quiet"]) {
      this.shadowRoot.getElementById(id).textContent = "";
    }
  }

  _audioFailed() {
    if (this.shadowRoot.getElementById("result").style.display === "none") return;
    this._clearResult();
    this._showError("Preview audio could not be retrieved. Check the Home Assistant logs for the provider error.");
  }

  _clearOverrideMessages() {
    this.shadowRoot.getElementById("override-error").textContent = "";
    this.shadowRoot.getElementById("override-success").textContent = "";
  }

  _showOverrideError(err) {
    this.shadowRoot.getElementById("override-error").textContent = err?.message || String(err);
  }

  _clearError() { this.shadowRoot.getElementById("error").textContent = ""; }
  _showError(err) { this.shadowRoot.getElementById("error").textContent = err?.message || String(err); }
}

customElements.define("adaptive-tts-panel", AdaptiveTtsPanel);
