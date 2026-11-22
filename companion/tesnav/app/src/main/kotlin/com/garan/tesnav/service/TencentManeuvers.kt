package com.garan.tesnav.service

import com.garan.tesnav.model.NavigationManeuver

/** tc-v61 Constants.IntersectionConstants, read from the unchanged SDK DEX.
 * Names/codes are statically checked; only code 3 also has a real UI capture.
 * Undocumented actions stay unknown. No Amap icon namespace is used.
 */
internal fun tencentManeuver(code: Int?): NavigationManeuver = when(code) {
    0 -> NavigationManeuver.NONE
    1,8,18,28,90 -> NavigationManeuver.STRAIGHT
    2,16,17,32,33,34,35,36 -> NavigationManeuver.TURN_LEFT
    3,26,27,42,43,44,45,46 -> NavigationManeuver.TURN_RIGHT
    10,37 -> NavigationManeuver.SLIGHT_LEFT
    20,47 -> NavigationManeuver.SLIGHT_RIGHT
    6,12,13,14,81,84 -> NavigationManeuver.KEEP_LEFT
    7,22,23,24,82,83 -> NavigationManeuver.KEEP_RIGHT
    30,31 -> NavigationManeuver.SHARP_LEFT
    40,41 -> NavigationManeuver.SHARP_RIGHT
    4,85,86 -> NavigationManeuver.U_TURN_LEFT
    87,88,89 -> NavigationManeuver.U_TURN_RIGHT
    5,in 51..59 -> NavigationManeuver.ROUNDABOUT
    60,61,62 -> NavigationManeuver.DESTINATION
    else -> NavigationManeuver.UNKNOWN
}
