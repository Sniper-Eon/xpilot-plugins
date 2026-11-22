package com.marcus.tcprobe.geometry;

import java.lang.reflect.Array;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.IdentityHashMap;
import java.util.Map;

/** Bounded field-only serializer: no Tencent getters or toString calls. */
public final class RawJson {
    public static final class Result {
        public final String json;
        public final boolean truncated;
        public final int unreadable;
        Result(String text, boolean cut, int errors) { json=text; truncated=cut; unreadable=errors; }
    }
    private final StringBuilder out = new StringBuilder();
    private final IdentityHashMap<Object,Boolean> seen = new IdentityHashMap<>();
    private final long deadline = System.nanoTime()+250_000_000L;
    private int nodes, errors;
    private boolean cut;
    public static Result encode(Object value) {
        RawJson w=new RawJson(); w.value(value,0);
        return new Result(w.out.toString(),w.cut,w.errors);
    }
    public static String quote(String s) {
        RawJson w=new RawJson(); w.string(s); return w.out.toString();
    }
    private boolean limit() {
        boolean hit=nodes>=20000 || out.length()>1_000_000 || System.nanoTime()>deadline;
        if (hit) cut=true;
        return hit;
    }
    private void string(String s) {
        if(s==null) { out.append("null"); return; }
        out.append('"'); int n=Math.min(s.length(),4096);
        if(n<s.length())cut=true;
        for(int i=0;i<n;i++) {
            char c=s.charAt(i);
            if(c=='"'||c=='\\') out.append('\\').append(c);
            else if(c<32) { String h=Integer.toHexString(c);out.append("\\u");for(int k=h.length();k<4;k++)out.append('0');out.append(h); }
            else out.append(c);
        }
        out.append('"');
    }
    private void value(Object x,int depth) {
        if(limit()||depth>10) { cut=true;out.append("null");return; }
        nodes++;
        if(x==null) {out.append("null");return;}
        if(x instanceof String || x instanceof Character || x instanceof Enum) {string(x instanceof Enum?((Enum<?>)x).name():String.valueOf(x));return;}
        if(x instanceof Boolean) {out.append(x);return;}
        if(x instanceof Number) {
            double d=((Number)x).doubleValue();
            if(!Double.isFinite(d)) {out.append("null");errors++;}
            else if(x instanceof Long && (((Long)x)>9007199254740991L || ((Long)x)<-9007199254740991L)) string(x.toString());
            else out.append(x);
            return;
        }
        if(seen.put(x,Boolean.TRUE)!=null) {out.append("null");cut=true;return;}
        try {
            if(x instanceof Map) {
                out.append('{');int n=0;
                for(Object e0:((Map<?,?>)x).entrySet()) {
                    if(n>=64||limit()){cut=true;break;}
                    Map.Entry<?,?> e=(Map.Entry<?,?>)e0;
                    if(!(e.getKey() instanceof String)){errors++;continue;}
                    if(n++>0)out.append(',');string((String)e.getKey());out.append(':');value(e.getValue(),depth+1);
                }
                out.append('}');return;
            }
            if(x instanceof Iterable || x.getClass().isArray()) {
                out.append('[');int n=0;
                if(x.getClass().isArray()) {
                    int len=Array.getLength(x);
                    for(int i=0;i<len;i++){if(n>=4096||limit()){cut=true;break;}if(n++>0)out.append(',');value(Array.get(x,i),depth+1);}
                } else for(Object item:(Iterable<?>)x) {
                    if(n>=4096||limit()){cut=true;break;}if(n++>0)out.append(',');value(item,depth+1);
                }
                out.append(']');return;
            }
            String name=x.getClass().getName();
            if(!name.startsWith("com.tencent.pangu.mapbase.") && !name.startsWith("com.tencent.pangu.mapbiz.") && !name.startsWith("com.tencent.tencentmap.mapbiz.") && !name.startsWith("com.tencent.map.navisdk.")) {
                out.append("{\"_unexpandedClass\":");string(name);out.append('}');errors++;return;
            }
            out.append("{\"_class\":");string(name);int n=0;
            for(Class<?> c=x.getClass();c!=null&&c!=Object.class;c=c.getSuperclass()) {
                for(Field f:c.getDeclaredFields()) {
                    if(Modifier.isStatic(f.getModifiers())||f.isSynthetic())continue;
                    if(n++>=64||limit()){cut=true;break;}
                    Object v;
                    try {f.setAccessible(true);v=f.get(x);}catch(Throwable e){errors++;continue;}
                    out.append(',');string(f.getName());out.append(':');value(v,depth+1);
                }
                if(n>=64||limit())break;
            }
            out.append('}');
        } finally { seen.remove(x); }
    }
}
