# ADR 2 — The event lane exists only if arrival is genuinely event-shaped

**Status:** Accepted (2026-07-19)

## Decision

Keep Redpanda for the advisory/recall lane.

## Condition

The lane's existence was made conditional on measurement: combined arrival of
~3+ items/week justifies a broker; below that the lane collapses to a Dagster
sensor.

## Measurement

`phoms.extract.verify_arrival_rate`, trailing 30 days as of 2026-07-19:

| Source | Rate | Access |
|---|---|---|
| FDA recalls | 3.5/wk | RSS, truncated at 20 items — **floor** |
| CDC outbreaks | 0.5/wk | RSS |
| USDA FSIS | 0.9/wk | API, full 2,011-record archive — exact |
| **Combined** | **4.9/wk** | |

Gate passes.

## Honest caveats

- 4.9 is a lower bound from one 30-day window.
- FDA carries most of the total. Remove it and the lane does not clear.
- HAN contributes nothing to the rate — see ADR 3.

## Consequence

Redpanda is the only broker in the system, on the one lane that needs it. The
revision lane runs as a batch diff and does not touch it.
