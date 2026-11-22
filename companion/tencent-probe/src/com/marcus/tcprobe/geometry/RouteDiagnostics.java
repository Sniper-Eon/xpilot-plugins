package com.marcus.tcprobe.geometry;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Inspect existing route holders and HD gates. No navigation setters, factories or force-enable calls. */
public final class RouteDiagnostics {
    private RouteDiagnostics(){}
    private static Object read(Class<?> c,Object object,String name) throws Exception {
        Field f=c.getDeclaredField(name);f.setAccessible(true);return f.get(object);
    }
    private static Object getter(Object object,String name) throws Exception {
        Method m=object.getClass().getMethod(name);m.setAccessible(true);return m.invoke(object);
    }
    private static Object existingSingleton(Class<?> c) throws Exception {
        for(Field f:c.getDeclaredFields())if(Modifier.isStatic(f.getModifiers())&&f.getType()==c) {
            f.setAccessible(true);Object object=f.get(null);if(object!=null)return object;
        }
        return null;
    }
    private static void route(List<Object> rows,String source,Object plan,String activeId) {
        Map<String,Object> r=new LinkedHashMap<>();r.put("source",source);r.put("result",RouteDataInspector.inspect(plan,activeId));rows.add(r);
    }
    public static Map<String,Object> capture(ClassLoader loader,String activeId) {
        Map<String,Object> out=new LinkedHashMap<>(),gates=new LinkedHashMap<>(),errors=new LinkedHashMap<>();
        List<Object> routes=new ArrayList<>();out.put("sampledWallMs",System.currentTimeMillis());
        out.put("controlUsable",false);out.put("activeRouteId",activeId);out.put("hdGates",gates);
        out.put("routeSources",routes);out.put("errors",errors);
        try {
            Class<?> c=Class.forName("com.tencent.map.ama.routenav.common.util.HDNavUtil",false,loader);
            String[][] names={{"userEnabled","isUserEnableHDNav"},{"cloudMode","j"},{"guidePlaneModeEnabled","c"},
                {"rtkModeEnabled","b"},{"cloudAndDevice4kEligible","f"},{"notLowPhone","g"}};
            for(String[] name:names)try {
                Method m=c.getDeclaredMethod(name[1]);m.setAccessible(true);Object value=m.invoke(null);
                gates.put(name[0],value instanceof Enum?((Enum<?>)value).name():value);
            }catch(Throwable e){gates.put(name[0],null);errors.put(name[0],e.getClass().getSimpleName());}
        }catch(Throwable e){errors.put("hdGates",e.getClass().getSimpleName());}
        try {
            Class<?> c=Class.forName("com.tencent.map.navikuikly.data.NaviRouteDataHolder",false,loader);
            route(routes,"NaviRouteDataHolder",read(c,null,"routePlanVisitor"),activeId);
        }catch(Throwable e){errors.put("navHolder",e.getClass().getSimpleName());}
        try {
            Class<?> c=Class.forName("com.tencent.map.module.KuiklyRouteDataManager",false,loader);
            Object singleton=existingSingleton(c),plan=null;
            if(singleton!=null){Object result=read(c,singleton,"carRouteResult");if(result!=null)plan=read(result.getClass(),result,"ao");}
            route(routes,"KuiklyRouteDataManager.carRouteResult",plan,activeId);
        }catch(Throwable e){errors.put("routeDataManager",e.getClass().getSimpleName());}
        return out;
    }
}
