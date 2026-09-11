# IQtec Home Assistant Integration

[![CC BY-NC-SA 4.0][cc-by-nc-sa-shield]][cc-by-nc-sa]

This custom HA integration uses the [`piqtec`](https://github.com/oberth-effect/piqtec) Python library, to integrate IQtec/Kobra smart home to [Home Assistant.](https://www.home-assistant.io/)

## Setup

- Install the component to HA (copy `custom_components/iqtec` into your HA `config/custom_components`, or add this
  repository to HACS as a custom repository),
- restart Home Assistant,
- use ConfigFlow to enter the host of the IQtec controller (must be accessible from your HA node).

### Configuration parameters

| Parameter                          | Meaning                                                                                             |
|------------------------------------|-----------------------------------------------------------------------------------------------------|
| Host                               | Hostname or IP address of the controller, optionally with a port.                                    |
| Covers use short tilt to open      | Use the short tilt command instead of the full tilt cycle when opening a blind's slats.               |
| Manual climate timeout             | How long a manually set temperature is held, in 5 minute intervals (24 = two hours).                  |

## Available Platforms

- Climate (currently heating only, cooling not implemented),
- Cover (controls sunblinds, windows, etc.),
- Sensor, Binary Sensor, Switch, Number, Select: all other variables discovered by `piqtec`.

Discovered variables are numerous and largely duplicated across a typical setup, so they are **disabled by default**.
Enable the ones you need from the device page. Entities already enabled from an earlier version keep their state.

## Data updates

The controller is polled every 15 seconds over its local HTTP interface. A command sent from Home Assistant requests an
immediate refresh, so the UI does not wait for the next poll.

The controller's request and reply buffers are small and overflow silently; `piqtec` batches the whole house into as few
requests as those limits allow (five on a medium-sized installation).

## Known limitations

- Cooling is not implemented; climate entities expose heating only.
- The controller has no authentication, so anything that can reach it on the network can control it.
- Whether a variable is writable is inferred from an undocumented `access` attribute, so a few entities may be
  classified as sensors when they are in fact settable, or the other way round.

## Removal

Delete the integration from **Settings → Devices & Services**, then remove `custom_components/iqtec` (or uninstall it
from HACS).

## Development

```shell
pip install -r requirements-test.txt
pytest
```

## License

This work is licensed under a
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License][cc-by-nc-sa].

[![CC BY-NC-SA 4.0][cc-by-nc-sa-image]][cc-by-nc-sa]

Relicensing is available upon request.

[cc-by-nc-sa]: http://creativecommons.org/licenses/by-nc-sa/4.0/

[cc-by-nc-sa-image]: https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png

[cc-by-nc-sa-shield]: https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg
