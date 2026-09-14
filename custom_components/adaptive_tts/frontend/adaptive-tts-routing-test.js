import "./adaptive-tts-root-panel.js";

const RootPanel = customElements.get("adaptive-tts-root-panel");
if (RootPanel && !RootPanel.prototype._routingTestEnhanced) {
  RootPanel.prototype._routingTestEnhanced = true;

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
    const cards = [...(this.shadowRoot?.querySelectorAll(".rule") || [])];
    cards.forEach((card, index) => {
      if (card.querySelector(".test-conditions")) return;
      const conditions = card.querySelector(".conditions");
      if (!conditions) return;

      const row = document.createElement("div");
      row.className = "actions routing-test-actions";
      row.innerHTML = `
        <button class="secondary test-conditions" type="button">Test conditions</button>
        <span class="status test-condition-result" role="status"></span>`;
      conditions.append(row);

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
