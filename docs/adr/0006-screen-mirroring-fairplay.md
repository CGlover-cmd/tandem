# ADR-0006: Screen mirroring and FairPlay

- Status: Accepted (after Phase 0 Spike D)
- Date: 2026-10-21

## Context
Phase 8 is whole-screen, then single-window, screen mirroring to an AirPlay receiver. The
roadmap always marked it "feasibility-gated", and the risk register rated "FairPlay encryption
blocks mirroring" as high likelihood. Spike D checked it
([findings](../spikes/spike-d-mirroring.md)).

Spike D found:
- Receivers (the reference Apple TV, and UxPlay on the test Pi) advertise and accept screen
  mirroring.
- pyatv, the library the rest of the engine is built on, has no mirroring *sender*. It sends
  audio and plays media files/URLs, nothing more.
- The AirPlay mirroring video stream is encrypted with a key established through FairPlay (the
  `fp-setup` step). Open-source *receivers* implement FairPlay on the receive side using
  recovered key material; we are not aware of an open-source *sender*.

So shipping mirroring would require Tandem to perform FairPlay as a sender, which means
reverse-engineering Apple's content protection. The spike did not attempt this.

## Options
1. **Reverse-engineer / reimplement FairPlay as a sender** (including by decompiling an existing
   AirPlay implementation with a tool such as a Ghidra/IDA-based decompiler). Technically the
   only known way to mirror to an unmodified Apple TV. The existence of general-purpose
   reverse-engineering tooling does not change the calculus: for a public project, distributing
   code that circumvents a content-protection measure is a legal risk (US DMCA §1201
   anti-circumvention and equivalents elsewhere; interop exceptions are narrow and do not
   clearly cover redistributing the result), it clashes with the project's stated values, and it
   depends on recovered secrets that break on Apple updates. We decline this route whether or
   not a decompiler makes it easier.
2. **Shelve mirroring.** Treat Phase 8 as no-go for now. Keep every FairPlay-free feature
   (control, audio out, multi-output, sending media files and URLs) that makes up the alpha and
   most of the value.
3. **Wait for a legitimate path.** Keep the door open for a sanctioned route if one appears:
   an officially documented API, a receiver that takes an unprotected stream, or an
   extend-the-desktop route via a signed virtual-display driver feeding a non-AirPlay path.

## Decision
Options 2 + 3: **do not implement or bypass FairPlay; shelve Phase 8 mirroring, and revisit
only if a legitimate path appears.** We will not add a reverse-engineered FairPlay sender to a
public project.

Concretely:
- Phase 8 is parked. The roadmap keeps it listed but marked blocked by this ADR.
- Spike E (NVENC H.264 encode latency) is still worth doing on its own: the encode pipeline is
  reusable work and independent of this decision.
- The alpha and v1.0 scope lose nothing else; every other feature is FairPlay-free.

## Consequences
- Tandem will not mirror your screen to an Apple TV in v1.0. The README and feature list must
  say so plainly, so users aren't surprised.
- The project avoids both the legal exposure and the maintenance churn of recovered FairPlay
  secrets.
- If a legitimate path opens later, mirroring can be reopened as a fresh spike; the encoder
  work from Spike E would carry over.

## Addendum (2026-11-10): open-source senders exist; Cast screen instead

Two open-source mirroring *senders* have appeared since Spike D:
- **lcd1232/pyatv** (a pyatv fork, its PR #1, MIT): a pure-Python FairPlay SAP sender
  handshake (`pyatv/protocols/airplay/mirror/fairplay_sap/`) and a mirroring session, reported
  working on an Apple TV 4K with tvOS 27. Registering it with a TV takes a one-time PIN.
- **omarroth/doubletake** (Go, LGPL-3.0+): a mirroring sender for Linux.

Both still implement FairPlay. That is the step this ADR declined, and their existence doesn't
change the reasons: the legal exposure of distributing it, the project's values, and fixed key
material that Apple can break with an update. The fork's FairPlay files carry no licence
header of their own (only the repository's MIT licence), and one notes that it computes the
same values as playfair's `hand_garble.c`, which is GPL-3.0. So their provenance is not clean
enough to bundle either.

The maintainer chose option A of the 2026-11-10 decision doc:
- **Tandem still ships no FairPlay code.** Nothing in this repository performs or bypasses
  FairPlay, and Tandem's installer doesn't download anything that does.
- **Cast screen, built now (FairPlay-free).** Tandem captures the screen, encodes it to H.264
  with AAC sound, writes it as a live HLS stream with short segments, serves it from the PC on
  the home network, and asks the Apple TV to play that address. This uses the same "play this
  URL" request as Send to TV (Phase 7, ADR-0015). The TV plays it as an ordinary video, so it
  runs a few seconds behind: fine for slides, photos, a video or a shared browser tab, but not
  for games or typing. Spike I measures the lag ([findings](../spikes/spike-i-cast.md)).
- **Real, low-lag mirroring later only as a user-installed add-on**, the same pattern as the
  virtual audio driver in ADR-0005: the user installs a third-party sender themselves, and
  Tandem finds it and hands it the work. Tandem doesn't bundle it, download it or link to a
  download from inside the app. Spike J is a private test of the pyatv fork to see whether
  such an add-on is worth designing ([findings](../spikes/spike-j-mirror-addon.md)).
