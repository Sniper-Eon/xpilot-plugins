package com.garan.tesnav.ui

import android.content.Context
import android.content.Intent
import android.net.Uri

/** A route-page dispatch is not an acknowledgement of active navigation. */
internal object TencentMapActions {
    const val PACKAGE = "com.tencent.map"

    fun open(context: Context): Boolean = runCatching {
        val launch = context.packageManager.getLaunchIntentForPackage(PACKAGE) ?: return false
        context.startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    }.getOrDefault(false)

    fun navigate(context: Context, name: String, latitude: Double, longitude: Double): Boolean {
        val uri = TencentMapDestination.uri(name, latitude, longitude, context.packageName) ?: return false
        return runCatching {
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)).apply {
                setPackage(PACKAGE)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
            true
        }.getOrDefault(false)
    }
}
