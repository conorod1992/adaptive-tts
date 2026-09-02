# Adaptive TTS

Adaptive TTS is a Home Assistant custom integration that creates a TTS entity
which wraps another TTS entity. It lets Home Assistant keep using one TTS entity
while a voice can be changed temporarily or persistently without rewriting an
Assist pipeline.

```text
Assist / automation
        |
        v
Adaptive TTS
        |
        v
underlying TTS provider
        |
        v
audio returned to Home Assistant
```

Adaptive TTS does not rewrite or shorten text, alter Assist conversation
responses, control media-player or satellite volume, schedule presentation
changes, or use an LLM. It only changes supported TTS presentation options when
explicitly requested.

## Features

- Config-entry setup and provider selection managed entirely in the Home
  Assistant UI.
- Wraps an existing `tts.*` entity and exposes its languages, defaults,
  supported option names, and supported voices.
- Home Assistant actions can override the voice for the next TTS request or
  persistently until changed or cleared.
- Preserves incoming options and replaces only explicitly overridden options.
- Rejects Adaptive TTS entities as providers, preventing direct and indirect
  wrapper loops.
- Forwards streaming input when the underlying entity supports it; otherwise
  safely collects the text and uses one-shot synthesis.
- Includes an admin-only Adaptive TTS panel for voice override controls and TTS
  testing with native temporary audio playback.
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
and choose **Configure**.

Adaptive TTS deliberately does not decide *when* a quieter or different voice
should be used. Scheduling, room state, household mode, or other broader
assistant/satellite policy can live elsewhere in Home Assistant and call the
voice override actions when required.

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
    the normal provider/pipeline voice.
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

Clearing the persistent override returns the entity to the ordinary provider and
pipeline settings.

For manual use, the Adaptive TTS panel provides the same set/clear behavior
without requiring voice IDs to be typed. It loads the wrapped provider's
languages and then dynamically loads the voices available for the selected
language.

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

Explicit voice overrides are validated against the provider's current
`supported_options`, supported languages, and `async_get_supported_voices` data
when the provider supplies a finite voice list. An invalid explicit override
fails clearly and is cleared so it cannot poison later requests. Providers that
do not enumerate voices can still accept provider-specific voice IDs.

Underlying provider output is also validated before Adaptive TTS returns it to
Home Assistant. Missing audio, malformed one-shot results, malformed streaming
responses, non-byte stream chunks, and provider exceptions are treated as TTS
failures and follow the same explicit-override recovery path.

Home Assistant forms its normal non-streaming cache identity before invoking a
TTS entity. Adaptive TTS contributes a private, self-contained request snapshot
through its public default-options metadata so normal, one-shot voice override,
and persistent voice override results use the correct cache identity. A unique
request nonce prevents separately prepared streams from sharing a pending
one-shot override cache entry. The private snapshot is removed before delegation
and is never sent to the underlying provider.

## Architecture and Home Assistant APIs

This version targets the Home Assistant 2026.8+ TTS entity API:

- `tts.get_engine_instance`/the TTS helper resolves the configured entity;
- `TextToSpeechEntity` metadata is mirrored dynamically;
- `async_get_tts_audio` delegates one-shot synthesis;
- `async_stream_tts_audio` delegates streaming input when supported and falls
  back to collecting input otherwise; and
- `tts.async_create_stream` provides native preview audio and bounded lifetime.

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
node --test tests/frontend.test.mjs
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

For a Home Assistant Cloud manual test:

1. Confirm `tts.home_assistant_cloud` works directly.
2. Open Adaptive TTS's TTS Test panel and select an English language.
3. Generate the same sentence directly with two different listed voices.
4. Generate through the Adaptive TTS wrapper and confirm the reported
   underlying entity, effective language, and options.
5. Use the panel or call `adaptive_tts.set_voice_override` with **Next TTS
   request**, then run an Assist request twice and confirm only the first uses
   that voice.
6. Use **Until changed again**, restart Home Assistant, and confirm the override
   remains active.
7. Clear the override from the panel or call
   `adaptive_tts.clear_voice_override` and confirm ordinary behavior resumes.
8. Disable or remove the source provider and confirm the wrapper reports a
   clear unavailable-provider error.

## Scope

Adaptive TTS deliberately keeps TTS behavior explicit. It does not include
emotion inference, sentiment analysis, text rewriting, notification handling,
volume control, per-room rules, scheduling, satellite feedback policy, or a
generic automation policy builder. Those broader decisions can live elsewhere
and use Adaptive TTS only as the voice-control endpoint when needed.

## License

Adaptive TTS is available under the MIT License.
