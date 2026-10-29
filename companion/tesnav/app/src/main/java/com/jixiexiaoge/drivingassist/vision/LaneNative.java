package com.jixiexiaoge.drivingassist.vision;

/** Minimal JNI ABI adapter. The class name is required by the reference binary;
 * it does not change this application's installation identity. No reference Java
 * implementation or private model assets are distributed in this source tree. */
public final class LaneNative {
    public native String nativeLoadStatus();
    public native long nativeInit(String path);
    public native int[] nativeRoadShape(long handle);
    public native int nativeInferCompact(long handle, byte[] y, int width, int height,
                                         int stride, float[] scratch, float[] scores);
    public native void nativeSetRoi(float x, float y);
    public native void nativeRelease(long handle);
    public static void load() { System.loadLibrary("lanenet"); }
}
