import com.marcus.tcprobe.geometry.LegacyEngineContext;
import java.util.Map;

public final class EngineContextHostTest {
    public static class Base { public boolean isRealNav=true,isStartNav=true; public Routes multiRoutes=new Routes(); }
    public static class Nav extends Base { public boolean isSimulate; public Object mLocationDataProvider=new Object(); }
    public static class Routes { public Route a(){return new Route();} }
    public static class Route { public String getRouteId(){return "route-A";} }
    public static class Adapter { public final Base owner; Adapter(Base nav){owner=nav;} }
    public static class Config { public Object h; }
    public static class Core { public Config E=new Config(); }
    public static class Engine { public Core k=new Core(); }
    public static void main(String[] args) {
        Engine engine=new Engine();Nav nav=new Nav();engine.k.E.h=new Adapter(nav);
        Map<String,Object> d=LegacyEngineContext.inspect(engine,Base.class);
        if(!"realtime".equals(d.get("navigationMode"))||!"route-A".equals(d.get("routeId")))throw new AssertionError();
        nav.isSimulate=true;
        if(!"simulation".equals(LegacyEngineContext.inspect(engine,Base.class).get("navigationMode")))throw new AssertionError();
        nav.isStartNav=false;
        if(!"idle".equals(LegacyEngineContext.inspect(engine,Base.class).get("navigationMode")))throw new AssertionError();
        engine.k.E.h=null;
        if(!"unknown".equals(LegacyEngineContext.inspect(engine,Base.class).get("navigationMode")))throw new AssertionError();
        if(!"unknown".equals(LegacyEngineContext.inspect(null,Base.class).get("navigationMode")))throw new AssertionError();
        System.out.println("Engine context: existing owner, inherited flags, simulation/idle/absent invalidation OK");
    }
}
