"""Constants for the ANWB Energie integration."""

from datetime import time, timedelta

DOMAIN = "anwb_energie_tarieven"
# Core has a virtual `anwb_energie` integration, so the domain differs from the
# entity id prefix.
ENTITY_ID_PREFIX = "anwb_energie"
ATTRIBUTION = "Tarieven van ANWB Energie (onofficiële API)"

COMMODITY_ELECTRICITY = "electricity"
COMMODITY_GAS = "gas"
COMMODITIES = (COMMODITY_ELECTRICITY, COMMODITY_GAS)

PRICE_ALL_IN = "all_in"
PRICE_MARKET = "market"

# Prices for the next day are published between 13:00 and 15:00 (Amsterdam);
# keep retrying until 16:00 to allow for delays.
PUBLISH_WINDOW_START = time(13, 0)
PUBLISH_WINDOW_END = time(16, 0)
UPDATE_INTERVAL = timedelta(hours=1)
RETRY_INTERVAL = timedelta(minutes=10)
# After a failed request the last prices stay in use; try again soon.
FAILURE_RETRY_INTERVAL = timedelta(minutes=5)
