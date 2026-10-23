# ADS-B Attack Generation Methodology

This document maps the selected paper to the implementation plan for this
repository. It is intentionally conservative: methods are marked as documented
only when they are explicitly visible from the accessible article text. Missing
formula details are not filled in by guesswork.

## Selected Paper

Li, T., Wang, B., Shang, F., Tian, J., & Cao, K. (2020). "Threat model and
construction strategy on ADS-B attack data." IET Information Security, 14(5),
542-552. https://doi.org/10.1049/iet-ifs.2018.5635

Publisher page: https://ietresearch.onlinelibrary.wiley.com/doi/abs/10.1049/iet-ifs.2018.5635

Access status during this project:

- The Wiley abstract page and indexed full-text excerpts were accessible.
- The direct PDF download was blocked by a Cloudflare challenge from the local
  command environment.
- Several mathematical expressions in the accessible text render as equation
  images and are not available as plain text. Therefore, equations (2), (3),
  (10), (11), (12), and (13) cannot be reproduced exactly from the currently
  accessible material.

## Repository Context

Current immutable project artifacts:

- Raw OpenSky CSV files: `data/raw/`
- Cleaned source table: `data/processed/opensky_clean_v1.parquet`
- Original sequence baseline: `data/sequences/`
- Validated v2 sequence dataset: `data/sequences_v2/`
- Centralized LSTM baseline: `results/centralized_lstm/`

Any paper-grounded attack-generation implementation must write to a new
versioned location, such as `data/attack_generation_v3/`, and must not overwrite
the artifacts above.

## Paper-To-Implementation Mapping

| Paper citation and DOI/URL | Attack type and threat model | Original data source | Fields modified | Attack-generation procedure | Parameters and ranges specified by the paper | Attack duration and temporal behaviour | Label-generation rules | Original validation procedure | Implementation in this repository | Deviations and justification | Limitations and reproducibility status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Li et al. (2020), https://doi.org/10.1049/iet-ifs.2018.5635 | Data manipulation attack. Attacker tampers GNSS, transmission data, or information systems so decoded ADS-B state attributes are wrong. The paper distinguishes partial attribute manipulation from whole-message corruption. | Real ADS-B data collected from open sites or devices; paper simulation uses real ADS-B data recoded every 10 s. | Paper simulation explicitly modifies latitude, longitude, and altitude for manipulation attacks. It also discusses possible attributes including location, velocity, and heading. | Six manipulation variants are documented: constant deviation, random deviation, increased deviation, non-linear/square deviation, zoom/static magnification, and changeable time-varying deviation. | Paper states target proportion is generally limited to small scale and mentions a basic proportion in [0, 0.1]. It states manipulation attack data accounts for 0.05% in the simulation. It states random deviation uses Gaussian-generated deviations. It states amplitude should be based on historical ADS-B statistics. Exact formulas and numeric constants are not fully recoverable from accessible equation images. | Manipulation occurs over selected attack windows. Increased/changeable deviations vary with time; constant deviations maintain fixed offsets; random deviations vary by sample. Exact time-window selection details are not fully available. | Paper says labels are added for normal and constructed attack data to support evaluation, but labels should not be used for unsupervised training. | Paper validates by simulation analysis with real ADS-B data and visual/metric comparison of attack effects, efficiency, and stealth. Exact code/data not available. | Candidate v3 implementation can support documented manipulation variants on observed `lat`, `lon`, `baroaltitude`, and `geoaltitude` only when fields are present. It should store original and modified values, interval, parameters, and source row identifiers. | OpenSky state vectors provide decoded state attributes, not raw 112-bit ADS-B messages. Exact paper formulas for amplitude/efficiency metrics are inaccessible as text, so amplitude rules must be declared as implementation choices unless the PDF is supplied. | Partially reproducible. Threat model and attack families are documented; exact parameter formulas are not fully reproducible from accessible material. |
| Li et al. (2020), https://doi.org/10.1049/iet-ifs.2018.5635 | Ghost flight injection attack. Attacker injects false aircraft into an airspace to degrade situation awareness. | Real ADS-B data; paper discusses mixing attack data with normal data. | New/fake flight tracks, including position/track attributes. | Paper documents three ghost patterns: copied ghost, created ghost, and random ghost. Random ghost adds random deviations to selected flights to construct ghost flights. Mixing strategy uses a selected existing flight as a center and injects fake nodes in neighbour areas. | Exact numeric offsets and counts for fake nodes are not recoverable from accessible text. Target selection may use random, area, or neighbour selection. | Continuous-time cycles are mentioned for hot-point mixture; exact duration not recoverable from accessible text. | Constructed ghost records are labelled as attack data for evaluation. | Simulation plots compare ghost-injected data with normal data. | Defer implementation unless the v3 objective includes injected new aircraft records. This repository currently works with per-aircraft trajectories and sequence windows; injecting new aircraft requires a row-level dataset first, not direct mutation of existing v2 arrays. | Available OpenSky data has real `icao24` values; fake IDs and mixing policy would be implementation choices unless the paper details are supplied. | Not currently reproducible with high fidelity from accessible material. |
| Li et al. (2020), https://doi.org/10.1049/iet-ifs.2018.5635 | Data replay attack. Historical data replaces newly received data, causing time delay in flight status. This is a data-layer stale-track simulation, not necessarily RF/message-level replay. | Real ADS-B trajectory data. | Historical state records replace current records for a selected flight. | Paper states historical data is used to replace current data with a specific time delay. | Paper simulation sets delay time to 300 s. | Temporal behaviour is delayed replay of historical trajectory values. | Replayed records are labelled as attack data for evaluation. | Paper visualises original and replayed tracks and describes the delay effect. | Candidate v3 implementation can replace current observations with observations from the same aircraft/segment approximately 300 s earlier where available. It must store source row, replay source row, delay, and fields replaced. | OpenSky data has 10 s sampling in this project, but gaps and missing fields vary. Replay can only be performed within continuous aircraft/segment histories with sufficient lookback. This should be called stale-track or data-layer replay, not full ADS-B message replay. | Reproducible for the documented 300 s delay when source history exists; message-level replay is not reproduced. |
| Li et al. (2020), https://doi.org/10.1049/iet-ifs.2018.5635 | DoS/message blocking attack. Attacker blocks current ADS-B data in time windows, causing missing data/disappearance from surveillance. | Real ADS-B trajectory data. | Records in selected time windows are removed or converted to missing data. | Accessible paper excerpts describe DoS in terms of attack target proportion and blocking current data. Related indexed text from follow-on work by the same research line describes configuring data in the attack time window as missing data. | Exact DoS parameters for Li et al. are not available in accessible text. | Blocking occurs over specific time windows. | Blocked/missing records are labelled as attack data for evaluation if represented as examples. | Simulation/evaluation discusses attack detection and attack target detection, but exact DoS simulation section is not accessible. | Candidate v3 implementation should be deferred unless the exact paper details are supplied. A conservative compatible implementation would mark selected windows as missing rather than deleting rows, but that is an engineering decision. | Deleting rows can break sequence alignment; marking fields missing may introduce an easy missingness shortcut, already observed in v2 diagnostics. | Not reproducible from accessible Li et al. text alone. |

## Documented Method Components

The accessible paper text explicitly supports these concepts:

- ADS-B attack data is difficult to collect in real environments, motivating
  synthetic construction from normal ADS-B data.
- ADS-B records are treated as spatio-temporal sequential data.
- Attack construction should include target selection, key parameter
  determination, attack-effect simulation, mixture with normal ADS-B data, and
  persistent labelled datasets for evaluation.
- Target selection strategies include random selection, area selection, and
  neighbour selection.
- Common parameters include attack target percentage, attack value amplitude,
  and additional Gaussian noise.
- Four primary attack categories are considered: data manipulation, ghost
  flight injection, data replay, and DoS.
- The simulation uses real ADS-B data with fields including timestamp, ICAO
  identifier, latitude, longitude, heading, velocity, vertical rate, warning
  information, and altitude.
- For manipulation attacks, the simulation modifies latitude, longitude, and
  altitude, including constant, random, increased, non-linear, zoom, and
  changeable deviations.
- Replay is described as replacing current data with historical data; the
  visible simulation text states a 300 s delay.

## Implementation Decisions Required By This Repository

These are not paper claims. They are engineering choices required because the
available project data differs from a full ADS-B message stream and because
some paper details are unavailable:

- Work from decoded OpenSky state vectors, not raw 112-bit ADS-B messages.
- Use `icao24`, `segment_id`, and `time` to preserve aircraft/segment isolation.
- Generate row-level attacked observations first, then derive sequence windows.
- Use aircraft-level train/validation/test split before window generation.
- Fit imputation/scaling on training aircraft only.
- Keep missingness indicators binary.
- Store original and modified values for every modified observation.
- Store attack parameter records and rejected-candidate records.
- Validate physical plausibility with derived trajectory checks, not merely
  numerical deviation magnitude.

## Proposed V3 Scope

The safest initial v3 scope is:

1. Normal class.
2. Data manipulation attacks on observed latitude/longitude/altitude:
   constant deviation, random Gaussian deviation, and gradual/increased
   deviation.
3. Data-layer replay/stale-track attack with 300 s delay where same-aircraft
   historical data exists.

Ghost injection and DoS should be documented but deferred unless the user
provides the full paper PDF or accepts repository-specific engineering choices.

## Validation Requirements For V3

For every generated example, validation should compute where supported:

- Source row mapping and modified row mapping.
- Attack interval bounds and duration.
- Geodesic distance between consecutive positions.
- Implied groundspeed from position and elapsed time.
- Difference between implied and reported velocity.
- Velocity-change rates and acceleration proxies.
- Heading and turn-rate consistency.
- Vertical rate from altitude and time.
- Temporal continuity before, during, and after the attack.
- Missing-field fractions before and after manipulation.
- Invalid, clipped, rejected, or unavailable candidate counts.

Checks that are limited or impossible must be recorded in the manifest. For
example, raw-message authentication, RF replay fidelity, received signal
strength, Doppler shift, and bit-level message integrity cannot be evaluated
from the current OpenSky state-vector CSVs.

## Current Stop/Go Status

Status: proceed only with a documented and limited v3 plan, not a full claimed
paper reproduction.

Reason: the paper is identified, but several mathematical details and exact
simulation parameters are unavailable from the accessible text because the PDF
download is blocked and equations render as images. A v3 implementation can be
paper-grounded in attack categories, target-selection concepts, replay delay,
and manipulation families, but any numeric ranges not visible in the text must
be marked as implementation choices.

## New-source cadence compatibility

The HDD archives in `data/hdd_data` are a separate source from the two-hour
2017 cleaned table used for the accepted seed-42 dataset. A sampled archive
README describes roughly 1 Hz state vectors, but cadence and schema consistency
across all hours are not yet measured. The current assembler/window conventions
were validated around roughly 10-second rows. Do not apply them to HDD data
unchanged. First complete the read-only archive audit and follow the cadence
gate in `docs/phase3_hdd_model_plan.md`; time-based semantics or deterministic
resampling must be specified and tested before attack generation.
