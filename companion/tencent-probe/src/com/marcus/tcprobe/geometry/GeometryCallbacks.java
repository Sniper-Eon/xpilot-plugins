package com.marcus.tcprobe.geometry;

import com.tencent.pangu.mapbiz.MapBizEventListener;
import com.tencent.pangu.mapbiz.api.common.GuideLineData;
import com.tencent.pangu.mapbiz.api.scale.MagicCameraStatus;
import com.tencent.pangu.mapbase.common.guidance.GuideAreaCenterLineData;
import com.tencent.pangu.mapbase.common.guidance.GuideAreaEndDistance;
import java.lang.reflect.Method;
import java.util.LinkedHashMap;
import java.util.Map;

/** Append-only diagnostic observer. Callbacks only retain the latest object reference. */
public final class GeometryCallbacks extends MapBizEventListener {
    public static final class Observation {
        public final Object payload;
        public final long sequence,arrivalWallMs,arrivalNano;
        Observation(Object value,long seq) {
            payload=value;sequence=seq;arrivalWallMs=System.currentTimeMillis();arrivalNano=System.nanoTime();
        }
    }
    private final Object manager;
    private volatile boolean active=true;
    private volatile Observation line,area,distance,camera;
    private GeometryCallbacks(Object value){manager=value;}
    private static void invoke(Object manager,String name,GeometryCallbacks listener) throws ReflectiveOperationException {
        Method m=manager.getClass().getMethod(name,MapBizEventListener.class);
        m.setAccessible(true);m.invoke(manager,listener);
    }
    public static GeometryCallbacks observe(Object manager,GeometryCallbacks old) throws ReflectiveOperationException {
        if(manager==null)throw new IllegalArgumentException("map manager absent");
        if(old!=null&&old.manager==manager&&old.active)return old;
        if(old!=null&&old.active) {
            invoke(old.manager,"removeMapBizEventListener",old);
            old.active=false;
        }
        GeometryCallbacks next=new GeometryCallbacks(manager);
        invoke(manager,"addMapBizEventListener",next);
        return next;
    }
    private static long sequence(Observation old){return old==null?1:old.sequence+1;}
    @Override public synchronized void onGuideLineDataUpdate(GuideLineData value) {
        try{if(active)line=new Observation(value,sequence(line));}catch(Throwable ignored){}
    }
    @Override public synchronized void onGuidanceAreaCenterLine(GuideAreaCenterLineData value) {
        try{if(active)area=new Observation(value,sequence(area));}catch(Throwable ignored){}
    }
    @Override public synchronized void onGuideAreaEndDistance(GuideAreaEndDistance value) {
        try{if(active)distance=new Observation(value,sequence(distance));}catch(Throwable ignored){}
    }
    @Override public synchronized void onMagicCameraStatus(MagicCameraStatus value) {
        try{if(active)camera=new Observation(value,sequence(camera));}catch(Throwable ignored){}
    }
    public Observation line(){return line;}
    public Observation area(){return area;}
    public boolean active(){return active;}
    private static Object info(Observation value) {
        return info(value,false);
    }
    private static Object info(Observation value,boolean cacheExported) {
        if(value==null)return null;
        Map<String,Object> d=new LinkedHashMap<>();
        d.put("sequence",value.sequence);d.put("arrivalWallMs",value.arrivalWallMs);
        d.put("arrivalAgeMs",Math.max(0,(System.nanoTime()-value.arrivalNano)/1000000L));
        d.put("sourceTimestampVerified",false);
        if(cacheExported) {
            d.put("payloadExportPolicy","engine_cache_exported_separately_callback_identity_not_compared");
            d.put("payloadPresent",value.payload!=null);
        } else d.put("payload",value.payload);
        return d;
    }
    public Map<String,Object> snapshot() {
        return snapshot(null);
    }
    public Map<String,Object> snapshot(Object areaCache) {
        Map<String,Object> d=new LinkedHashMap<>();d.put("attached",active);
        d.put("sourceTimestampMeaning","callback_arrival_not_map_geometry_creation");
        d.put("guideLine",info(line));d.put("guideArea",info(area,areaCache!=null));
        d.put("guideAreaDistance",info(distance));d.put("magicCamera",info(camera));return d;
    }
}
