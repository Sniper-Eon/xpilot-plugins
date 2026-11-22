import com.marcus.tcprobe.geometry.NavigationObservations;
import java.util.*;

/** Clock freshness, route replacement, retained values, release and bounded memory. */
public final class NavigationObservationsHostTest {
    static void check(boolean x){if(!x)throw new AssertionError();}
    static Map<String,Object> data(String key,Object value) {
        Map<String,Object> m=new LinkedHashMap<>();m.put(key,value);return m;
    }
    @SuppressWarnings("unchecked")
    public static void main(String[] args) {
        NavigationObservations store=new NavigationObservations("test");
        check(((Map<?,?>)store.snapshot(100)).get("controlUsable").equals(false));
        store.navigation("LeftDistance", "route-A", data("distanceM",80),1000,100);
        Map<String,Object> first=store.snapshot(101);
        check(first.get("routeId").equals("route-A"));
        Map<String,Object> events=(Map<String,Object>)first.get("events");
        Map<String,Object> obs=(Map<String,Object>)events.get("LeftDistance");
        check(obs.get("observedMonoMs").equals(100L));
        // Export/heartbeat cannot renew source time. Same-valued NEW callbacks can.
        store.snapshot(9000);
        check(((Map<?,?>)((Map<?,?>)store.snapshot(9001).get("events")).get("LeftDistance"))
            .get("observedMonoMs").equals(100L));
        store.navigation("LeftDistance","route-A",data("distanceM",80),1100,200);
        check(((Map<?,?>)((Map<?,?>)store.snapshot(201).get("events")).get("LeftDistance"))
            .get("observedMonoMs").equals(200L));
        store.navigation("NavRouteUpdate","route-B",data("routeId","route-B"),1200,300);
        check(!((Map<?,?>)store.snapshot(301).get("events")).containsKey("LeftDistance"));
        // Old route-tagged callbacks must not revive the previous route.
        store.navigation("LeftDistance","route-A",data("distanceM",50),1300,400);
        check(store.snapshot(401).get("routeId").equals("route-B"));
        check(!((Map<?,?>)store.snapshot(401).get("events")).containsKey("LeftDistance"));
        store.navigation("Release","route-B",data("inNavigation",false),1400,500);
        check(((Map<?,?>)store.snapshot(501).get("events")).size()==1);
        store.navigation("LeftDistance","route-B",data("distanceM",20),1500,600);
        check(((Map<?,?>)store.snapshot(601).get("events")).size()==1);
        store.navigation("StartNav","route-C",data("inNavigation",true),1600,700);
        for(int i=0;i<100;i++)store.navigation("extra"+i,"route-C",data("value",i),1700+i,800+i);
        check(((Map<?,?>)store.snapshot(1000).get("events")).size()<=32);
        // Absent/new objects do not inherit old positions or HD fields.
        store.location("location",data("latitude",23.0),2000,1000);
        store.location("location",data("latitude",null),2100,1100);
        check(((Map<?,?>)((Map<?,?>)store.snapshot(1101).get("location")).get("values")).get("latitude")==null);
        check(store.snapshot(1101).get("controlUsable").equals(false));
        // SDK clears UI observers during route changes; its authoritative lifecycle
        // can invalidate/bind a route without fabricating a guidance callback.
        store.contextRoute("route-D",true);
        check(store.snapshot(1200).get("routeId").equals("route-D"));
        check(((Map<?,?>)store.snapshot(1200).get("events")).isEmpty());
        store.navigation("LeftDistance","route-C",data("distanceM",10),2200,1200);
        check(((Map<?,?>)store.snapshot(1201).get("events")).isEmpty());
        store.navigation("LeftDistance","route-D",data("distanceM",90),2300,1300);
        check(((Map<?,?>)store.snapshot(1301).get("events")).size()==1);
        store.contextRoute("route-D",false);
        check(store.snapshot(1400).get("released").equals(true));
        check(((Map<?,?>)store.snapshot(1400).get("events")).isEmpty());
        System.out.println("Navigation observations: callback clocks, route fencing, release, no carryover and bounds OK");
    }
}
