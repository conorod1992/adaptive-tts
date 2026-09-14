# Adaptive TTS

Adaptive TTS is a Home Assistant custom integration that creates a TTS entity
which wraps another TTS entity. It lets Home Assistant keep using one TTS entity
while the effective voice can be changed manually or selected automatically from
ordered Home Assistant conditions, without rewriting an Assist pipeline.

```text
Assist / automation
        |
        v
Adaptive TTS
        |
        +--> explicit voice override, if present
        |
        +--> first matching Conditional Voice Routing rule
        |
        v
underlying TTS provider
        |
        v
audio returned to Home Assistant
```

Adaptive TTS does not rewrite or shorten text, alter Assist conversation
responses, control media-player or satellite volume, or use an LLM. It changes
only supported TTS presentation options.

## Features

- Config-entry setup and provider selection managed entirely in the Home
  Assistant UI.
- Wraps an existing `tts.*` entity and exposes its languages, defaults,
  supported option names, and supported voices.
- Home Assistant actions can override the voice for the next TTS request or
  persistently until changed or cleared.
- Conditional Voice Routing can automatically select a language/voice from
  ordered rules built with Home Assistant's native condition system.
- Explicit manual overrides take precedence over Conditional Voice Routing.
- Preserves incoming options and replaces only explicitly overridden options.
- Rejects Adaptive TTS entities as providers, preventing direct and indirect
  wrapper loops.
- Forwards streaming input when the underlying entity supports it; otherwise
  safely collects the text and uses one-shot synthesis.
- Includes an admin-only Adaptive TTS panel for voice overrides, Conditional
  Voice Routing, and TTS testing with native temporary audio playback.
- Provides redacted diagnostics without generated speech text.

## Installation with HACS

1. In HACS, open **Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/conorod1992/adaptive-tts` as an **Integration**.
4. Install **Adaptive TTS** and restart Home Assistant.

For manual installation, copy `custom_components/adaptive_tts` into the
matching directory under your Home Assistant configuration and restart.

## Configuration

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Adaptive TTS**.
3. Enter a name and select the source TTS entity, for example
   `tts.home_assistant_cloud`.

To change the wrapped provider later, open the Adaptive TTS integration entry
and choose **Configure**. Changing the provider reloads the Adaptive TTS config
entry so the wrapper immediately picks up the new provider's defaults,
languages, voices, and supported options.

Adaptive TTS can be used in either of two ways:

- keep policy elsewhere in Home Assistant and call the voice override actions
  when required; or
- configure Conditional Voice Routing rules inside Adaptive TTS for automatic
  voice selection based on Home Assistant state and conditions.

## Using Adaptive TTS in Assist

After setup, edit an Assist pipeline and select the new entity, usually named
something like `tts.adaptive_tts` or `tts.bedroom_tts`, as its TTS engine.
Choose the pipeline language and normal voice as usual.

Automations can use the Adaptive TTS entity anywhere they would use a normal
TTS entity. The integration generates and returns audio; it never calls
`tts.speak` and never targets a media player directly.

## Voice override actions

Adaptive TTS exposes two Home Assistant actions.

### `adaptive_tts.set_voice_override`

Targets one or more Adaptive TTS entities and accepts:

- **Language** — the language/accent code, such as `en-GB`. This is explicit
  because provider voices are language-specific. The Home Assistant action
  editor uses its native language selector for this field.
- **Voice** — the provider voice ID exposed for that language.
- **Duration**:
  - **Next TTS request** — use the override once, then automatically return to
    the normal routing/provider behavior.
  - **Until changed again** — keep using the override until another persistent
    override replaces it or it is cleared.

A next-request override is intentionally in-memory only. A persistent override
is saved in Home Assistant storage and survives restarts.

Adaptive TTS does **not** rewrite the Assist pipeline when setting a persistent
override. Any pipeline or automation using the targeted Adaptive TTS entity
gets the override, while the pipeline's own configuration remains unchanged.

### `adaptive_tts.clear_voice_override`

Clears:

- all explicit overrides;
- only a pending next-request override; or
- only the persistent override.

If Conditional Voice Routing is configured, clearing the explicit override
allows routing to take effect again. If no routing rule matches, the wrapper
falls back to the ordinary provider/pipeline settings.

For manual use, the Adaptive TTS panel provides the same set/clear behavior
without requiring voice IDs to be typed. It loads the wrapped provider's
languages and then dynamically loads the voices available for the selected
language.

## Conditional Voice Routing

Conditional Voice Routing lets one Adaptive TTS entity automatically choose a
different provider language and voice according to Home Assistant state. Rules
are configured in the Adaptive TTS panel and use Home Assistant's native
condition format and condition engine.

Each rule contains:

- a name;
- an enabled/disabled state;
- one or more Home Assistant conditions;
- a provider language, when applicable; and
- a provider voice.

Rules are evaluated **from top to bottom**. Disabled rules are skipped. All
conditions inside a rule must currently match. The first enabled matching rule
whose language/voice is valid for the current provider wins; lower-priority
rules are not applied.

This makes rule order significant. For example, a more specific late-night rule
can be placed above a broader evening rule so it wins whenever both match.

### Precedence

Effective voice selection follows this order:

1. an explicit manual override set with `adaptive_tts.set_voice_override`;
2. the first valid matching Conditional Voice Routing rule; then
3. the normal incoming/provider defaults if no override or route applies.

Both next-request and persistent manual overrides therefore take precedence over
a matching routing rule. A next-request override is consumed by that request;
a persistent override continues to win until it is replaced or cleared.

### Managing rules in the panel

The Conditional Voice Routing section lets an administrator:

- add and remove rules;
- enable or disable individual rules;
- reorder rules to change priority;
- edit conditions with Home Assistant's native condition selector;
- select the language and voice exposed by the wrapped provider;
- test a draft rule against current Home Assistant state before saving; and
- save the ordered rule set back to the config entry.

**Test conditions** evaluates the unsaved draft against current Home Assistant
state. It reports whether the target rule matches and, if it does, whether it
would actually win or whether a higher-priority enabled rule would be selected
first. Testing does not persist the draft or reload the config entry.

Saving validates every rule and its Home Assistant conditions before changing
the config entry. A successful save reloads the Adaptive TTS entry so the new
routing policy becomes active immediately.

The panel protects unsaved work when switching between Adaptive TTS entities:
if the current routing draft has changes, it asks before discarding them.
Backend save failures also leave the draft intact so it can be corrected and
retried.

Adaptive TTS supports up to 50 routing rules per entity. Every saved rule must
have a non-empty ID, name and voice and at least one valid Home Assistant
condition.

### Invalid or stale persisted rules

Persisted routing data is treated fail-safe. If a previously saved routing set
can no longer be validated or compiled—for example after a Home Assistant
condition-schema change or external/manual storage modification—Adaptive TTS
does not let that routing data prevent the TTS entity from loading.

Instead, it logs a warning, ignores the unusable routing set for that runtime,
and continues with normal provider behavior. The stored configuration is left
unchanged rather than silently rewritten, so the user can inspect and repair it.

A matching rule that becomes invalid specifically at request time, such as a
voice no longer supported by the provider, is ignored and evaluation continues
to the next matching rule.

## Adaptive TTS panel

Open the Adaptive TTS integration's **Configure** panel from **Settings →
Devices & services**. The panel is registered as an integration configuration
panel and does not add a permanent sidebar item.

### Voice override

The panel lets an administrator:

- choose an Adaptive TTS entity;
- choose one of the entity's supported languages;
- choose a voice dynamically loaded from the wrapped provider for that
  language;
- set the voice for the **next TTS request** or **until changed again**; and
- clear explicit voice overrides.

These controls call the same `adaptive_tts.set_voice_override` and
`adaptive_tts.clear_voice_override` actions used by automations. They do not
introduce separate override state or modify the Assist pipeline.

### TTS Test

The TTS Test section lets an administrator:

- choose an Assist pipeline and read its current `tts_engine`, `tts_language`,
  and `tts_voice` as test defaults;
- directly select either a source TTS entity or an Adaptive TTS wrapper;
- inspect supported languages, voices, and provider option names;
- override test options without changing the Assist pipeline;
- generate and replay audio; and
- see the requested entity, actual underlying entity, effective language, and
  effective options.

Preview generation uses Home Assistant's authenticated WebSocket API to create
a native TTS result stream. The spoken text is passed as a message stream,
which deliberately selects Home Assistant's temporary in-memory cache path.
Playback uses Home Assistant's short-lived `/api/tts_proxy/` URL. Adaptive TTS
does not write or retain preview files, and Home Assistant's TTS manager expires
both the stream token and in-memory audio.

## Provider costs and compatibility

The underlying provider still performs synthesis. Its account, subscription,
network access, rate limits, and API costs all continue to apply. Adaptive TTS
does not provide voices of its own.

Explicit voice overrides and routed voices are validated against the provider's
current `supported_options`, supported languages, and
`async_get_supported_voices` data when the provider supplies a finite voice
list. An invalid explicit override fails clearly and is cleared so it cannot
poison later requests. An invalid routing candidate is skipped so another
matching rule or the normal provider defaults can still be used. Providers that
do not enumerate voices can still accept provider-specific voice IDs.

Underlying provider output is also validated before Adaptive TTS returns it to
Home Assistant. Missing audio, malformed one-shot results, malformed streaming
responses, non-byte stream chunks, and provider exceptions are treated as TTS
failures and follow the same explicit-override recovery path.

If the underlying provider temporarily disappears or becomes unavailable,
Adaptive TTS reports itself unavailable while keeping its config entry loaded.
When the provider becomes available again, the same Adaptive TTS entity can
recover without requiring a manual integration reload.

Home Assistant forms its normal non-streaming cache identity before invoking a
TTS entity. Adaptive TTS contributes a private, self-contained request snapshot
through its public default-options metadata so normal, routed, one-shot voice
override, and persistent voice override results use the correct cache identity.
A unique request nonce prevents separately prepared streams from sharing a
pending one-shot override cache entry. The private snapshot is removed before
delegation and is never sent to the underlying provider.

## Architecture and Home Assistant APIs

This version targets the Home Assistant 2026.8+ TTS entity API:

- `tts.get_engine_instance`/the TTS helper resolves the configured entity;
- `TextToSpeechEntity` metadata is mirrored dynamically;
- `async_get_tts_audio` delegates one-shot synthesis;
- `async_stream_tts_audio` delegates streaming input when supported and falls
  back to collecting input otherwise; and
- `tts.async_create_stream` provides native preview audio and bounded lifetime.

Conditional Voice Routing compiles Home Assistant-native condition definitions
through Home Assistant's condition helpers. Routing rules are stored in the
Adaptive TTS config entry options and are recompiled whenever that entry loads
or reloads.

There is currently no separate high-level public API whose sole purpose is
"synthesize through another entity." The wrapper therefore delegates through
the documented entity methods instead of reaching into the TTS manager's
private entity collection, invoking a service, or making a loopback HTTP
request. The Assist pipeline reaches Adaptive TTS through the standard TTS
manager, so the pipeline is not bypassed.

Persistent voice action state is owned by Adaptive TTS and stored with Home
Assistant's normal storage helper. It does not mutate Assist pipeline records.

## Development and manual testing

```bash
python -m pip install -r requirements_test.txt
node --test tests/*.test.mjs
python -m pytest tests
python -m ruff check .
python -m ruff format --check .

# Real Home Assistant acceptance tests
python -m pip install -r requirements_real_ha.txt
python scripts/install_real_ha_component_requirements.py
python -m pytest tests_real_ha

# Browser acceptance tests
npm install
npx playwright install chromium
npm run test:browser
```

CI runs the fast tests plus dedicated Real Home Assistant and Playwright browser
acceptance lanes. The Real HA suite is also exercised against the current
stable Home Assistant release and, when one is available, an upcoming
prerelease.

For a Home Assistant Cloud manual test:

1. Confirm `tts.home_assistant_cloud` works directly.
2. Open Adaptive TTS's TTS Test panel and select an English language.
3. Generate the same sentence directly with two different listed voices.
4. Generate through the Adaptive TTS wrapper and confirm the reported
   underlying entity, effective language, and options.
5. Use the panel or call `adaptive_tts.set_voice_override` with **Next TTS
   request**, then run an Assist request twice and confirm only the first uses
   that voice.
6. Configure two routing rules that can both match, put the intended winner
   first, and use **Test conditions** to confirm priority behavior.
7. Clear any explicit override and confirm a matching routing rule changes the
   effective voice; then set a persistent manual override and confirm it wins
   over routing.
8. Use **Until changed again**, restart Home Assistant, and confirm the override
   remains active.
9. Clear the override from the panel or call
   `adaptive_tts.clear_voice_override` and confirm routing or ordinary provider
   behavior resumes as appropriate.
10. Disable or remove the source provider and confirm the wrapper becomes
    unavailable, then restore the provider and confirm the wrapper recovers.

## Scope

Adaptive TTS deliberately keeps its policy surface limited to **TTS
presentation**. It supports explicit voice overrides and conditional
language/voice routing, but it does not rewrite speech text, infer emotion or
sentiment, change media-player volume, schedule notifications, choose target
rooms/media players, or alter broader Assist/satellite behavior.

Use Home Assistant automations, scripts and helpers for broader policy. Those
systems can either call Adaptive TTS's explicit override actions or expose the
state consumed by Conditional Voice Routing rules.

## License

Adaptive TTS is available under the MIT License.
