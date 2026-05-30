# Decisions

## 0001: Use Forge 1.8.9

WolfTAS targets Minecraft Forge 1.8.9.

Implications:

- Java source should stay compatible with Java 8.
- The mod uses the legacy ForgeGradle 2.x toolchain.
- Gradle should be run through the checked-in Gradle 2.14.1 wrapper.
- On macOS ARM, Java 8 may be x86_64 and run through Rosetta; that is expected
  for this legacy toolchain.
- Disable Gradle native integration with `-Dorg.gradle.native=false` for modern
  macOS ARM compatibility.
- Modern Minecraft APIs and mappings should not be assumed.

## 0002: Use JSON Contracts Between Components

The mod, Python orchestrator, Mathematica scripts, and C++ solver exchange
versioned JSON payloads.

Rationale:

- Codex and humans can inspect fixtures cheaply.
- Component tests can run independently.
- Contract changes are explicit.
