import com.marcus.tcprobe.geometry.RawJson;
import java.util.*;

public final class RawJsonHostTest {
    static void check(boolean x){if(!x)throw new AssertionError();}
    public static void main(String[] args) {
        check(RawJson.encode(null).json.equals("null"));
        Map<String,Object> m=new LinkedHashMap<>();
        m.put("laneId",Long.MAX_VALUE);m.put("text","a\n\"b\\c");m.put("bad",Double.NaN);
        RawJson.Result r=RawJson.encode(m);
        check(r.json.contains("\"9223372036854775807\""));
        check(r.json.contains("a\\u000a\\\"b\\\\c"));
        check(r.json.contains("\"bad\":null"));check(r.unreadable==1);
        List<Object> cycle=new ArrayList<>();cycle.add(cycle);
        check(RawJson.encode(cycle).truncated);
        check(RawJson.encode(new int[5000]).truncated);
        Map<String,Object> safe=new LinkedHashMap<>();safe.put("point",Arrays.asList(1.2,3.4,5.6));
        r=RawJson.encode(safe);check(!r.truncated&&r.unreadable==0&&r.json.equals("{\"point\":[1.2,3.4,5.6]}"));
        Object dangerous=new Object(){@Override public String toString(){throw new AssertionError("must not call");}};
        check(RawJson.encode(dangerous).unreadable==1);
        System.out.println("RawJson host: nulls, exact lane IDs, escaping, non-finite, cycles, bounds and getter-free fallback OK");
    }
}
