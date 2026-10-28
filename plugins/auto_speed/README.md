
## Map conflict guard (1.2.0)

An independently packaged read-only VEH map decoder compares fresh regular,
unconditional, road-matched limits against the current carStateSP fused limit in
consistent units. A continuous disagreement of at least two 5-unit steps for 3 s blocks
new upward wheel ticks. It does not replace the fused target, create a lower target,
clear driver override or change Panda rules. Missing/conditional/stale map data does
not create a conflict. No dependency on the Tesla Map display plugin or its switch.
