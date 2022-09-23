# HomeAssistant - Polyaire AirTouch 4 Integration

Custom integration to add an AirTouch 4 AC Controller (with local push)

## Installation:

Copy contents of custom_components/polyaire/ to custom_components/polyaire/ in your Home Assistant config folder.

## Installation using HACS:

HACS is a community store for Home Assistant. After installation, add this repository to HACS and install the polyaire integration.


## Requirements

AirTouch 4 console IP address is required when installing the integration.

## Services

This custom component creates:
* one device for each AC unit installed
* one climate entity for each AC unit installed
* one fan entity for each group defined, which controls the zone damper
* one climate entity for each group with ITC installed, which controls the zone temperature

For each group with ITC, the fan entity can switch between 2 profiles (and Turbo if setup):
* Damper - which allows direct damper control via the fan
* ITC - which allows for temperature control using the ITC
* Turbo - turbo for the group


Enjoy!
---
If you found this useful, say _Thank You!_ [with a beer.](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=mihailescu2m%40gmail%2Ecom&lc=AU&item_name=memeka&item_number=odroid&currency_code=AUD&bn=PP%2DDonationsBF%3Abtn_donate_LG%2Egif%3ANonHosted)
