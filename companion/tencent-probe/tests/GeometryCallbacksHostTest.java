import com.marcus.tcprobe.geometry.GeometryCallbacks;
import com.tencent.pangu.mapbiz.MapBizEventListener;
import com.tencent.pangu.mapbiz.api.common.GuideLineData;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Failures: replacing app listeners, duplicate subscription, stale old-manager callbacks, registration failure. */
public final class GeometryCallbacksHostTest {
    public static final class Manager {
        public final List<MapBizEventListener> listeners=new ArrayList<>();
        public boolean fail;
        public void addMapBizEventListener(MapBizEventListener x) {
            if(fail)throw new IllegalStateException("not ready");listeners.add(x);
        }
        public void removeMapBizEventListener(MapBizEventListener x){listeners.remove(x);}
    }
    static void check(boolean x){if(!x)throw new AssertionError();}
    public static void main(String[] args) throws Exception {
        Manager first=new Manager();MapBizEventListener original=new MapBizEventListener();first.listeners.add(original);
        GeometryCallbacks tap=GeometryCallbacks.observe(first,null);
        check(first.listeners.size()==2&&first.listeners.contains(original));
        check(GeometryCallbacks.observe(first,tap)==tap&&first.listeners.size()==2);
        GuideLineData data=new GuideLineData();tap.onGuideLineDataUpdate(data);
        check(tap.line().payload==data&&tap.line().sequence==1&&tap.line().arrivalWallMs>0);
        tap.onGuideLineDataUpdate(null);check(tap.line().payload==null&&tap.line().sequence==2);
        tap.onGuidanceAreaCenterLine(null);check(tap.area().sequence==1);
        Map<?,?> exported=(Map<?,?>)tap.snapshot(new Object()).get("guideArea");
        check(!exported.containsKey("payload")&&exported.containsKey("payloadExportPolicy"));
        exported=(Map<?,?>)tap.snapshot(null).get("guideArea");check(exported.containsKey("payload"));
        Manager second=new Manager();GeometryCallbacks next=GeometryCallbacks.observe(second,tap);
        check(first.listeners.size()==1&&first.listeners.get(0)==original&&second.listeners.size()==1);
        tap.onGuideLineDataUpdate(data);check(tap.line().sequence==2);
        check(next.line()==null);
        Manager failed=new Manager();failed.fail=true;
        try{GeometryCallbacks.observe(failed,next);throw new AssertionError();}catch(ReflectiveOperationException expected){}
        check(failed.listeners.isEmpty()&&first.listeners.size()==1);
        System.out.println("Geometry callbacks host: append, idempotence, null invalidation, manager change and failure OK");
    }
}
