import "./adaptive-tts-root-panel.js";

const RootPanel = customElements.get("adaptive-tts-root-panel");
if (RootPanel && !RootPanel.prototype._routingTestEnhanced) {
  RootPanel.prototype._routingTestEnhanced = true;

  const refineNestedPanel = (rootPanel) => {
    const panel = rootPanel.shadowRoot?.querySelector("adaptive-tts-panel");
    const shadow = panel?.shadowRoot;
    if (!shadow || shadow.querySelector("style[data-routing-copy-refine]")) return;

    const cards = shadow.querySelectorAll("ha-card");
    const overrideCard = cards[0];
    const testCard = cards[1];
    if (overrideCard) {
      const intros = overrideCard.querySelectorAll(".intro");
      if (intros[0]) {
        intros[0].textContent =
          "Control voice overrides and preview TTS output without changing an Assist pipeline.";
      }
      if (intros[1]) {
        intros[1].textContent = "Choose where the override applies and which voice to use.";
        intros[1].classList.add("section-tagline");
      }
      const hint = overrideCard.querySelector(".hint");
      if (hint) {
        hint.textContent =
          "Persistent overrides survive restarts; next-request overrides are used once.";
      }
    }
    if (testCard) {
      const intro = testCard.querySelector(".intro");
      if (intro) {
        intro.textContent = "Preview a source or Adaptive TTS entity without changing an Assist pipeline.";
        intro.classList.add("section-tagline");
      }
      const hint = testCard.querySelector(".hint");
      if (hint) hint.textContent = "Preview audio is temporary.";
    }

    const style = document.createElement("style");
    style.dataset.routingCopyRefine = "true";
    style.textContent = `
      .intro { margin-bottom: 18px; }
      .section-tagline {
        margin-top: -2px;
        margin-bottom: 16px;
        font-size: 13px;
        line-height: 1.4;
      }
      .actions .hint {
        flex-basis: 100%;
        margin-top: -4px;
        line-height: 1.4;
      }
    `;
    shadow.append(style);
  };

  const originalRenderShell = RootPanel.prototype._renderShell;
  RootPanel.prototype._renderShell = function (...args) {
    originalRenderShell.apply(this, args);

    const style = document.createElement("style");
    style.textContent = `
      .routing-page {
        max-width: 880px;
        padding: 24px 0 0;
      }
      .routing-shell {
        padding: 24px;
      }
      .page-head {
        margin-bottom: 18px;
      }
      .eyebrow {
        display: none;
      }
      .intro {
        max-width: 720px;
        margin-top: 6px;
      }
      .toolbar {
        display: block;
        padding: 0;
        border: 0;
        border-radius: 0;
        background: transparent;
      }
      .toolbar .help {
        margin-top: 5px;
      }
      .precedence {
        display: block;
        margin-top: 14px;
        padding: 0;
        border: 0;
        border-radius: 0;
        background: transparent;
        color: var(--secondary-text-color);
        font-size: 12px;
      }
      .precedence-badge {
        display: none;
      }
      .rules-section-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin-top: 22px;
        padding-top: 18px;
        border-top: 1px solid var(--divider-color);
      }
      .rules-section-title {
        font-size: 16px;
        font-weight: 600;
      }
      .rules-section-head #add-rule {
        min-height: 36px;
        padding: 8px 13px;
      }
      .rules {
        margin-top: 12px;
        gap: 16px;
      }
      .rule {
        border-radius: 10px;
        box-shadow: none;
      }
      .rule-head {
        grid-template-columns: minmax(0, 1fr) auto;
        padding: 16px 18px;
        background: var(--card-background-color);
        gap: 16px;
      }
      .rule-identity {
        align-items: center;
      }
      .priority {
        min-width: auto;
        height: 24px;
        padding: 0 9px;
        font-size: 11px;
      }
      .rule-title input {
        margin-top: 0;
      }
      .rule-head-actions {
        gap: 8px;
      }
      .enabled {
        min-height: 36px;
        padding: 0 9px;
        border-color: transparent;
        background: transparent;
      }
      .rule-actions {
        gap: 4px;
      }
      button.icon {
        min-width: 36px;
        min-height: 36px;
        padding: 6px 9px;
      }
      .rule-body {
        gap: 0;
        padding: 0 18px 18px;
      }
      .voice-section {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
        padding: 16px 0;
        border-bottom: 1px solid var(--divider-color);
        border-radius: 0;
        background: transparent;
      }
      .voice-section .field {
        gap: 6px;
      }
      .voice-section .help {
        display: none;
      }
      .conditions {
        padding: 16px 0 0;
        border: 0;
        border-radius: 0;
        background: transparent;
      }
      .section-heading {
        align-items: center;
        margin: 0 0 8px;
      }
      .conditions-title {
        font-size: 15px;
      }
      .conditions > .help {
        margin: 0 0 12px;
      }
      .condition-host {
        margin-top: 0;
        padding: 0;
        border-radius: 0;
        background: transparent;
      }
      .routing-test-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0;
        padding: 0;
        border: 0;
      }
      .routing-test-actions .test-conditions {
        min-height: 34px;
        padding: 7px 11px;
        white-space: nowrap;
      }
      .test-condition-result {
        max-width: 300px;
      }
      .save-bar {
        justify-content: flex-start;
        margin-top: 18px;
        padding-top: 16px;
      }
      .save-bar .status {
        margin-left: 2px;
      }
      .empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        margin-top: 12px;
        padding: 32px 20px;
        background: transparent;
      }
      .empty strong {
        color: var(--primary-text-color);
        margin-bottom: 4px;
      }
      .empty #add-rule {
        margin-top: 16px;
        color: var(--text-primary-color);
        background: var(--primary-color);
        border-color: var(--primary-color);
      }
      @media (max-width: 928px) {
        .routing-page {
          box-sizing: border-box;
          max-width: none;
          margin: 0 24px;
        }
      }
      @media (max-width: 760px) {
        .routing-page {
          margin: 0 12px;
          padding-top: 12px;
        }
        .routing-shell {
          padding: 18px;
        }
        .rules-section-head {
          align-items: flex-start;
        }
        .rule-head {
          grid-template-columns: 1fr;
        }
        .rule-head-actions {
          justify-content: flex-start;
        }
        .voice-section {
          grid-template-columns: 1fr;
        }
        .section-heading {
          align-items: flex-start;
          flex-direction: column;
        }
        .routing-test-actions {
          width: 100%;
        }
        .save-bar {
          flex-direction: row;
          align-items: center;
          flex-wrap: wrap;
        }
      }
    `;
    this.shadowRoot.append(style);

    const title = this.shadowRoot.querySelector(".page-head h2");
    const intro = this.shadowRoot.querySelector(".page-head .intro");
    const toolbarHelp = this.shadowRoot.querySelector(".toolbar .help");
    const precedence = this.shadowRoot.querySelector(".precedence span:last-child");
    if (title) title.textContent = "Conditional Voice Routing";
    if (intro) {
      intro.textContent =
        "Create ordered rules that choose a voice when Home Assistant conditions match. The first matching enabled rule is used.";
    }
    if (toolbarHelp) {
      toolbarHelp.textContent = "Rules are stored separately for each Adaptive TTS entity.";
    }
    if (precedence) {
      precedence.textContent = "Manual voice overrides temporarily take precedence over routing rules.";
    }

    const rules = this.shadowRoot.getElementById("rules");
    if (rules && !this.shadowRoot.querySelector(".rules-section-head")) {
      const header = document.createElement("div");
      header.className = "rules-section-head";
      header.innerHTML = '<div class="rules-section-title">Routing rules</div>';
      rules.before(header);
      const addButton = this.shadowRoot.getElementById("add-rule");
      if (addButton) header.append(addButton);
    }

    refineNestedPanel(this);
    queueMicrotask(() => refineNestedPanel(this));
  };

  const originalEngineChanged = RootPanel.prototype._engineChanged;
  RootPanel.prototype._engineChanged = async function (...args) {
    const select = this.shadowRoot?.getElementById("routing-engine");
    const nextEntityId = select?.value || "";
    const currentEntityId = this._routingLoadedEntityId || "";

    if (
      this._dirty &&
      currentEntityId &&
      nextEntityId &&
      nextEntityId !== currentEntityId
    ) {
      const discard = globalThis.confirm(
        "Discard unsaved routing changes and switch Adaptive TTS entity?"
      );
      if (!discard) {
        select.value = currentEntityId;
        this._setStatus("Unsaved changes.");
        return;
      }
    }

    await originalEngineChanged.apply(this, args);
    if (!this._dirty && select?.value) {
      this._routingLoadedEntityId = select.value;
    }
  };

  const originalRenderRules = RootPanel.prototype._renderRules;
  RootPanel.prototype._renderRules = async function (...args) {
    await originalRenderRules.apply(this, args);

    const addButton = this.shadowRoot?.getElementById("add-rule");
    const rulesHeader = this.shadowRoot?.querySelector(".rules-section-head");
    const empty = this.shadowRoot?.querySelector(".empty");
    if (addButton) {
      if (empty) {
        addButton.textContent = "+ Add first rule";
        empty.append(addButton);
      } else if (rulesHeader) {
        addButton.textContent = "+ Add rule";
        rulesHeader.append(addButton);
      }
    }

    const cards = [...(this.shadowRoot?.querySelectorAll(".rule") || [])];
    cards.forEach((card, index) => {
      const conditions = card.querySelector(".conditions");
      if (!conditions) return;

      const explanatoryText = conditions.querySelector(":scope > .help");
      if (explanatoryText) {
        explanatoryText.textContent = "Set the Home Assistant conditions for this voice.";
      }

      if (card.querySelector(".test-conditions")) return;
      const heading = conditions.querySelector(".section-heading") || conditions;
      const row = document.createElement("div");
      row.className = "routing-test-actions";
      row.innerHTML = `
        <button class="secondary test-conditions" type="button">Test conditions</button>
        <span class="status test-condition-result" role="status"></span>`;
      heading.append(row);

      row.querySelector(".test-conditions").addEventListener("click", () => {
        void this._testRoutingConditions(index, row);
      });
    });
  };

  RootPanel.prototype._testRoutingConditions = async function (index, row) {
    const button = row.querySelector(".test-conditions");
    const status = row.querySelector(".test-condition-result");
    const rule = this._rules?.[index];
    if (!rule) return;

    button.disabled = true;
    status.className = "status test-condition-result";
    status.textContent = "Testing against current Home Assistant state…";
    try {
      const result = await this._hass.callWS({
        type: "adaptive_tts/routing_test",
        target_index: index,
        rules: this._rules.map((item) => ({
          name: item.name,
          enabled: item.enabled !== false,
          conditions: item.conditions || [],
        })),
      });

      if (!result.matches) {
        status.textContent = "Does not match now.";
      } else if (!result.enabled) {
        status.textContent = "Matches now, but this rule is disabled.";
      } else if (result.would_win) {
        status.textContent = "Matches now — this rule would be selected.";
        status.classList.add("success");
      } else if (result.winner_name) {
        status.textContent = `Matches now, but higher-priority rule “${result.winner_name}” would be selected first.`;
      } else {
        status.textContent = "Matches now.";
      }
    } catch (err) {
      status.textContent = `Cannot test: ${this._errorText(err)}`;
      status.classList.add("error");
    } finally {
      button.disabled = false;
    }
  };
}
