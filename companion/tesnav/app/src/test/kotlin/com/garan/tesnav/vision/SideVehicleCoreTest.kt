package com.garan.tesnav.vision

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.roundToLong

class SideVehicleCoreTest {
    private val box = VehicleBox(100.0, 200.0, 140.0, 300.0, .9)
    @Test fun speedUsesCaptureTimeAndNeverInventsMissingGeometry() {
        val tracker = SideVehicleTracker()
        var result: SideObservation? = null
        repeat(6) { i -> result = tracker.update(listOf(SideDetection(box, "left", 20.0 - i * .5)), 1_000_000_000L + i * 250_000_000L, 15.0)["left"] }
        assertNotNull(result)
        assertEquals(-2.0, result!!.relative_speed_mps!!, 1e-8)
        assertEquals(13.0, result!!.absolute_speed_mps!!, 1e-8)
        val uncalibrated = tracker.update(listOf(SideDetection(box, "left", null)), 2_500_000_000, 15.0)["left"]!!
        assertNull(uncalibrated.distance_m)
        assertNull(uncalibrated.relative_speed_mps)
    }
    @Test fun missedFramesDoNotReturnOldTracksOrRefreshTheirTime() {
        val tracker = SideVehicleTracker()
        repeat(5) { tracker.update(listOf(SideDetection(box, "left", 20.0)), 1_000_000_000L + it * 250_000_000L, 15.0) }
        assertNull(tracker.update(emptyList(), 2_250_000_000, 15.0)["left"])
        assertNull(tracker.update(listOf(SideDetection(box, "left", 20.0)), 5_000_000_000, 15.0)["left"])
    }
    @Test fun duplicateFramesCannotCreateTrackHits() {
        val tracker = SideVehicleTracker()
        repeat(20) { assertNull(tracker.update(listOf(SideDetection(box, "left", 20.0)), 1_000_000_000L, 15.0)["left"]) }
    }
    @Test fun discontinuousDistancesDoNotBecomeSpeeds() {
        val tracker = SideVehicleTracker()
        repeat(5) { tracker.update(listOf(SideDetection(box, "left", 20.0)), 1_000_000_000L + it * 250_000_000L, 15.0) }
        assertNull(tracker.update(listOf(SideDetection(box, "left", 40.0)), 2_250_000_000, 15.0)["left"])
    }
    @Test fun projectionRejectsMissingCalibrationAndClippedObjects() {
        assertNull(SideVehicleGeometry.distance(box, null, 960, 601))
        val inverse = listOf(0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        assertEquals(20.0, SideVehicleGeometry.distance(box, inverse, 960, 601)!!, .001)
        assertNull(SideVehicleGeometry.distance(box.copy(y2 = 600.0), inverse, 960, 601))
    }
    @Test fun modelOutputDecodesAndSuppressesDuplicateBoxes() {
        val output = arrayOf(floatArrayOf(160f, 160f), floatArrayOf(160f, 160f), floatArrayOf(40f, 40f), floatArrayOf(40f, 40f), floatArrayOf(.9f, .8f))
        assertEquals(1, SideVehicleGeometry.decode(output, 960, 600).size)
    }

    @Test fun sceneSizedFalseBoxesAreRejectedWithoutRemovingSmallerVehicles() {
        val output = arrayOf(floatArrayOf(160f, 160f), floatArrayOf(160f, 160f),
            floatArrayOf(320f, 40f), floatArrayOf(320f, 40f), floatArrayOf(.99f, .9f))
        val boxes = SideVehicleGeometry.decode(output, 960, 600)
        assertEquals(1, boxes.size)
        assertEquals(120.0, boxes.single().x2 - boxes.single().x1, 1e-8)
        // A large partial side view is not a whole-scene box.
        val partial = arrayOf(floatArrayOf(160f), floatArrayOf(160f),
            floatArrayOf(200f), floatArrayOf(180f), floatArrayOf(.9f))
        assertEquals(1, SideVehicleGeometry.decode(partial, 960, 600).size)
    }

    @Test fun wholeSceneBoxIsRemovedBeforeNmsSoItCannotEraseAnOverlappingVehicle() {
        // On a square frame the 300px scene box overlaps the vehicle with IoU > 0.45
        // and has the higher score. Filtering it first is what keeps the vehicle.
        val output = arrayOf(
            floatArrayOf(160f, 160f), floatArrayOf(160f, 200f),
            floatArrayOf(300f, 220f), floatArrayOf(300f, 200f),
            floatArrayOf(.99f, .9f))
        val boxes = SideVehicleGeometry.decode(output, 320, 320)
        assertEquals(1, boxes.size)
        assertEquals(220.0, boxes.single().x2 - boxes.single().x1, 1e-6)
    }

    @Test fun nearFullFrameBoxThatLetterboxClampingLeavesUnderEightyPercentIsRejected() {
        // 250x200 in the 320 input covers ~78% of the width and ~95% of the height
        // after unletterboxing, and its bottom is not clipped. Still not measurable.
        val output = arrayOf(floatArrayOf(160f), floatArrayOf(150f),
            floatArrayOf(250f), floatArrayOf(200f), floatArrayOf(.95f))
        assertTrue(SideVehicleGeometry.decode(output, 960, 600).isEmpty())
    }

    @Test fun letterboxPaddingMatchesTheWideCameraDecode() {
        val placed = SideVehicleGeometry.letterbox(960, 600, 320)
        assertEquals(0, placed.dx)
        assertEquals(60, placed.dy)
        assertEquals(320, placed.contentWidth)
        assertEquals(200, placed.contentHeight)
    }

    @Test fun measurementsKeepOnlyCalibratedSideVehiclesInsideTheRoi() {
        val inverse = listOf(0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        val roi = mapOf(
            "poly_left_norm" to listOf(listOf(0.0, 0.3), listOf(0.4, 0.3), listOf(0.4, 0.8), listOf(0.0, 0.8)),
            "poly_right_norm" to listOf(listOf(0.6, 0.3), listOf(1.0, 0.3), listOf(1.0, 0.8), listOf(0.6, 0.8)),
        )
        val left = VehicleBox(100.0, 200.0, 140.0, 300.0, .9)
        val right = VehicleBox(700.0, 200.0, 760.0, 300.0, .8)
        val outside = VehicleBox(400.0, 200.0, 460.0, 300.0, .9)
        val scene = VehicleBox(0.0, 0.0, 900.0, 580.0, .99)
        val clipped = left.copy(y2 = 600.0)
        val measured = SideVehicleGeometry.measurements(listOf(left, right, outside, scene, clipped), 960, 601, roi, inverse)
        assertEquals(listOf("left", "right"), measured.map { it.side })
        assertEquals(20.0, measured[0].distance!!, .001)
        assertTrue(SideVehicleGeometry.measurements(listOf(left), 960, 601, roi, null).isEmpty())
    }

    @Test fun measurementFieldsOmitUntrustedSpeedsAndNeverUseBlindspotKeys() {
        val good = measurementFields(SideObservation(3, 20.0, -2.0, 13.0, 5, .9), 0)!!
        assertEquals(20.0, good["distance_m"])
        assertEquals(-2.0, good["relative_speed_mps"])
        assertEquals(13.0, good["absolute_speed_mps"])
        assertEquals(3, good["track_id"])
        assertEquals(5, good["track_hits"])
        assertEquals(.9, good["track_confidence"])
        assertEquals(0, good["age_ms"])
        assertFalse(good.keys.any { it == "hits" || it == "confidence" || it == "occupied" })
        val bounded = measurementFields(SideObservation(3, 20.0, 25.0, 0.0, 3, .30), SIDE_MEASUREMENT_MAX_AGE_MS)!!
        assertEquals(25.0, bounded["relative_speed_mps"])
        assertEquals(0.0, bounded["absolute_speed_mps"])
        assertNull(measurementFields(SideObservation(3, 20.0, 25.1, -0.1, 5, .9), 0)!!["relative_speed_mps"])
        assertNull(measurementFields(SideObservation(3, 20.0, 1.0, 70.1, 5, .9), 0)!!["absolute_speed_mps"])
        assertEquals(70.0, measurementFields(SideObservation(3, 80.0, null, 70.0, 5, .9), 0)!!["absolute_speed_mps"])
        for (bad in listOf(
            SideObservation(3, null, -2.0, 13.0, 5, .9),
            SideObservation(3, 1.9, -2.0, 13.0, 5, .9),
            SideObservation(3, 80.1, -2.0, 13.0, 5, .9),
            SideObservation(3, 20.0, -2.0, 13.0, 2, .9),
            SideObservation(3, 20.0, -2.0, 13.0, 5, .29),
            SideObservation(3, Double.NaN, -2.0, 13.0, 5, .9),
        )) assertNull(measurementFields(bad, 0))
        assertNull(measurementFields(SideObservation(3, 20.0, -2.0, 13.0, 5, .9), SIDE_MEASUREMENT_MAX_AGE_MS + 1))
        assertNull(measurementFields(SideObservation(3, 20.0, -2.0, 13.0, 5, .9), -1))
    }

    @Test fun planarRgbKeepsRedGreenBlueOrder() {
        val packed = planarRgb(intArrayOf(0xFF112233.toInt()))
        assertEquals(0x11 / 255f, packed[0], 1e-6f)
        assertEquals(0x22 / 255f, packed[1], 1e-6f)
        assertEquals(0x33 / 255f, packed[2], 1e-6f)
    }

    @Test fun speedFieldsCannotReplaceBlindspotOccupancy() {
        val blind = mapOf<String, Any>("hits" to 4, "confidence" to 0.2f, "occupied" to 0.2f)
        val speed = measurementFields(SideObservation(3, 12.0, -1.0, 14.0, 6, .95), 0)!!
        val merged = mergeSidePayload(blind, speed + mapOf("hits" to 99, "confidence" to 0.99, "occupied" to 0.99))
        assertEquals(4, merged["hits"])
        assertEquals(0.2f, merged["confidence"])
        assertEquals(0.2f, merged["occupied"])
        assertEquals(12.0, merged["distance_m"])
        assertEquals(6, merged["track_hits"])
        assertSame(blind, mergeSidePayload(blind, null))
    }

    @Test fun absoluteSpeedCompensatesAccelerationOverTheSameCaptureWindow() {
        for ((acceleration, initial) in listOf(0.0 to 10.0, 2.0 to 10.0, -2.0 to 15.0)) {
            val tracker = SideVehicleTracker()
            var result: SideObservation? = null
            repeat(11) { i ->
                val t = i * .25
                val distance = 4.0 + (15.0 - initial) * t - .5 * acceleration * t * t
                result = tracker.update(listOf(SideDetection(box, "left", distance)),
                    1_000_000_000L + i * 250_000_000L, initial + acceleration * t)["left"]
            }
            assertEquals("a=$acceleration", 15.0, result!!.absolute_speed_mps!!, 1e-8)
        }
    }

    @Test fun changingEgoSpeedUsesTrapezoidalIntegrationAtIrregularCaptureTimes() {
        val tracker = SideVehicleTracker()
        val times = listOf(0.0, .2, .55, .8, 1.1, 1.35, 1.7, 2.0)
        val egos = listOf(10.0, 11.0, 10.5, 12.0, 11.0, 10.0, 11.0, 12.0)
        var travelled = 0.0
        var result: SideObservation? = null
        times.indices.forEach { i ->
            if (i > 0) travelled += (egos[i - 1] + egos[i]) * .5 * (times[i] - times[i - 1])
            result = tracker.update(listOf(SideDetection(box, "left", 5.0 + 15.0 * times[i] - travelled)),
                1_000_000_000L + (times[i] * 1e9).roundToLong(), egos[i])["left"]
        }
        assertEquals(15.0, result!!.absolute_speed_mps!!, 1e-8)
    }

    @Test fun unavailableEgoSpeedRequiresANewContinuousWindowForAbsoluteSpeed() {
        for (missing in listOf<Double?>(null, Double.NaN, Double.POSITIVE_INFINITY)) {
            val tracker = SideVehicleTracker()
            fun frame(i: Int, ego: Double?) = tracker.update(listOf(SideDetection(box, "left", 10.0)),
                1_000_000_000L + i * 250_000_000L, ego)["left"]
            repeat(6) { frame(it, 10.0) }
            val unavailable = frame(6, missing)!!
            assertNotNull(unavailable.relative_speed_mps)
            assertNull(unavailable.absolute_speed_mps)
            for (i in 7..10) assertNull(frame(i, 10.0)!!.absolute_speed_mps)
            assertEquals(10.0, frame(11, 10.0)!!.absolute_speed_mps!!, 1e-8)
        }
    }

    @Test fun duplicateCaptureCannotChangeIntegratedMotion() {
        val tracker = SideVehicleTracker()
        var result: SideObservation? = null
        repeat(8) { i ->
            val t = 1_000_000_000L + i * 250_000_000L
            result = tracker.update(listOf(SideDetection(box, "left", 10.0)), t, 10.0)["left"]
            assertNull(tracker.update(listOf(SideDetection(box, "left", 10.0)), t, 1000.0)["left"])
        }
        assertEquals(10.0, result!!.absolute_speed_mps!!, 1e-8)
    }
}
