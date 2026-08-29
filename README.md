# Adaptive TTS

Adaptive TTS is a Home Assistant custom integration that creates a TTS entity
which wraps another TTS entity. It can change provider options at synthesis
time—initially for quiet-hours behavior and explicit voice overrides—then
returns the provider's audio to Home Assistant unchanged.

It is useful when the same Assist pipeline or automation should keep using one
TTS entity while its presentation changes by policy. A typical setup uses the
normal Home Assistant Cloud voice during the day and a supported whisper voice
variant overnight.

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
responses, control media-player or satellite volume, or use an LLM. It only
changes supported TTS presentation options during audio synthesis.

## Features

- Config-entry setup and options managed entirely in the Home Assistant UI.
- Wraps an existing `tts.*` entity and exposes its languages, defaults,
  supported option names, and supported voices.
- Quiet hours support ordinary and cross-midnight ranges such as
  `23:00–07:00`.
- Quiet voice configuration lets you choose the language/accent first and then
  a voice exposed for that language.
- Home Assistant actions can override the voice for the next TTS request or
  persistently until changed or cleared.
- Preserves incoming options and replaces only the configured/explicit options.
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
4. Enable or disable quiet mode and choose the start and end times.
5. Select the provider option to override.
6. For a voice override, choose the language/accent family first and then choose
   a voice exposed by the provider for that language.

Home Assistant Cloud exposes voice variants as voice IDs. Available voices and
styles depend entirely on the selected provider and language.

To change the provider or quiet-hours policy later, open the Adaptive TTS
integration entry and choose **Configure**.

If the start and end times are identical, quiet mode is active all day. The
start is inclusive and the end is exclusive.

When the override is `voice`, the configuration UI enumerates the provider's
supported languages first, then loads voices for the selected language. If a
provider does not enumerate voices, Adaptive TTS retains a text-field fallback.
Non-voice options such as `style` or `emotion` also use a text field because
Home Assistant does not provide a generic API for enumerating arbitrary option
values.

## Using Adaptive TTS in Assist

After setup, edit an Assist pipeline and select the new entity, usually named
something like `tts.adaptive_tts` or `tts.bedroom_tts`, as its TTS engine.
Choose the language and normal voice as usual. Adaptive TTS preserves those
normal pipeline options outside quiet hours and applies the configured quiet
override during quiet hours. It does not modify the pipeline itself.

Automations can use the Adaptive TTS entity anywhere they would use a normal
TTS entity. The integration generates and returns audio; it never calls
`tts.speak` and never targets a media player directly.

## Voice override actions

Adaptive TTS exposes two Home Assistant actions.

### `adaptive_tts.set_voice_override`

Targets one or more Adaptive TTS entities and accepts:

- **Language** — the language/accent code, such as `en-GB`. This is explicit
  because provider voices are language-specific and prevents accidentally
  pairing a voice with the quiet-hours or pipeline language from another
  accent family. The Home Assistant action editor uses its native language
  selector for this field.
- **Voice** — the provider voice ID exposed for that language.
- **Duration**:
  - **Next TTS request** — use the override once, then automatically return to
    the normal/quiet-hours policy.
  - **Until changed again** — keep using the override until another persistent
    override replaces it or it is cleared.

A next-request override is intentionally in-memory only. A persistent override
is saved in Home Assistant storage and survives restarts.

An explicit voice override takes precedence over a quiet-hours **voice**
override. If quiet mode changes another option such as style or emotion, that
option may still be applied alongside the explicit voice.

Adaptive TTS does **not** rewrite the Assist pipeline when setting a persistent
override. Any pipeline or automation using the targeted Adaptive TTS entity
gets the override, while the pipeline's own configuration remains unchanged.

### `adaptive_tts.clear_voice_override`

Clears:

- all explicit overrides;
- only a pending next-request override; or
- only the persistent override.

Clearing the persistent override returns the entity to its ordinary pipeline
and quiet-hours behavior.

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
- see the requested entity, actual underlying entity, effective language and
  options, and whether quiet mode was active.

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

At runtime, a configured quiet option is checked against the provider's current
`supported_options`. A `voice` override is also checked against
`async_get_supported_voices` when the provider supplies a list. If a capability
or voice disappears, synthesis fails with a useful Home Assistant error rather
than silently sending a stale override. Providers that do not enumerate valid
values for a non-voice option can only be validated by the provider itself.

Home Assistant forms its normal non-streaming cache identity before invoking a
TTS entity. Adaptive TTS contributes a private policy fingerprint through its
public default-options metadata so normal, quiet, one-shot voice override, and
persistent voice override results use different cache entries. A unique token
is used for each next-request override. The fingerprint is removed before
delegation and is never sent to the underlying provider.

## Architecture and Home Assistant APIs

This version targets the current Home Assistant Core `dev` TTS entity API:

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
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

For a Home Assistant Cloud manual test:

1. Confirm `tts.home_assistant_cloud` works directly.
2. Open Adaptive TTS's TTS Test panel and select an English language.
3. Generate the same sentence directly with a normal voice and a listed voice
   variant.
4. Configure that variant as the Adaptive TTS quiet voice override.
5. Generate through the wrapper inside and outside the configured time range;
   confirm the reported underlying entity, effective options, and quiet state.
6. Use the panel or call `adaptive_tts.set_voice_override` with **Next TTS
   request**, then run an Assist request twice and confirm only the first uses
   that voice.
7. Use **Until changed again**, restart Home Assistant, and confirm the override
   remains active.
8. Clear the override from the panel or call
   `adaptive_tts.clear_voice_override` and confirm ordinary behavior resumes.
9. Disable or remove the source provider and confirm the wrapper reports a
   clear unavailable-provider error.

## Scope

Adaptive TTS deliberately keeps policy explicit. It does not include emotion
inference, sentiment analysis, text rewriting, notification handling, volume
control, per-room rules, or a generic automation policy builder. Provider voice
and style choices can be driven explicitly from Home Assistant automations
without adding an LLM decision layer.

## License

Adaptive TTS is available under the MIT License.
