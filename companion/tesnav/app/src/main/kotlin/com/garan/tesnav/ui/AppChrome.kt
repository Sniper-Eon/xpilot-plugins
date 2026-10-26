package com.garan.tesnav.ui

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.content.res.ColorStateList
import android.os.Build
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.Button

/** Presentation only: shared touch targets, spacing and safe system-bar insets. */
internal object AppChrome {
    fun primaryButton(button: Button) = with(button) {
        val d = resources.displayMetrics.density
        textSize = 15f
        isAllCaps = false
        minimumHeight = (48 * d).toInt()
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setTextColor(Color.WHITE)
        elevation = 0f
        backgroundTintList = null
        val fill = GradientDrawable().apply {
            cornerRadius = 14 * d
            setColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
                intArrayOf(Color.rgb(163, 179, 199), Color.rgb(23, 99, 211))))
        }
        background = RippleDrawable(ColorStateList.valueOf(Color.argb(50, 255, 255, 255)), fill, null)
        setPadding((14 * d).toInt(), (8 * d).toInt(), (14 * d).toInt(), (8 * d).toInt())
    }

    fun secondaryButton(button: Button) = with(button) {
        primaryButton(this)
        val d = resources.displayMetrics.density
        setTextColor(Color.rgb(23, 77, 138))
        val fill = GradientDrawable().apply {
            cornerRadius = 14 * d
            setColor(Color.rgb(248, 251, 255))
            setStroke(d.toInt().coerceAtLeast(1), Color.rgb(218, 228, 240))
        }
        background = RippleDrawable(ColorStateList.valueOf(Color.argb(30, 23, 99, 211)), fill, null)
    }

    fun fitSystemBars(activity: Activity, root: View) {
        if (Build.VERSION.SDK_INT >= 30) {
            activity.window.insetsController?.setSystemBarsAppearance(
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS,
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS)
        } else {
            @Suppress("DEPRECATION")
            activity.window.decorView.systemUiVisibility = activity.window.decorView.systemUiVisibility or View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
        }
        root.setOnApplyWindowInsetsListener { view, insets ->
            if (Build.VERSION.SDK_INT >= 30) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            } else {
                @Suppress("DEPRECATION")
                view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                    insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
        root.requestApplyInsets()
    }
}
