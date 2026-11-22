package com.marcus.tcprobe.geometry;

import android.content.Context;
import android.os.Process;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/** Independent read-only poller of the legacy engine's cached map geometry.
 * No navigation settings, listener replacement, reflection setters or control output.
 */
public final class GeometryReader {
    private static final String MONITOR="com.tencent.map.ama.navigation.engine.car.hd.monitor.inner.HDMonitor";
    private static final String BUILD="tc-geometry-nav-observer-v5-20261122";
    private static final AtomicBoolean STARTED=new AtomicBoolean();
    private static volatile String snapshot="{\"schema\":1,\"controlUsable\":false,\"objectPresent\":false,\"state\":\"starting\"}";
    private static volatile int port;
    private static volatile String lastError="";
    private static volatile String attachError="not_attempted";
    private static volatile GeometryCallbacks callbacks;
    private static volatile Map<String,Object> routeDiagnostics;
    private static long lastRouteSample;
    private static final AtomicBoolean ATTACH_PENDING=new AtomicBoolean();
    private GeometryReader() {}
    public static void start(final Context context) {
        if(!STARTED.compareAndSet(false,true))return;
        final Context app=context.getApplicationContext();
        Thread server=new Thread(new Runnable(){public void run(){serve();}},"tc-geometry-http");
        server.setDaemon(true);server.start();
        Thread worker=new Thread(new Runnable(){public void run(){poll(app);}},"tc-geometry-read");
        worker.setDaemon(true);worker.start();
    }
    private static Object read(Class<?> c,Object object,String name) throws Exception {
        Field f=c.getDeclaredField(name);f.setAccessible(true);return f.get(object);
    }
    private static Object safeRead(Class<?> c,Object object,String name) {
        try{return read(c,object,name);}catch(Throwable e){return null;}
    }
    private static String text(Object x){return x instanceof String?(String)x:"";}
    private static int count(Object x) {
        if(x instanceof Map)return ((Map<?,?>)x).size();
        if(x instanceof java.util.Collection)return ((java.util.Collection<?>)x).size();return -1;
    }
    private static Object getter(Object object,String name) throws Exception {
        java.lang.reflect.Method m=object.getClass().getMethod(name);m.setAccessible(true);return m.invoke(object);
    }
    private static void attachOnMain(final Context app) {
        if(!ATTACH_PENDING.compareAndSet(false,true))return;
        new Handler(Looper.getMainLooper()).post(new Runnable(){public void run(){
            try{LegacyNavigationTap.attach(app.getClassLoader());}
            catch(Throwable e){Log.w("TcGeometry","legacy observer not ready: "+e.getClass().getSimpleName());}
            try {
                Class<?> c=Class.forName("com.tencent.map.framework.TMContext",false,app.getClassLoader());
                Object map=c.getMethod("getMap").invoke(null);
                Object wrapper=getter(getter(getter(map,"C"),"getMapPro"),"b");
                Object manager=getter(wrapper,"b");
                callbacks=GeometryCallbacks.observe(manager,callbacks);attachError="";
                long now=SystemClock.elapsedRealtime();
                if(now-lastRouteSample>=10000) {
                    lastRouteSample=now;
                    Class<?> monitor=Class.forName(MONITOR,false,app.getClassLoader());
                    String before=text(safeRead(monitor,null,"currentNavRoute"));
                    Map<String,Object> report=RouteDiagnostics.capture(app.getClassLoader(),before);
                    String after=text(safeRead(monitor,null,"currentNavRoute"));
                    report.put("routeChangedDuringRead",!before.equals(after));routeDiagnostics=report;
                }
            } catch(Throwable e){attachError=e.getClass().getSimpleName()+": "+String.valueOf(e.getMessage());}
            finally{ATTACH_PENDING.set(false);}
        }});
    }
    private static void poll(Context app) {
        long lastWrite=0,lastAttach=0;String previousData="";
        while(!Thread.currentThread().isInterrupted()) {
            try {
                long attachNow=SystemClock.elapsedRealtime();
                if(attachNow-lastAttach>=5000){attachOnMain(app);lastAttach=attachNow;}
                Class<?> c=Class.forName(MONITOR,false,app.getClassLoader());
                String routeBefore=text(safeRead(c,null,"currentNavRoute"));
                Object area=read(c,null,"mapBizCenterLineInfo");
                Map<String,Object> data=new LinkedHashMap<>();
                data.put("guideAreaCenterLineData",area);
                data.put("guideAreaDistanceInfo",safeRead(c,null,"mapBizDistanceInfo"));
                data.put("hasCallMapBizCenterLine",safeRead(c,null,"hasCallMapBizCenterLine"));
                data.put("isInHDNav",safeRead(c,null,"isInHDNav"));
                data.put("guidanceDistance",safeRead(c,null,"guidanceDistance"));
                GeometryCallbacks tap=callbacks;
                data.put("callbackObservations",tap==null?null:tap.snapshot(area));
                data.put("routeDiagnostics",routeDiagnostics);
                RawJson.Result raw=RawJson.encode(data);
                String routeAfter=text(safeRead(c,null,"currentNavRoute"));
                Object after=read(c,null,"mapBizCenterLineInfo");
                boolean consistent=routeBefore.equals(routeAfter)&&area==after;
                String areaRoute=area==null?"":text(safeRead(area.getClass(),area,"routeId"));
                String routeMatch=routeAfter.length()==0||areaRoute.length()==0?"null":String.valueOf(routeAfter.equals(areaRoute));
                int points=area==null?0:count(safeRead(area.getClass(),area,"centerLine"));
                int groups=area==null?0:count(safeRead(area.getClass(),area,"laneGroupMap"));
                long now=SystemClock.elapsedRealtime();
                GeometryCallbacks.Observation guideLine=tap==null?null:tap.line();
                GeometryCallbacks.Observation guideArea=tap==null?null:tap.area();
                boolean linePresent=guideLine!=null&&guideLine.payload!=null;
                boolean callbackAreaPresent=guideArea!=null&&guideArea.payload!=null;
                snapshot="{\"schema\":2,\"build\":"+RawJson.quote(BUILD)+",\"pid\":"+Process.myPid()+
                    ",\"port\":"+port+",\"pollMonoMs\":"+now+",\"sourceAgeMs\":null,\"sourceFreshness\":\"unknown_cached_object\""+
                    ",\"coordinateSystem\":\"unknown_raw\",\"controlUsable\":false,\"objectPresent\":"+(area!=null||linePresent||callbackAreaPresent)+
                    ",\"areaCachePresent\":"+(area!=null)+",\"guideLineCallbackPresent\":"+linePresent+
                    ",\"guideAreaCallbackPresent\":"+callbackAreaPresent+
                    ",\"listenerAttached\":"+(tap!=null&&tap.active())+",\"listenerError\":"+RawJson.quote(attachError)+
                    ",\"snapshotConsistent\":"+consistent+",\"consistencyCheck\":\"route_and_cache_reference_only\",\"routeIdentityMatch\":"+routeMatch+
                    ",\"currentRouteId\":"+RawJson.quote(routeAfter)+",\"centerLinePointCount\":"+points+
                    ",\"laneGroupCount\":"+groups+",\"truncated\":"+raw.truncated+
                    ",\"unreadableFields\":"+raw.unreadable+",\"largeIntegerEncoding\":\"decimal_string_above_2pow53\",\"raw\":"+raw.json+"}";
                lastError="";
                // Save only changed raw data, or a sparse heartbeat, not unbounded logs.
                if(!previousData.equals(raw.json)||now-lastWrite>30000) {
                    write(app,snapshot);lastWrite=now;previousData=raw.json;
                }
            } catch(Throwable e) {
                lastError=e.getClass().getSimpleName()+": "+String.valueOf(e.getMessage());
                snapshot="{\"schema\":1,\"build\":"+RawJson.quote(BUILD)+",\"controlUsable\":false,\"objectPresent\":false,\"error\":"+RawJson.quote(lastError)+"}";
            }
            try{Thread.sleep(1000);}catch(InterruptedException e){Thread.currentThread().interrupt();}
        }
    }
    private static void write(Context context,String data) throws Exception {
        File base=context.getExternalFilesDir(null);
        if(base==null)base=context.getFilesDir();
        File dir=new File(base,"tcgeometry");
        if(!dir.isDirectory()&&!dir.mkdirs())throw new java.io.IOException("cannot create export directory");
        File temp=new File(dir,"geometry-"+Process.myPid()+".tmp");
        File dest=new File(dir,"geometry-"+Process.myPid()+".json");
        try(FileOutputStream stream=new FileOutputStream(temp)){stream.write(data.getBytes(StandardCharsets.UTF_8));}
        if(!temp.renameTo(dest))throw new java.io.IOException("atomic snapshot rename failed");
    }
    private static void serve() {
        ServerSocket server=null;
        for(int p=8898;p<8908;p++)try {
            server=new ServerSocket();server.bind(new InetSocketAddress("127.0.0.1",p),4);port=p;break;
        }catch(Exception e){try{if(server!=null)server.close();}catch(Exception ignored){}server=null;}
        if(server==null){Log.e("TcGeometry","no free loopback diagnostic port");return;}
        Log.i("TcGeometry","read-only geometry export on loopback "+port);
        while(true)try(Socket client=server.accept()) {
            client.setSoTimeout(1500);InputStream in=client.getInputStream();StringBuilder request=new StringBuilder();
            // Consume bounded HTTP headers before closing: unread headers caused TCP resets on Android.
            for(int i=0;i<8192;i++){
                int ch=in.read();if(ch<0)break;request.append((char)ch);
                int n=request.length();
                if(n>=4&&request.substring(n-4).equals("\r\n\r\n"))break;
                if(n>=2&&request.substring(n-2).equals("\n\n"))break;
            }
            String first=request.toString();String body;String status;
            if(first.startsWith("GET /geometry ")){body=snapshot;status="200 OK";}
            else if(first.startsWith("GET /navigation ")){body=RawJson.encode(LegacyNavigationTap.snapshot()).json;status="200 OK";}
            else if(first.startsWith("GET /health ")) {
                body="{\"build\":"+RawJson.quote(BUILD)+",\"pid\":"+Process.myPid()+",\"port\":"+port+",\"controlUsable\":false,\"lastError\":"+RawJson.quote(lastError)+",\"listenerError\":"+RawJson.quote(attachError)+"}";status="200 OK";
            }else {body="{\"error\":\"read-only endpoints: /health /geometry /navigation\"}";status="404 Not Found";}
            byte[] bytes=body.getBytes(StandardCharsets.UTF_8);
            String header="HTTP/1.0 "+status+"\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: "+bytes.length+"\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
            client.getOutputStream().write(header.getBytes(StandardCharsets.US_ASCII));client.getOutputStream().write(bytes);
        } catch(Throwable e){Log.w("TcGeometry","diagnostic connection ended");}
    }
}
