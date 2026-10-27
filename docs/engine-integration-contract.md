# Engine Integration Contract

The engine plugins consume versioned audio banks instead of calling the Python API during gameplay.

## Runtime boundary

The Unity and Unreal runtimes must be able to load a bank from local packaged files and:

- find an event by ID;
- set a numeric parameter by ID;
- start and stop an event;
- select active layers from parameter ranges;
- crossfade between layers using the transition duration.

AI generation, MIDI analysis, soundfont rendering, and bank export happen in the authoring tool or backend. A shipped game should not require Python, FastAPI, FluidSynth, MusicGen, or an internet connection.

## Bank format

The machine-readable contract is [audio_bank.schema.json](../formats/audio_bank.schema.json). The example [adaptive_music.bank.json](../formats/adaptive_music.bank.json) describes an exploration event with an `intensity` parameter and two generated audio layers.

IDs are stable public identifiers. Plugins should report an error for an unknown event, parameter, asset, or unsupported bank version rather than silently guessing.

## First runtime API

The first native runtime can expose this engine-neutral shape:

```text
LoadBank(path) -> BankHandle
CreateEvent(bank, eventId) -> EventHandle
SetParameter(event, parameterId, value)
Play(event)
Stop(event)
Release(event)
```

Unity C# and Unreal C++ wrappers should map to this API without changing the bank format.