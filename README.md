# IQtec Home Assistant Integration

[![CC BY-NC-SA 4.0][cc-by-nc-sa-shield]][cc-by-nc-sa]

This custom HA integration uses the [`piqtec`](https://github.com/oberth-effect/piqtec) Python library, to integrate IQtec/Kobra smart home to [Home Assistant.](https://www.home-assistant.io/)

## Setup
- Install the compoponent to HA,
- use ConfigFlow to enter the host of the IqTec controller (must be accessible from yout HA node).

## Available Platforms

- Climate (currently heating only, cooling not implemented),
- Cover (controls sunblinds, windows, etc.),
- Sensor, Binary Sensor, Switch: all other devices discovered by `piqtec`. You may want to disable bunch of them as they are meaningless/duplicated across the setup.

## License

This work is licensed under a
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License][cc-by-nc-sa].

[![CC BY-NC-SA 4.0][cc-by-nc-sa-image]][cc-by-nc-sa]

Relicensing is available upon request.

[cc-by-nc-sa]: http://creativecommons.org/licenses/by-nc-sa/4.0/

[cc-by-nc-sa-image]: https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png

[cc-by-nc-sa-shield]: https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg