package android.util
// JVM harness only: Android logging shim; never part of phone/plugin runtime.
object Log {
 @JvmStatic fun d(tag: String, msg: String): Int = 0
 @JvmStatic fun i(tag: String, msg: String): Int = 0
 @JvmStatic fun w(tag: String, msg: String): Int = 0
 @JvmStatic fun w(tag: String, msg: String, error: Throwable?): Int = 0
 @JvmStatic fun e(tag: String, msg: String): Int { System.err.println("$tag: $msg"); return 0 }
 @JvmStatic fun e(tag: String, msg: String, error: Throwable?): Int { System.err.println("$tag: $msg"); return 0 }
}
