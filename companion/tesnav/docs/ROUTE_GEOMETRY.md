# SDK route geometry (v23 / navassist 1.4.0)

The embedded AMap SDK supplies the selected path's `coordList`. AMap Auto's broadcast
source does not supply a complete route. Select **高德 SDK** in TesNav to use this
path; source selection uses the existing explicit UI and starts a new snapshot
session. It does not enable any vehicle feature or start navigation automatically.

This release adds route data, not a lane/branch decision engine. Existing navigation
snapshots, signing/pairing, source-readiness gates, lane decisions, signals, speed
ceilings and BSM vetoes remain separate. Geometry cannot refresh their timestamps
or grant control. On current older X-Pilot hosts, `navRoute` has no full map consumer;
publishing it does not add a C3 map screen or route recalculation service.

## Transport

Default discovery/UDP mode only. The phone first receives a normal v3 snapshot ACK
from a private IPv4 C3 address, then starts optional geometry IO in a separate worker.
Explicit HTTP snapshot overrides and legacy WebSocket are not extended by this new
transport (legacy WebSocket retains its existing route export).

UDP port 4213 uses separate `route_geometry_hello` and `route_geometry_chunk`
messages, schemaVersion 1. Both contain sessionId, routeRevision, and routeId
(lowercase SHA-256 of the complete UTF-8 JSON body). Chunks add chunkIndex (zero
based), chunkCount and base64 payload. Each payload is at most 2048 bytes; at most
64 chunks / 128 KiB. Packets are at most 4096 bytes. The receiver binds to the
already accepted snapshot source address, fresh session and revision. UDP ACKs
prove delivery, not authentication. The route is private LAN data, never broadcast.

The body contains exactly schemaVersion, coordinateSystem, pathId,
sourcePointCount, sourcePointIndices, totalDistanceMeters, toleranceMeters, points.
Points are `[latitude,longitude]`, explicitly GCJ-02 from AMap. Source indices are
strictly increasing and preserve both original endpoints. Up to 50,000 source
points simplify to at most 4096 points using RDP, capped at 5 m in the local planar
projection. Overlarge/invalid paths disable this optional export; the sender never
silently increases the tolerance. This is not a global survey-error guarantee.

The ACK contains exactly messageType `route_geometry_ack`, schemaVersion 1,
sessionId, routeRevision, routeId, chunkIndex (-1 for hello), accepted and complete.
Only a strict matching ACK advances the transfer. There are at most three attempts
per packet, 160 ms pacing and a 12 s transfer budget. A completed route sends only
a small hello at most every 10 s; a receiver restart triggers retransmission.
An old/silent host receives only bounded hello probes, not chunks. Cancellation,
source/session changes, route end and ordinary snapshot delivery failure stop the
worker. Receiver assembly expires after 15 s and geometry has its own rate budget.

## Vehicle publication and limits

The integrated plugin declares `source:route` and `msg:nav.route`. It deliberately
does not take `source:map`, so the existing OSM process remains available. Under
`ExtNavAssistEnabled` and route ownership, a fully checked route becomes the existing
`navRoute` message and bounded status `nav.route`; both are display/data only.
Conversion runs once on a single background worker, outside both the snapshot receiver and navigation loop. Cache reads never
wait on conversion. GCJ-02 is approximately inverted to WGS-84 before publication;
`navRoute` itself uses Float32 coordinates and cannot label coordinate systems.
Mode end/recalculation, new session/revision, stale snapshots or disabling the
plugin clears the published line. Route publisher errors cannot stop navigation.

Benefits: actual route shape, preserved bends and source-point indices for future
progress matching, consistent updates after reroutes, low average LAN traffic.
Costs: SDK map/network/key availability, occasional bounded route bursts, more
protocol/cache state, coordinate approximation and privacy of destination/route.
Parallel roads, stacked roads and absolute lane identity still need independent
evidence. This release does not claim those decisions or road validation.

Reference patterns: [openpilot navd](https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/navigation/navd.py)
separates instructions from route geometry; [AMap Android navigation SDK](https://a.amap.com/lbs/static/unzip/Android_Navi_Doc/com/amap/api/navi/model/AMapNaviPath.html)
exposes the selected navigation path. No official mapsd renderer or camera capture
pipeline is added to this C3.
