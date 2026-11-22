"""Raw frame dict -> Observation -> lane filters. Shared by replay and tests.

Frame schema (one JSON object per line, see README):
  t, gps{latitude,longitude (WGS-84),horizontalAccuracy,bearingDeg,speed,flags},
  speed (vEgo m/s), yaw_rate_dps, mnn{leftClass,rightClass}, model{visibleLaneCount,
  egoLaneIndexFromLeft,leftRoadEdge,rightRoadEdge}, lines{left,right} (Tesla codes),
  lane_change ('left'/'right'/null), nav{road_lanes, junction{id,distance_m,lanes[],added_left}},
  truth (optional ground-truth lane, 1..N in the active numbering).
"""
from __future__ import annotations

from . import baselines
from .announce import Announcer, LaneSpec
from .deadreckon import LateralDeadReckoner
from .gpsjump import GpsJumpDetector
from .geo import Route
from .hmm import FilterConfig, LaneFilter, Observation
from .sources import ADAPTERS

JUNCTION_SWITCH_M = 250.0
DEDUPE_S = 5.0
DEDUPE_GPS_S = 8.0   # the GPS step is confirmed only ~5-6 s after the manoeuvre


class Pipeline:
  def __init__(self, route_points_gcj, cfg: FilterConfig | None = None, source="ublox",
               use_gps=True, use_vision=True, use_dr=True, announce=True, use_gps_jump=False):
    self.route = Route(route_points_gcj) if route_points_gcj else None
    self.cfg = cfg or FilterConfig()
    self.filter = LaneFilter(self.cfg)
    self.adapter = ADAPTERS[source]
    self.source = source
    self.use_gps, self.use_vision, self.use_dr = use_gps, use_vision, use_dr
    self.dr = LateralDeadReckoner(self.cfg.lane_width_m)
    self.gps_jump = GpsJumpDetector() if use_gps_jump else None
    self.announcer = Announcer() if announce else None
    self.s = None
    self.route_bearing = None
    self._last_event = None

  def observation(self, fr: dict) -> Observation:
    nav = fr.get("nav") or {}
    road_n = int(nav.get("road_lanes") or 0)
    j = nav.get("junction") or None
    jn = jd = ja = None
    if j and j.get("lanes") and j.get("distance_m") is not None and j["distance_m"] <= JUNCTION_SWITCH_M:
      jn, jd, ja = len(j["lanes"]), float(j["distance_m"]), j.get("added_left")
    ob = Observation(t=float(fr["t"]), road_lanes=road_n, junction_lanes=jn,
                     junction_added_left=ja, junction_distance_m=jd)
    # Amap recommended lanes in the active numbering (1-based). Near a junction they come
    # from the junction lane list; on the open road from nav.road_recommended if present.
    if jn is not None:
      rec = tuple(int(l["index"]) for l in j["lanes"] if l.get("recommended") and isinstance(l.get("index"), int))
    else:
      rec = tuple(int(k) for k in (nav.get("road_recommended") or ()) if isinstance(k, int))
    ob.recommended = rec or None
    if jn is not None:
      ob.maneuver = j.get("maneuver") or (j.get("id") and "junction")
      arrows = tuple(tuple(l.get("allowed") or ()) for l in j["lanes"])
      ob.lane_arrows = arrows if any(arrows) else None
    else:
      ob.maneuver = nav.get("maneuver")
    edges = fr.get("edges") or {}
    ob.left_edge_gap_m, ob.right_edge_gap_m = edges.get("left_gap_m"), edges.get("right_gap_m")
    if j and j.get("distance_m") is not None:
      ob.extras["junction_distance_any"] = float(j["distance_m"])
    gps = fr.get("gps")
    fix = self.adapter(dict(gps, t=fr["t"])) if gps else None
    if fix is not None and self.route is not None:
      p = self.route.project(fix.lat_gcj, fix.lon_gcj, fix.bearing_deg if (fix.speed_mps or 0) > 3 else None,
                             self.s)
      if p is not None:
        self.s, self.route_bearing = p.s, p.seg_bearing
        ob.gps_lateral_m, ob.gps_proj_dist_m, ob.gps_hacc_m = p.lateral, p.dist, fix.hacc_m
    # Live hook: the car already has a route-relative offset (right-positive).
    if fr.get("gps_lateral_m") is not None:
      ob.gps_lateral_m = fr["gps_lateral_m"]
      if fr.get("gps_hacc_m") is not None:
        ob.gps_hacc_m = fr["gps_hacc_m"]
      if fr.get("gps_proj_dist_m") is not None:
        ob.gps_proj_dist_m = fr["gps_proj_dist_m"]
    if fr.get("route_bearing") is not None:
      self.route_bearing = fr["route_bearing"]
    if self.use_vision:
      m = fr.get("mnn") or {}
      ob.mnn_left_class, ob.mnn_right_class = m.get("leftClass"), m.get("rightClass")
      mv = fr.get("model") or {}
      ob.model_visible, ob.model_ego0 = mv.get("visibleLaneCount"), mv.get("egoLaneIndexFromLeft")
      ob.model_left_edge, ob.model_right_edge = bool(mv.get("leftRoadEdge")), bool(mv.get("rightRoadEdge"))
      ln = fr.get("lines") or {}
      ob.left_line, ob.right_line = ln.get("left"), ln.get("right")
    car_event = fr.get("lane_change") if self.use_vision else None
    dr_event = None
    if self.use_dr and self.route_bearing is not None:
      dr_event = self.dr.update(ob.t, fr.get("speed"), self.route_bearing, fr.get("yaw_rate_dps"),
                                (gps or {}).get("bearingDeg"))
    gps_event = None
    if self.gps_jump is not None and self.use_gps:
      gps_event = self.gps_jump.update(ob.t, ob.gps_lateral_m, ob.gps_hacc_m,
                                       ob.junction_lanes if ob.junction_lanes is not None else ob.road_lanes)
    event = None
    # One physical lane change may be reported twice (lateral integrator first, the
    # car's lane-change state machine at completion). Count it once.
    for ev, kind in ((dr_event, "dr"), (car_event, "car"), (gps_event, "gps")):
      if ev is None:
        continue
      last = self._last_event
      # same direction, other source, within DEDUPE_S of the counted event -> same change.
      # (With only dr+car this is exactly the old rule; the kinds set lets a third source join.)
      win = DEDUPE_GPS_S if last and "gps" in (last[1] | {kind}) else DEDUPE_S
      if last and last[0] == ev and kind not in last[1] and ob.t - last[2] <= win:
        last[1].add(kind)
        if kind == "car":
          self.dr.lat = 0.0
        continue
      event = ev
      self._last_event = (ev, {kind}, ob.t)
      if kind == "car":
        self.dr.lat = 0.0
    ob.lane_change = event
    return ob

  def step(self, fr: dict) -> dict:
    ob = self.observation(fr)
    mnn_base = baselines.mnn_only(ob)
    gps_base = baselines.gps_only(ob, self.cfg.lane_width_m)
    if not self.use_gps:
      ob.gps_lateral_m = None
    res = self.filter.update(ob)
    res["obs"] = ob
    res["announcement"] = None
    nav = fr.get("nav") or {}
    j = nav.get("junction")
    if self.announcer is not None and j and j.get("lanes"):
      lanes = [LaneSpec(int(l["index"]), tuple(l.get("allowed") or ()), bool(l.get("recommended")))
               for l in j["lanes"]]
      in_junction_frame = ob.junction_lanes is not None
      ego = res.get("lane") if in_junction_frame else None
      if not in_junction_frame and res.get("lane") is not None:
        add = j.get("added_left")
        add = (len(lanes) - ob.road_lanes) if add is None else add
        ego = res["lane"] + add  # where the current lane leads into the junction layout
      res["announcement"] = self.announcer.update(j.get("id"), lanes, j.get("distance_m"), ego,
                                                  res.get("prob", 0.0))
    res["mnn_only"] = mnn_base
    res["gps_only"] = gps_base
    res["side"] = getattr(self.filter, "last_side", None)
    res["dr_lat"] = self.dr.lat
    res["dr_heading"] = self.dr.heading
    res["route_bearing"] = self.route_bearing
    return res
