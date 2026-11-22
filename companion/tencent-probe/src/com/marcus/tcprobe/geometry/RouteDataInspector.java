package com.marcus.tcprobe.geometry;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Explicit read-only route queries. A route polyline or successful HD search is not verified lane geometry. */
public final class RouteDataInspector {
    private RouteDataInspector(){}
    private static Object call(Object target,String name,Class<?>[] types,Object... args) throws Exception {
        Method m=target.getClass().getMethod(name,types);m.setAccessible(true);return m.invoke(target,args);
    }
    private static Object call(Object target,String name) throws Exception {return call(target,name,new Class<?>[0]);}
    private static Object field(Object target,String name) {
        if(target==null)return null;
        try{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}catch(Throwable e){return null;}
    }
    private static int size(Object value){return value instanceof Collection?((Collection<?>)value).size():0;}
    private static String meaning(int value) {
        switch(value){
            case -1:return "hd_service_unsupported";case 0:return "hd_search_success";
            case 1:return "hd_not_requested";case 2:return "cloud_filter_level_1";
            case 3:return "cloud_filter_level_2";case 4:return "no_hd_data_or_shr_error";
            case 5:return "hd_region_discontinuous";case 6:return "hd_topology_poor";
            case 7:return "hd_generation_timeout";default:return "unknown_status";
        }
    }
    public static Map<String,Object> inspect(Object plan,String activeId) {
        Map<String,Object> out=new LinkedHashMap<>(),errors=new LinkedHashMap<>();
        out.put("controlUsable",false);out.put("physicalLaneGeometryVerified",false);
        out.put("sourceFreshness","route_snapshot_unknown_update_time");
        out.put("activeRouteId",activeId);out.put("routeMatched",false);out.put("hdStatus",null);
        out.put("errors",errors);
        if(plan==null){out.put("reason","plan_absent");return out;}
        if(activeId==null||activeId.isEmpty()){out.put("reason","active_route_unknown");return out;}
        try {
            Object ids=call(plan,"getRouteIdList");
            if(!(ids instanceof Collection)||!((Collection<?>)ids).contains(activeId)) {
                out.put("reason","active_route_not_in_plan");return out;
            }
            Object route=call(plan,"getRoute",new Class<?>[]{String.class},activeId);
            if(route==null||!activeId.equals(call(route,"getRouteId"))) {
                out.put("reason","route_identity_mismatch");return out;
            }
            out.put("routeMatched",true);out.put("reason","read_route_snapshot");
            try {
                Object status=call(plan,"getHDResStatusOnRoute",new Class<?>[]{String.class},activeId);
                if(status instanceof Number){out.put("hdStatus",status);out.put("hdStatusMeaning",meaning(((Number)status).intValue()));}
            }catch(Throwable e){errors.put("hdStatus",e.getClass().getSimpleName());}
            Object length=call(route,"getLength");out.put("routeLengthM",length);
            if(!(length instanceof Number)||((Number)length).intValue()<=0||((Number)length).intValue()>20000) {
                out.put("adDataSkipReason","route_length_limit");return out;
            }
            try {
                Object data=call(route,"getAdMapDataLinkList");
                if(!(data instanceof List)){out.put("adMapLinkCount",null);out.put("adDataSkipReason","links_not_list");return out;}
                List<?> links=(List<?>)data;int count=Math.min(links.size(),128);
                List<Object> subset=new ArrayList<>();long geometryPoints=0,groups=0,covers=0;
                for(int i=0;i<count;i++) {
                    Object link=links.get(i);subset.add(link);
                    Object detail=field(link,"routeLinkDetailAdExt"),lane=field(link,"apLaneInfo");
                    geometryPoints+=size(field(detail,"geometry"));
                    groups+=size(field(lane,"laneGroupInfoList"));covers+=size(field(lane,"coverLaneAreas"));
                }
                out.put("adMapLinkCount",links.size());out.put("exportedAdLinkCount",count);
                out.put("adDataTruncated",count<links.size());out.put("linkGeometryPointCount",geometryPoints);
                out.put("laneGroupInfoCount",groups);out.put("coverLaneAreaCount",covers);
                out.put("geometryMeaning","raw_ad_link_fields_not_verified_physical_lane_polylines");
                out.put("adMapLinks",subset);
            }catch(Throwable e){errors.put("adMapData",e.getClass().getSimpleName());}
        }catch(Throwable e){out.put("reason","query_failed");errors.put("query",e.getClass().getSimpleName());}
        return out;
    }
}
