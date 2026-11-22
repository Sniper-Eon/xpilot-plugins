package com.marcus.tcprobe.geometry;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.LinkedHashMap;
import java.util.Map;

/** Reads existing engine lifecycle, never constructs or modifies a navigator.
 * Context polling may revoke an input; it never renews guidance/location clocks.
 */
public final class LegacyEngineContext {
    private LegacyEngineContext(){}
    static Object field(Object object,String name) {
        if(object==null)return null;
        for(Class<?> c=object.getClass();c!=null&&c!=Object.class;c=c.getSuperclass())try {
            Field f=c.getDeclaredField(name);f.setAccessible(true);return f.get(object);
        }catch(NoSuchFieldException e){continue;}catch(ReflectiveOperationException e){return null;}
        return null;
    }
    private static Object owner(Object adapter,Class<?> base) {
        if(adapter==null)return null;
        if(base.isInstance(adapter))return adapter;
        int count=0;
        for(Class<?> c=adapter.getClass();c!=null&&c!=Object.class;c=c.getSuperclass())
            for(Field f:c.getDeclaredFields()) {
                if(++count>64)return null;
                if(Modifier.isStatic(f.getModifiers())||!base.isAssignableFrom(f.getType()))continue;
                try{f.setAccessible(true);Object nav=f.get(adapter);if(base.isInstance(nav))return nav;}
                catch(ReflectiveOperationException e){return null;}
            }
        return null;
    }
    private static Object getter(Object object,String name) {
        if(object==null)return null;
        try{java.lang.reflect.Method m=object.getClass().getMethod(name);m.setAccessible(true);return m.invoke(object);}
        catch(ReflectiveOperationException e){return null;}
    }
    public static Map<String,Object> inspect(Object engine,Class<?> navBase) {
        Map<String,Object> out=new LinkedHashMap<>();out.put("navigationMode","unknown");out.put("routeId","");
        Object core=field(engine,"k"),adapter=field(field(core,"E"),"h"),nav=owner(adapter,navBase);
        out.put("enginePresent",engine!=null);out.put("navigatorPresent",nav!=null);
        if(nav==null)return out;
        Object real=field(nav,"isRealNav"),started=field(nav,"isStartNav"),simulation=field(nav,"isSimulate");
        Object provider=field(nav,"mLocationDataProvider");
        String providerClass=provider==null?"":provider.getClass().getName();
        String mode="unknown";
        if(Boolean.FALSE.equals(started))mode="idle";
        else if(Boolean.TRUE.equals(started)) {
            if(Boolean.TRUE.equals(simulation)||providerClass.contains("NavSimulateGpsProvider"))mode="simulation";
            else if(Boolean.TRUE.equals(real)&&Boolean.FALSE.equals(simulation)&&provider!=null)mode="realtime";
        }
        Object route=getter(getter(field(nav,"multiRoutes"),"a"),"getRouteId");
        out.put("navigationMode",mode);out.put("routeId",route instanceof String?route:"");
        out.put("isRealNav",real);out.put("isStartNav",started);out.put("isSimulate",simulation);
        out.put("locationProviderClass",providerClass);
        return out;
    }
    public static Map<String,Object> capture(ClassLoader loader) throws Exception {
        Class<?> factory=Class.forName("com.tencent.map.navisdk.a.ecv",false,loader);
        Field f=factory.getDeclaredField("f");f.setAccessible(true);
        Class<?> nav=Class.forName("com.tencent.map.navisdk.api.TNavCarBase",false,loader);
        return inspect(f.get(null),nav);
    }
}
