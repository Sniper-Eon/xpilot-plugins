"""Builds the lane_number_v3 frame from runtime.py locals (draft, not installed)."""
from __future__ import annotations


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def frame_from_runtime(*, now_ns, nav, topology, candidate, road_total, geo, lane_offset_m,
                       lane_width_m, lane_sigma_m, speed_mps, meta, car, road_kind=""):
    lanes = list(nav.get("lanes") or ())
    rec = tuple(int(l["index"]) for l in lanes
                if l.get("recommended") is True and isinstance(l.get("index"), int))
    fnav = topology.get("fnav") or {}
    lcs = str(getattr(meta, "laneChangeState", "")) if meta is not None else ""
    ldir = str(getattr(meta, "laneChangeDirection", "")).lower() if meta is not None else ""
    lc_dir = "left" if "left" in ldir else ("right" if "right" in ldir else None)
    if lc_dir is None and car is not None:
        lb, rb = bool(getattr(car, "leftBlinker", False)), bool(getattr(car, "rightBlinker", False))
        lc_dir = "left" if (lb and not rb) else ("right" if (rb and not lb) else None)
    cand = candidate or {}
    num = _int(cand.get("laneNumber")) if cand.get("valid") else None
    cnt = _int(cand.get("laneCount")) if cand.get("valid") else None
    return dict(
        t=now_ns / 1e9, speed=float(speed_mps or 0.0), road_kind=road_kind or "",
        n_amap=len(lanes), rec=rec, maneuver=str(nav.get("maneuver") or "none"),
        dist_m=nav.get("distanceM") if nav.get("routeActive", True) else None,
        event_id=str(nav.get("maneuverEventId") or ""), road_total=road_total,
        fused_value=_int((geo or {}).get("value")), fused_conf=float((geo or {}).get("confidence") or 0.0),
        fused_err=bool(fnav.get("err")), fused_side_added=_int(fnav.get("side_added")),
        gps_off_m=lane_offset_m, gps_hacc_m=lane_sigma_m, lane_width_m=lane_width_m, dr_lat=None,
        mnn_num=num, mnn_cnt=cnt,
        cam_ego=_int(topology.get("egoLaneIndexFromLeft")), cam_visible=_int(topology.get("visibleLaneCount")) or 0,
        edge_l_anc=bool(topology.get("leftCarriagewayAnchored") or topology.get("leftRoadEdge")),
        edge_r_anc=bool(topology.get("rightCarriagewayAnchored") or topology.get("rightRoadEdge")),
        lcs=lcs, lc_dir=lc_dir)
