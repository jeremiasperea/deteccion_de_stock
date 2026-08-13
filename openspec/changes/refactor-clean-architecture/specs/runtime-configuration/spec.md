# Runtime Configuration Specification

## Purpose

Defines how the application resolves confidence threshold, model weights path, export directory, and queue bounds independent of the process's current working directory or a single OS layout. The resolution mechanism (env vars, file, or CLI) is decided in `sdd-design`; this spec defines only the required resolved behavior.

## Requirements

### Requirement: Package-Relative Model Weights Resolution

Model weights MUST resolve relative to the installed package, not the process's current working directory. (FT8 partial; replaces FIX 9)

#### Scenario: Resolution independent of cwd
- GIVEN the application is launched from a directory other than the project root
- WHEN the detector loads model weights
- THEN resolution MUST succeed using a package-relative or explicitly configured path, not an implicit cwd-relative one

### Requirement: Configurable Confidence Threshold

The confidence threshold MUST be configurable, defaulting to `0.4` when unset. (PRESERVE 2, configuration leg)

#### Scenario: Explicit configuration overrides default
- GIVEN a confidence threshold is supplied through configuration
- WHEN the application resolves its runtime configuration
- THEN the active threshold MUST equal the configured value, not `0.4`

### Requirement: Configurable Export Directory

The export directory MUST be resolvable through configuration, with a documented default that works outside `~/Desktop`. (FT8 partial; replaces FIX 5)

#### Scenario: Default works cross-platform
- GIVEN no export directory is configured
- WHEN the default is resolved
- THEN it MUST reference a path that exists or can be created without depending on a Windows-only, English-locale `~/Desktop`

### Requirement: Configurable Queue Bounds

The UI event queue's capacity bound MUST be configurable rather than hardcoded. (supports FT3)

#### Scenario: Configured bound is honored
- GIVEN a queue capacity is supplied through configuration
- WHEN the event queue is constructed
- THEN it MUST enforce that capacity

### Requirement: Pinned Flet Dependency Compatible With Target Image API

The resolved Flet dependency version MUST support the `Image.src_bytes` property used by the presentation layer. (replaces FIX 10)

#### Scenario: Installed version supports src_bytes
- GIVEN the project's pinned dependency floor
- WHEN the installed Flet version is checked
- THEN it MUST be at or above the version that documents `src_bytes` support
