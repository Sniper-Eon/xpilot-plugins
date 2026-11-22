package com.marcus.tcprobe.geometry;

public final class GeometryProbeApp extends com.marcus.tcprobe.TcProbeApp {
    @Override public void onCreate() {
        super.onCreate();
        try { GeometryReader.start(this); }
        catch(Throwable e) { android.util.Log.e("TcGeometry","read-only exporter startup failed",e); }
    }
}
