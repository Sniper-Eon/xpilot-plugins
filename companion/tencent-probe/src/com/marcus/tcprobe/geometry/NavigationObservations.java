package com.marcus.tcprobe.geometry;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;

/** Latest immutable callback observations. Exporting never changes source clocks.
 * This raw bridge does not assert mode, matching or ego-lane numbering semantics.
 */
public final class NavigationObservations {
    private final String session;
    private final LinkedHashMap<String,Object> events=new LinkedHashMap<>();
    private final LinkedHashSet<String> ended=new LinkedHashSet<>();
    private String route="";
    private long sequence,revision;
    private boolean released;
    private Map<String,Object> location,hd;
    public NavigationObservations(String session){this.session=session;}
    private static Map<String,Object> observation(Map<String,Object> values,long wall,long mono) {
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("observedWallMs",wall);out.put("observedMonoMs",mono);
        out.put("values",new LinkedHashMap<>(values));return out;
    }
    public synchronized void navigation(String kind,String incoming,Map<String,Object> values,long wall,long mono) {
        String id=incoming==null?"":incoming;
        boolean start=kind.equals("StartNav"),replacement=kind.equals("NavRouteUpdate");
        if(ended.contains(id)&&!start)return;
        if(start||replacement||route.isEmpty()) {
            if(!route.equals(id)||start) {
                events.clear();revision++;
                if(!route.isEmpty())ended.add(route);
                if(start)ended.remove(id);
                route=id;released=false;
                while(ended.size()>16)ended.remove(ended.iterator().next());
            }
        } else if(!route.equals(id))return;
        if(released&&!start)return;
        if(kind.equals("Release")) {
            events.clear();released=true;
            if(!route.isEmpty())ended.add(route);
        }
        events.put(kind,observation(values,wall,mono));sequence++;
        while(events.size()>32)events.remove(events.keySet().iterator().next());
    }
    public synchronized void location(String kind,Map<String,Object> values,long wall,long mono) {
        if(kind.equals("hd"))hd=observation(values,wall,mono);
        else location=observation(values,wall,mono);
        sequence++;
    }
    public synchronized Map<String,Object> snapshot(long exportMono) {
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("schemaVersion",1);out.put("messageType","tencent_legacy_observations");
        out.put("sourceSessionId",session);out.put("sequence",sequence);
        out.put("exportMonoMs",exportMono);out.put("routeRevision",revision);out.put("routeId",route);
        out.put("released",released);out.put("events",new LinkedHashMap<>(events));
        out.put("location",location);out.put("hd",hd);
        out.put("navigationMode","unknown");out.put("coordinateSystem","unknown_raw");
        out.put("egoLaneIndexBase","unknown");out.put("controlUsable",false);
        out.put("controlBlockReason","mode_route_progress_and_lane_semantics_not_validated");
        return out;
    }
}
