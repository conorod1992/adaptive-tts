# Adaptive TTS

Adaptive TTS is a Home Assistant custom integration that creates a TTS entity
which wraps another TTS entity. It can change a provider option at synthesis
time—initially for a quiet-hours voice or style—then returns the provider's
audio to Home Assistant unchanged.

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
- Preserves incoming options and replaces only the configured quiet option.
- Rejects Adaptive TTS entities as providers, preventing direct and indirect
  wrapper loops.
- Forwards streaming input when the underlying entity supports it; otherwise
  safely collects the text and uses one-shot synthesis.
- Includes an admin-only TTS Test configuration panel with native temporary
  audio playback and no permanent preview files.
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
5. Select the provider option to override and enter its exact value.

Home Assistant Cloud exposes voice variants as voice IDs. Select `voice` as
the quiet option and enter the exact ID shown in the TTS Test panel. A variant
may look like a base voice plus a provider-defined style suffix. Available
voices and styles depend entirely on the selected provider and language.

To change the provider or quiet-hours policy later, open the Adaptive TTS
integration entry and choose **Configure**.

If the start and end times are identical, quiet mode is active all day. The
start is inclusive and the end is exclusive.

## Using Adaptive TTS in Assist

After setup, edit an Assist pipeline and select the new entity, usually named
something like `tts.adaptive_tts` or `tts.bedroom_tts`, as its TTS engine.
Choose the language and normal voice as usual. Adaptive TTS preserves those
normal pipeline options outside quiet hours and applies the configured quiet
override during quiet hours. It does not modify the pipeline itself.

Automations can use the Adaptive TTS entity anywhere they would use a normal
TTS entity. The integration generates and returns audio; it never calls
`tts.speak` and never targets a media player directly.

## TTS Test panel

Open the Adaptive TTS integration's **Configure** panel from **Settings →
Devices & services**. The panel is registered as an integration configuration
panel and does not add a permanent sidebar item.

The panel lets an administrator:

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
4. Configure that variant as the Adaptive TTS `voice` quiet override.
5. Generate through the wrapper inside and outside the configured time range;
   confirm the reported underlying entity, effective options, and quiet state.
6. Select the wrapper in a temporary Assist pipeline and run a voice request.
7. Disable or remove the source provider and confirm the wrapper reports a
   clear unavailable-provider error.

## Scope

Version 1 intentionally has one explicit quiet-hours override. It does not
include emotion inference, sentiment analysis, text rewriting, notification
handling, volume control, per-room rules, or a generic automation policy
builder. The option-oriented design allows explicit cheerful, sad, sarcastic,
or other provider-defined variants to be added later without changing the
delegation core.

## License

Adaptive TTS is available under the MIT License.
