# Tesla Map Data (`tesla_map`)

Read-only tile for Tesla's own map frame, `0x238 UI_driverAssistMapData`, on the **vehicle** bus. The card plugin
decodes it, publishes a small JSON snapshot and the tile shows map limit, road class, next branch and lane rejects.
No claims, no CAN sends, no control output.

## Not the scroll wheel

`0x238` exists twice on a Model Y:

| source | frame | meaning |
|---|---|---|
| 1 `CANBUS.vehicle` | `UI_driverAssistMapData` | map data (this plugin) |
| 2 `CANBUS.autopilot_party` | `STW_ACTN_RQ` | right scroll wheel / `DTR_Dist_Rq` (`tn_long`) |

The decoder accepts only source 1, so the wheel frame can never be read as map data.

## What the tile shows

One tile, `small`/`medium`/`wide`, onroad only, `Tesla Map`:

```
MAP 60            limit code in the car's display unit; "!" = map and fused limit conflict
HWY C1 EXIT 250 R controlled access / road class, next branch distance and off-ramp side
SP 60 OK          the limit sunnypilot already resolved; "-15" = map is lower, "NO MAP" = map missing
REJ L AS          the car rejects the left lane and Autosteer here
```

`MAP SNA` means no frame for 5 s (or the plugin was just enabled). `MAP UNL` is code 30 (unlimited); `MAP 60 ADV`
is an advisory/dependent/bumps limit, not a hard one.

## Signals

Layout: opendbc `tesla_modely_hw4_perception.dbc`, `BO_ 568`, 8 bytes, Intel. Enumerations: tesLAX Model 3 DBC
`VAL_ 568`.

| signal | bit | use |
|---|---|---|
| `UI_mapSpeedLimit` | 8\|5 | code, see below |
| `UI_mapSpeedUnits` | 7\|1 | 0 mph, 1 kph |
| `UI_mapSpeedLimitType` | 13\|3 | 1 REGULAR, 2 ADVISORY, 3 DEPENDENT, 4 BUMPS, 7 SNA |
| `UI_mapSpeedLimitDependency` | 0\|3 | NONE, SCHOOL, RAIN, SNOW, TIME, SEASON, LANE, SNA |
| `UI_roadClass` | 3\|3 | 1 major .. 6 minor, 0 SNA |
| `UI_controlledAccess` | 37\|1 | closed road / highway |
| `UI_gpsRoadMatch` | 28\|1 | the car matched GPS to the road; used as a trust gate |
| `UI_navRouteActive` | 29\|1 | the car has a route |
| `UI_nextBranchDist` | 32\|5 | ×10 m, **31 = SNA**, so 0..300 m are real |
| `UI_nextBranchLeftOffRamp` / `RightOffRamp` | 38 / 39 | branch side |
| `UI_rejectLeftLane` / `RightLane` / `LeftFreeSpace` / `RightFreeSpace` | 40 / 41 / 44 / 45 | map rejects that side |
| `UI_rejectAutosteer` / `rejectHandsOn` / `rejectNav` / `rejectHPP` | 46 / 47 / 43 / 42 | other rejects |
| `UI_countryCode` | 16\|10 | raw code (0 unknown, 1023 SNA) |
| `UI_streetCount`, `UI_inSuperchargerGeofence`, `UI_acceptBottsDots`, `UI_autosteerRestricted`, `UI_pmmEnabled`, `UI_scaEnabled`, parking flags | 26, 6, 48, 49, 50, 51, 30, 31 | carried in the snapshot, not shown on the tile |

Speed limit codes are **upper bounds** ("LESS_OR_EQ_60"), in `UI_mapSpeedUnits`:

```
1=5  2=7  3=10 4=15 5=20 6=25 7=30 8=35 9=40 10=45 11=50 12=55 13=60 14=65 15=70
16=75 17=80 18=85 19=90 20=95 21=100 22=105 23=110 24=115 25=120 26=130 27=140 28=150 29=160
30 = unlimited, 31 / 0 = SNA / unknown
```

The table comes from the tesLAX DBC `VAL_ 568` and agrees with `tesla_can_visualization.py`. It is not car-verified in
this branch; if your car shows a constant offset, fix `SPEED_LIMIT` in `decode.py` and the tests follow.

## Comparison rules (`compare.py`)

The car's fused limit (`carStateSP.speedLimit`, from `DAS_fusedSpeedLimit`) and the map limit are compared in the map
frame's unit:

- difference of one step (5 units) or less: `AGREE` (the map code is an upper bound, so 60 vs 65 is not a conflict).
  This tolerance also absorbs the usual 5-unit offset between the map code table and `DAS_fusedSpeedLimit`'s factor 5
  (`code 25` is "<=120" while the fused raw 25 reads 125);
- two steps or more: `MAP_HIGHER` / `MAP_LOWER`, and `conflict` after 3 s **only if** the map frame is REGULAR,
  GPS-matched and fresh;
- missing side: `SP_ONLY`, `MAP_ONLY` or `NONE`.

A conflict clears as soon as the two agree and the 3 s hold restarts from zero. Nothing is actuated.

## Params and local checks

`ExtTeslaMap` (BOOL, default `0`) enables the plugin. `ExtTeslaMapState` (JSON) is the card → tile snapshot, schema v1.

```bash
X=/path/to/xpilot
cd xpilot-plugins
PYTHONPATH=$X:$X/opendbc_repo:$X/tinygrad_repo:$X/msgq_repo python3 -m pytest -q plugins/tesla_map
PYTHONPATH=$X:$X/opendbc_repo python3 -m plugins.tesla_map.demo
```

The demo packs frames with opendbc's `CANPacker` from the DBC, so it fails if the hand-written bit offsets drift.

## Not included

Control consumers are deliberately out of scope here (they need host hooks and their own claims):

- map-limit fallback or conflict pause for `auto_speed`;
- an "exit approaching" alert (`alert` claim, selfdrived);
- a lane-change veto from `UI_rejectLeftLane` / `RightLane` (`role:lane_change.policy`, already done by `navassist`
  from 0x238 + 0x39B).

A more precise map limit exists in `UI_driverAssistRoadSign` mux 3 (`UI_baseMapSpeedLimitMPS`, 0.25 m/s, 0x218 on the
HW4 DBC). It is not used because 0x238 is the frame this plugin targets; wire it in only after seeing it on the car.

Before a PR: bump `version`, run `python3 tools/build_index.py`, and commit `dist/` with `index.json`.
