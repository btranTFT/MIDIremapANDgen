# Improvement roadmap

This roadmap records follow-up work for the MIDI Remaster Lab architecture. The
current baseline and ML endpoints remain synchronous request/response APIs.

## Priority 1: reliability and responsiveness

### Asynchronous generation jobs and progress polling

- Add a job submission endpoint that returns a job identifier immediately.
- Persist job state and expose progress, stage, errors, and result URLs through a
  polling endpoint.
- Keep the existing synchronous endpoints during migration for compatibility.

### MIDI recording and capture

- Capture browser keyboard and Web MIDI note events into a timestamped event
  stream.
- Export a standards-compliant MIDI file while preserving tempo, channels, note
  durations, and sustain pedal events.
- Add explicit recording controls and permission/error states.

## Priority 2: product quality

### Exact SoundFont browser auditioning

- Provide a browser playback path that uses the selected SoundFont rather than
  the current oscillator preview.
- Clearly distinguish exact SoundFont auditioning from the existing browser
  audio preview.

### Latency benchmarking

- Measure upload, MIDI parsing, remapping, FluidSynth rendering, ML inference,
  encoding, and end-to-end latency by style and hardware profile.
- Publish repeatable benchmark fixtures and percentile summaries.

## Priority 3: evaluation and research

### Listening tests

- Run blinded A/B listening tests for baseline and ML outputs across console
  styles.
- Record preference, perceived authenticity, content preservation, and audio
  quality ratings.

### Usability evaluation

- Test onboarding, upload, advanced editing, browser MIDI permissions, and
  result downloads with representative users.
- Track task completion, errors, time on task, and qualitative feedback.

## Priority 4: repository maintenance

### Repository size reduction through Git LFS history migration

- Audit historical large binaries and confirm their ownership and licensing.
- Configure Git LFS migration filters and rehearse the rewrite on a mirror.
- Coordinate the history rewrite with all contributors before force-pushing,
  then verify clones and CI fetch LFS objects correctly.
