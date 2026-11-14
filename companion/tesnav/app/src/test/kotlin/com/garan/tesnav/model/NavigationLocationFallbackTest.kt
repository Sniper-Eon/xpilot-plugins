package com.garan.tesnav.model

import org.junit.Assert.*
import org.junit.Test

/** Failure contracts: a qualified vehicle fix beats phone; phone is used only when the vehicle
 * fix is stale or unavailable; bad inputs, rollback, duplicate reinjection and
 * inactive/clock reversal fail closed. */
class NavigationLocationFallbackTest {
    private fun fix(t: Long = 100) = NavigationLocationObservation("epoch", 10_000 + t, t, 0,
        32.0, 121.0, 5.0, 0.0, 90.0, NavigationCoordinateSystem.GCJ02, true)
    private fun NavigationLocationFallback.at(t: Long, phone: NavigationLocationObservation?,
        vehicle: NavigationLocationObservation?, active: Boolean = true) = select(phone, vehicle, active, t, 10_000 + t)

    @Test fun `vehicle preferred and phone used only when vehicle expires`() {
        val s = NavigationLocationFallback()
        val primary = s.at(100, fix(), fix())
        assertEquals(NavigationLocationSource.VEHICLE, primary.source)
        assertEquals("vehiclePrimary", primary.reason)
        assertNotNull(primary.vehicleFixToInject)
        assertNull(primary.phoneFixToInject)
        val fallback = s.at(3100, fix(3100), fix())
        assertEquals(NavigationLocationSource.PHONE, fallback.source)
        assertEquals("phoneFallback", fallback.reason)
        assertNull(fallback.phoneFixToInject)
        assertNull(fallback.vehicleFixToInject)
        val renewed = s.at(3200, null, fix(3200))
        assertEquals(NavigationLocationSource.VEHICLE, renewed.source)
        assertEquals("vehiclePrimary", renewed.reason)
        assertNotNull(renewed.vehicleFixToInject)
        val duplicate = s.at(3300, null, fix(3200).copy(receivedElapsedMs = 3300))
        assertEquals(NavigationLocationSource.VEHICLE, duplicate.source)
        assertEquals("awaitingNewVehicleFix", duplicate.reason)
        assertNull(duplicate.vehicleFixToInject)
        assertEquals(NavigationLocationSource.NONE, s.at(6200, null, fix(3200)).source)
    }

    @Test fun `phone is used immediately when vehicle is unavailable`() {
        val s = NavigationLocationFallback()
        s.at(100, null, fix())
        val both = s.at(1100, fix(1100), fix(1100))
        assertEquals(NavigationLocationSource.VEHICLE, both.source)
        assertEquals("vehiclePrimary", both.reason)
        assertNotNull(both.vehicleFixToInject)
        val absent = s.at(2100, fix(2100), null)
        assertEquals(NavigationLocationSource.PHONE, absent.source)
        assertEquals("phoneFallback", absent.reason)
        assertEquals(NavigationLocationSource.PHONE, s.at(3100, fix(1100), null).source)
        assertEquals(NavigationLocationSource.PHONE, s.at(3100, fix(3100), null).source)
    }

    @Test fun `unverified and invalid vehicle observations never become fallback`() {
        val f = fix()
        for (bad in listOf(f.copy(measurementTimeVerified = false), f.copy(accuracyM = null),
            f.copy(accuracyM = 51.0), f.copy(accuracyM = Double.NaN), f.copy(speedMps = null),
            f.copy(speedMps = -1.0), f.copy(bearingDeg = 360.0), f.copy(latitude = 91.0),
            f.copy(longitude = Double.NaN), f.copy(coordinateSystem = NavigationCoordinateSystem.UNKNOWN),
            f.copy(measuredAtMs = 10_101), f.copy(receivedElapsedMs = 101), f.copy(ageAtReceiptMs = 3000),
            f.copy(sourceEpoch = ""))) {
            assertEquals(NavigationLocationSource.NONE, NavigationLocationFallback().at(100, null, bad).source)
        }
    }

    @Test fun `transport age cannot be refreshed by changing receipt or advancing heartbeat`() {
        val s = NavigationLocationFallback()
        assertEquals(NavigationLocationSource.VEHICLE, s.at(100, null, fix().copy(ageAtReceiptMs = 2000)).source)
        assertEquals(NavigationLocationSource.NONE, s.at(1100, null, fix().copy(ageAtReceiptMs = 2000)).source)
        assertEquals(NavigationLocationSource.NONE, s.at(3100, null, fix().copy(receivedElapsedMs = 3100)).source)
    }

    @Test fun `stop reset clock reversal and vehicle timestamp reversal fail closed`() {
        val s = NavigationLocationFallback()
        s.at(200, null, fix(200))
        assertEquals("vehicleTimeReversed", s.at(201, null, fix(100)).reason)
        assertEquals("clockInvalid", s.at(199, null, fix(199)).reason)
        assertEquals("inactive", s.at(300, fix(300), fix(300), active = false).reason)
        assertEquals(NavigationLocationSource.PHONE, s.at(301, fix(301), null).source)
    }

    @Test fun `fresh vehicle remains primary without injecting phone updates`() {
        val s = NavigationLocationFallback()
        s.at(100, null, fix())
        val withPhone = s.at(1000, fix(1000), fix(1000))
        assertEquals(NavigationLocationSource.VEHICLE, withPhone.source)
        assertEquals("vehiclePrimary", withPhone.reason)
        assertNotNull(withPhone.vehicleFixToInject)
        assertNull(withPhone.phoneFixToInject)
        assertNotNull(s.at(2000, null, fix(2000)).vehicleFixToInject)
        val stillVehicle = s.at(3000, fix(3000), fix(3000))
        assertEquals(NavigationLocationSource.VEHICLE, stillVehicle.source)
        assertEquals("vehiclePrimary", stillVehicle.reason)
        assertNotNull(stillVehicle.vehicleFixToInject)
        assertNull(stillVehicle.phoneFixToInject)
        assertEquals(NavigationLocationSource.VEHICLE, s.at(4000, fix(4000), fix(4000)).source)
        assertEquals(NavigationLocationSource.VEHICLE, s.at(5000, fix(5000), fix(5000)).source)
    }

    @Test fun `invalid phone falls back without weakening qualification or freshness`() {
        for (bad in listOf(fix().copy(accuracyM = 51.0), fix().copy(measuredAtMs = 10101),
            fix().copy(measurementTimeVerified = false), fix().copy(ageAtReceiptMs = 3000),
            fix().copy(coordinateSystem = NavigationCoordinateSystem.UNKNOWN), fix().copy(latitude = Double.NaN))) {
            val result = NavigationLocationFallback().at(100, bad, fix())
            assertEquals(NavigationLocationSource.VEHICLE, result.source)
            assertNotNull(result.vehicleFixToInject)
        }
    }
    @Test fun `vehicle timestamp reversal returns no fix even when phone is qualified`() {
        val s = NavigationLocationFallback()
        s.at(200, null, fix(200))
        val blocked = s.at(201, fix(201), fix(100))
        assertEquals(NavigationLocationSource.NONE, blocked.source)
        assertEquals("vehicleTimeReversed", blocked.reason)
        assertNull(blocked.vehicleFixToInject)
        assertNull(blocked.phoneFixToInject)
    }

    @Test fun `raw phone candidate is independent and stale external SDK echo cannot recover it`() {
        val raw = fix().copy(sourceEpoch="phone-gps", coordinateSystem=NavigationCoordinateSystem.WGS84)
        val sdk = fix().copy(sourceEpoch="phone-sdk")
        assertSame(raw, phoneLocationCandidate(raw, sdk, false, 100, 10100))
        assertSame(sdk, phoneLocationCandidate(raw.copy(accuracyM=51.0), sdk, false, 100, 10100))
        assertNull(phoneLocationCandidate(null, sdk, true, 100, 10100))
        assertNull(phoneLocationCandidate(sdk, sdk, true, 100, 10100))
        assertNull(phoneLocationCandidate(raw, sdk, true, 3100, 13100))
    }
    @Test fun `raw phone injection is deduplicated and reversed or unverified measurements are refused`() {
        val s = NavigationLocationFallback()
        val raw = fix(200).copy(sourceEpoch="phone-gps", coordinateSystem=NavigationCoordinateSystem.WGS84)
        assertEquals(raw, s.at(200, raw, null).phoneFixToInject)
        assertNull(s.at(201, raw, null).phoneFixToInject)
        assertEquals("phoneTimeReversed", s.at(202, raw.copy(measuredAtMs=10100), null).reason)
        assertEquals(NavigationLocationSource.NONE, NavigationLocationFallback().at(200,
            raw.copy(measurementTimeVerified=false, observationTimeOnly=true), null).source)
    }
}
