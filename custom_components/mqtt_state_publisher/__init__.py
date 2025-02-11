"""Publish simple item state changes via MQTT."""

import logging

import voluptuous as vol
from homeassistant.components import mqtt
from homeassistant.components.mqtt.util import valid_publish_topic
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, EVENT_STATE_CHANGED
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.entityfilter import (
    INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA,
    convert_include_exclude_filter,
)
from homeassistant.helpers.start import async_at_start
from homeassistant.helpers.typing import ConfigType

CONF_BASE_TOPIC = "base_topic"

DOMAIN = "mqtt_state_publisher"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA.extend(
            {
                vol.Required(CONF_BASE_TOPIC): valid_publish_topic,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the MQTT state feed."""
    # Make sure MQTT integration is enabled and the client is available
    if not await mqtt.async_wait_for_mqtt_client(hass):
        _LOGGER.error("MQTT integration is not available")
        return False

    conf: ConfigType = config[DOMAIN]
    publish_filter = convert_include_exclude_filter(conf)
    base_topic: str = conf[CONF_BASE_TOPIC]

    if not base_topic.endswith("/"):
        base_topic = f"{base_topic}/"

    async def _state_publisher(evt: Event[EventStateChangedData]) -> None:
        entity_id: str = evt.data["entity_id"]
        new_state: State | None = evt.data["new_state"]

        if new_state is None:
            return

        payload_json = new_state.as_dict_json

        mybase = f"{base_topic}{entity_id.replace('.', '/')}/"

        await mqtt.async_publish(hass, f"{mybase}state", payload_json, 1)

    @callback
    def _ha_started(hass: HomeAssistant) -> None:
        @callback
        def _event_filter(event_data: EventStateChangedData) -> bool:
            entity_id = event_data["entity_id"]
            new_state = event_data["new_state"]
            if new_state is None:
                return False

            return publish_filter(entity_id)

        callback_handler = hass.bus.async_listen(
            EVENT_STATE_CHANGED, _state_publisher, _event_filter
        )

        @callback
        def _ha_stopping(_: Event) -> None:
            callback_handler()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _ha_stopping)

    async_at_start(hass, _ha_started)

    return True
