"""Sonoff ZG-303Z-z (pvvx ZigbeeTLc firmware, raw-ADC build).

Exposes:
  - Temperature offset / Humidity offset / Measurement interval  (HVAC UI cluster 0x0204)
  - Soil raw ADC (0xF000) and Soil ADC reference / diode (0xF001) on the EP2
    relative-humidity cluster, for DIY calibration in Home Assistant.

Requires the custom firmware built with the raw_adc/adc_diode attributes.
Based on https://github.com/pvvx/ZigbeeTLc (zhaquirks/custom/zigbeetlc.py).
"""

from zigpy.quirks.v2 import QuirkBuilder
from zigpy.quirks.v2.homeassistant import PERCENTAGE, UnitOfTemperature, UnitOfTime
from zigpy.quirks.v2.homeassistant.sensor import SensorStateClass
import zigpy.types as t
from zigpy.zcl import ClusterType
from zigpy.zcl.clusters.hvac import UserInterface
from zigpy.zcl.clusters.measurement import RelativeHumidity
from zigpy.zcl.foundation import ZCLAttributeDef

from zhaquirks import CustomCluster


class CustomUserInterfaceCluster(CustomCluster, UserInterface):
    """pvvx ZigbeeTLc config attributes on cluster 0x0204."""

    class AttributeDefs(UserInterface.AttributeDefs):
        temperature_offset = ZCLAttributeDef(
            id=0x0100, type=t.int16s, access="rw", is_manufacturer_specific=True
        )
        humidity_offset = ZCLAttributeDef(
            id=0x0101, type=t.int16s, access="rw", is_manufacturer_specific=True
        )
        measurement_interval = ZCLAttributeDef(
            id=0x0107, type=t.uint8_t, access="rw", is_manufacturer_specific=True
        )


class SoilRawCluster(CustomCluster, RelativeHumidity):
    """EP2 relative-humidity (soil) cluster + raw ADC / diode-reference attributes."""

    class AttributeDefs(RelativeHumidity.AttributeDefs):
        raw_adc = ZCLAttributeDef(id=0xF000, type=t.uint16_t, access="rp")
        adc_diode = ZCLAttributeDef(id=0xF001, type=t.uint16_t, access="rp")


(
    QuirkBuilder("Fortify", "Soil-Moisture")
    .removes(CustomUserInterfaceCluster.cluster_id, cluster_type=ClusterType.Client)
    .adds(CustomUserInterfaceCluster)
    .replaces(SoilRawCluster, endpoint_id=2)
    .number(
        CustomUserInterfaceCluster.AttributeDefs.temperature_offset.name,
        CustomUserInterfaceCluster.cluster_id,
        min_value=-327.67,
        max_value=327.67,
        step=0.01,
        unit=UnitOfTemperature.CELSIUS,
        translation_key="temperature_offset",
        fallback_name="Temperature offset",
        multiplier=0.01,
        mode="box",
    )
    .number(
        CustomUserInterfaceCluster.AttributeDefs.humidity_offset.name,
        CustomUserInterfaceCluster.cluster_id,
        min_value=-327.67,
        max_value=327.67,
        step=0.01,
        unit=PERCENTAGE,
        translation_key="humidity_offset",
        fallback_name="Humidity offset",
        multiplier=0.01,
        mode="box",
    )
    .number(
        CustomUserInterfaceCluster.AttributeDefs.measurement_interval.name,
        CustomUserInterfaceCluster.cluster_id,
        min_value=3,
        max_value=255,
        unit=UnitOfTime.SECONDS,
        translation_key="measurement_interval",
        fallback_name="Measurement interval",
        mode="box",
    )
    .sensor(
        SoilRawCluster.AttributeDefs.raw_adc.name,
        SoilRawCluster.cluster_id,
        endpoint_id=2,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="soil_raw_adc",
        fallback_name="Soil raw ADC",
    )
    .sensor(
        SoilRawCluster.AttributeDefs.adc_diode.name,
        SoilRawCluster.cluster_id,
        endpoint_id=2,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="soil_adc_reference",
        fallback_name="Soil ADC reference",
    )
    .add_to_registry()
)
