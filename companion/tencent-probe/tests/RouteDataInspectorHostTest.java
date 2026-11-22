import com.marcus.tcprobe.geometry.RouteDataInspector;
import java.util.*;

/** Failures: stale/wrong route, failed query masquerading as zero, HD status mistaken for lane geometry, unbounded route reads. */
public final class RouteDataInspectorHostTest {
    public static final class Plan {
        public List<String> ids=Arrays.asList("route-A");
        public int calls,status=1;public boolean fail;
        public Route route=new Route();
        public List<String> getRouteIdList(){return ids;}
        public int getHDResStatusOnRoute(String id){calls++;if(fail)throw new IllegalStateException("native not ready");return status;}
        public Route getRoute(String id){return route;}
    }
    public static final class Route {
        public String id="route-A";public int length=1000,reads;
        public String getRouteId(){return id;}
        public int getLength(){return length;}
        public List<Object> getAdMapDataLinkList(){reads++;return Collections.emptyList();}
    }
    static void check(boolean v){if(!v)throw new AssertionError();}
    public static void main(String[] args) {
        Plan p=new Plan();Map<String,Object> d=RouteDataInspector.inspect(p,"route-B");
        check(Boolean.FALSE.equals(d.get("routeMatched"))&&p.calls==0&&p.route.reads==0);
        d=RouteDataInspector.inspect(p,"");check(p.calls==0);
        d=RouteDataInspector.inspect(p,"route-A");check(Integer.valueOf(1).equals(d.get("hdStatus")));
        check("hd_not_requested".equals(d.get("hdStatusMeaning"))&&Boolean.FALSE.equals(d.get("controlUsable")));
        p.status=0;d=RouteDataInspector.inspect(p,"route-A");
        check("hd_search_success".equals(d.get("hdStatusMeaning"))&&Boolean.FALSE.equals(d.get("physicalLaneGeometryVerified")));
        p.fail=true;d=RouteDataInspector.inspect(p,"route-A");check(d.get("hdStatus")==null);
        p.fail=false;p.route.length=20001;int before=p.route.reads;d=RouteDataInspector.inspect(p,"route-A");
        check(p.route.reads==before&&"route_length_limit".equals(d.get("adDataSkipReason")));
        p.route.id="other";before=p.route.reads;d=RouteDataInspector.inspect(p,"route-A");
        check(p.route.reads==before&&Boolean.FALSE.equals(d.get("routeMatched")));
        check("plan_absent".equals(RouteDataInspector.inspect(null,"route-A").get("reason")));
        System.out.println("Route data inspector host: route identity, unknown-on-error, HD status semantics, bounded extraction OK");
    }
}
