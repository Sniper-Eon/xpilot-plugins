package com.marcus.tcprobe.geometry;

import android.os.SystemClock;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** Append observers to the legacy UI and existing LocationAPI singleton.
 * Only explicitly named data fields/getters are read. No engine is constructed,
 * no single listener is replaced, and no cached getter read becomes a callback.
 */
public final class LegacyNavigationTap {
    private static final String UI="com.tencent.map.ama.navigation.ui.views.data.NavViewDataManager";
    private static final NavigationObservations STORE=new NavigationObservations(UUID.randomUUID().toString());
    private static volatile Object uiManager,locationManager;
    private static Object uiObserver,locationObserver,hdObserver;
    private static volatile String error="not_attached";
    private LegacyNavigationTap(){}
    private static Object field(Object object,String name) {
        if(object==null)return null;
        return staticField(object.getClass(),object,name);
    }
    private static Object staticField(Class<?> type,Object object,String name) {
        try{Field f=type.getDeclaredField(name);f.setAccessible(true);return f.get(object);}
        catch(ReflectiveOperationException e){return null;}
    }
    private static Object get(Object object,String name) {
        if(object==null)return null;
        try{return object.getClass().getMethod(name).invoke(object);}
        catch(ReflectiveOperationException e){return null;}
    }
    private static String text(Object x){return x instanceof String?(String)x:"";}
    private static Object scalar(Object x) {
        if(x==null||x instanceof Number||x instanceof Boolean)return x;
        if(x instanceof Enum)return ((Enum<?>)x).name();
        if(x instanceof String)return ((String)x).substring(0,Math.min(512,((String)x).length()));
        return null;
    }
    private static Map<String,Object> fields(Object object,String... names) {
        Map<String,Object> out=new LinkedHashMap<>();
        for(String name:names)out.put(name,scalar(field(object,name)));
        return out;
    }
    private static Map<String,Object> getters(Object object,String... names) {
        Map<String,Object> out=new LinkedHashMap<>();
        for(String name:names)out.put(name,scalar(get(object,name)));
        return out;
    }
    private static Object objectMethod(Object proxy,Method method,Object[] args) {
        if(method.getName().equals("equals"))return args!=null&&args.length==1&&proxy==args[0];
        if(method.getName().equals("hashCode"))return System.identityHashCode(proxy);
        if(method.getName().equals("toString"))return "TcLegacyObserver";
        return null;
    }
    private static Object proxy(final Class<?> listener,final String channel) {
        return Proxy.newProxyInstance(listener.getClassLoader(),new Class<?>[]{listener},new InvocationHandler(){
            public Object invoke(Object self,Method method,Object[] args) {
                if(method.getDeclaringClass()==Object.class)return objectMethod(self,method,args);
                try {
                    if(channel.equals("ui")&&method.getName().equals("onNavViewDataChanged")&&args!=null&&args.length==2)
                        onNavigation(args[0],args[1]);
                    else if(channel.equals("location")&&method.getName().equals("onGetLocation")&&args!=null&&args.length==1)
                        onLocation(args[0]);
                    else if(channel.equals("hd")&&method.getName().equals("onGetHDLocation")&&args!=null&&args.length==1)
                        onHD(args[0]);
                }catch(Throwable e){error=e.getClass().getSimpleName();}
                return null;
            }
        });
    }
    /** Call on the app main thread. Re-register only our observer if UI.clear removed it. */
    public static synchronized void attach(ClassLoader loader) throws Exception {
        Class<?> type=Class.forName(UI,false,loader);
        Object manager=type.getField("INSTANCE").get(null);
        Object list=staticField(type,null,"observers");
        boolean present=list instanceof java.util.Collection&&((java.util.Collection<?>)list).contains(uiObserver);
        if(manager!=uiManager||!present) {
            Class<?> listener=Class.forName(UI+"$NavViewDataObserver",false,loader);
            if(uiObserver==null)uiObserver=proxy(listener,"ui");
            if(manager!=uiManager&&uiManager!=null)type.getMethod("removeObserver",listener).invoke(uiManager,uiObserver);
            type.getMethod("addObserver",listener).invoke(manager,uiObserver);uiManager=manager;
        }
        Class<?> loc=Class.forName("com.tencent.map.location.LocationAPI",false,loader);
        Object active=staticField(loc,null,"sInstance"); // never call factory getInstance().
        if(active!=locationManager) {
            Class<?> observer=Class.forName("com.tencent.map.location.LocationObserver",false,loader);
            Class<?> hd=Class.forName("com.tencent.map.location.HDLocationObserver",false,loader);
            if(locationManager!=null) {
                loc.getMethod("removeLocationObserver",observer).invoke(locationManager,locationObserver);
                loc.getMethod("removeHDLocationObserver",hd).invoke(locationManager,hdObserver);
            }
            locationManager=null;
            if(active!=null) {
                // SDK addHDLocationObserver silently ignores calls before its adapter exists.
                if(staticField(loc,active,"mAdapter")==null)throw new IllegalStateException("location_adapter_not_ready");
                if(locationObserver==null)locationObserver=proxy(observer,"location");
                if(hdObserver==null)hdObserver=proxy(hd,"hd");
                loc.getMethod("addLocationObserver",observer).invoke(active,locationObserver);
                try{loc.getMethod("addHDLocationObserver",hd).invoke(active,hdObserver);}
                catch(Exception e){loc.getMethod("removeLocationObserver",observer).invoke(active,locationObserver);throw e;}
                locationManager=active;
            }
        }
        error=active==null?"location_singleton_absent":"";
    }
    private static void onNavigation(Object event,Object data) {
        if(!(event instanceof Enum))return;
        String kind=((Enum<?>)event).name();
        Object guidance=field(data,"guidance"),status=field(data,"status"),route=field(guidance,"route");
        String routeId=text(get(route,"getRouteId"));
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("inNavigation",field(data,"isInNav"));
        // Each event copies only the section that the SDK says has changed.
        if(kind.equals("StartNav")||kind.equals("Release")||kind.equals("NavModeChange")||kind.equals("NavRouteUpdate")) {
            out.put("mode",fields(field(status,"navMode"),"sceneMode","state","navMode"));
            out.put("routeId",routeId);
        } else if(kind.equals("LeftDistance"))out.put("distance",fields(field(guidance,"leftTurnDistanceData"),"leftDistance"));
        else if(kind.equals("Direction"))out.put("direction",fields(field(guidance,"directionData"),"direction"));
        else if(kind.equals("EtaUpdate"))out.put("eta",fields(field(guidance,"etaData"),"leftDistance","leftTime"));
        else if(kind.equals("NowRoadName")||kind.equals("RoadName"))out.put("road",fields(field(guidance,"roadNameData"),"nowRoadName","roadName"));
        else if(kind.equals("LaneInfo")||kind.equals("LaneInfoVisible")) {
            Object laneView=field(guidance,"laneInfo");
            out.put("laneVisible",field(laneView,"isLaneShow"));
            out.put("laneInfo",fields(field(laneView,"laneInfo"),"arrow","flag","property","recommend","startIndex"));
        } else if(kind.equals("Speed"))out.put("speed",fields(field(guidance,"speedData"),"speed","limitSpeed"));
        else if(kind.equals("GPSInfo"))out.put("gps",fields(field(guidance,"gpsInfo"),"locationRssi","rtkStatus","isSmartLoc"));
        else return; // UI theme, heartbeats and unrelated redraws are not source evidence.
        STORE.navigation(kind,routeId,out,System.currentTimeMillis(),SystemClock.elapsedRealtime());
    }
    private static void onLocation(Object value) {
        Map<String,Object> out=fields(value,"latitude","longitude","accuracy","direction","speed","coordinateType",
            "timestamp","tickTime","receivetimestamp","status","rssi","provider","sourceProvider","fakeReason","emptyCode","isMatchResult");
        Object match=field(value,"matchLocationResult");
        out.put("match",getters(match,"getMainRouteId","getMatchStatus","getTimestamp","getPosType","getPosSubType"));
        out.put("routeMatch",getters(get(match,"getRouteMatchResult"),"getMatchedIndex","getLinkId","getLinkRawId","getRoadKind","getFuncClass"));
        STORE.location("location",out,System.currentTimeMillis(),SystemClock.elapsedRealtime());
    }
    private static void onHD(Object value) {
        Map<String,Object> out=getters(value,"getTimestamp","getTickTime","getLatitude","getLongitude","getSpeed","getBearing");
        Object lane=get(value,"getHDLaneMatchResult");
        out.put("lane",getters(lane,"getWorkMode","getCurLaneNum","getLaneMatchedIndex","getFreePosLaneNum","getCurLaneNumConf","getTotalLaneCntConf","getRatio","getSlope"));
        out.put("locLane",getters(get(lane,"getLocLane"),"getLaneID","getLaneId","getTileId"));
        STORE.location("hd",out,System.currentTimeMillis(),SystemClock.elapsedRealtime());
    }
    public static Map<String,Object> snapshot() {
        Map<String,Object> out=STORE.snapshot(SystemClock.elapsedRealtime());
        out.put("listenerError",error);out.put("uiAttached",uiManager!=null);out.put("locationAttached",locationManager!=null);
        return out;
    }
}
