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

## Calendars

Every heating calendar is exposed as a sensor whose state is the calendar name
and whose attributes carry the whole schedule:

```yaml
calendar_type: TEMPERATURE      # or BLIND, ON_OFF, VALUE, ON_OFF2
levels: 3                       # 2 for the ON_OFF types
temperatures: [14, 17, 20, 27, 25, 22]
days:
  - name: monday
    as_monday: false
    transitions: [[0, 1], [72, 2], [119, 1], [182, 2], [240, 1]]
```

A transition is `[time, level]`, where time counts 5 minute steps from midnight
(0-287) and level is `0` Nobody, `1` Night or `2` Day. The first transition of a
day is pinned to midnight and a day holds at most 7.

Write them back with the `iqtec.set_calendar` action. Every field is optional
except the calendar itself, so a rename does not have to resend the schedule:

```yaml
action: iqtec.set_calendar
data:
  calendar_id: sensor.calendar_0
  name: Weekdays
  temperatures: [14, 17, 21, 27, 25, 22]
  days:
    - transitions: [[0, 1], [72, 2], [240, 1]]
      as_monday: false
    # ... eight days in all, Monday first, "day 8" last
```

For a drag-and-drop editor, install
[the calendar card](https://github.com/oberth-effect/iqtec-ha-calendar-card).

### Telling a calendar what it really is

`data.xml` types several calendars `TEMPERATURE` even when they drive something
on or off. The OEM application guesses from the calendar's name, matching Czech
keywords like *cirkulace* or *zavlaha*; this integration asks instead.

**Settings → Devices & Services → IQtec → Configure** offers a display type per
calendar. It changes only how the calendar is presented — `levels`,
`level_names`, the calendar entity's event summaries and what the card draws.
The controller's own type stays visible as `calendar_type`, and nothing is
written to the controller.

| Display type | Lanes | Levels shown as          |
|--------------|-------|--------------------------|
| `TEMPERATURE`| 3     | Nobody / Night / Day, with setpoints |
| `VALUE`      | 3     | Nobody / Night / Day     |
| `BLIND`      | 3     | Down / Tilted / Up       |
| `ON_OFF`, `ON_OFF2` | 2 | Off / On              |

A calendar always *stores* three levels, so when one is shown as two, Night is
drawn together with Off, exactly as the controller's `OutNobody`, `OutNight` and
`OutDay` outputs behave.

### Schedules as Home Assistant calendars

Each schedule also appears as a `calendar` entity, so it can drive automations:

```yaml
triggers:
  - trigger: calendar
    entity_id: calendar.generalprofile
    event: start
    offset: "-00:30:00"       # half an hour before a period begins
conditions:
  - condition: template
    value_template: "{{ trigger.calendar_event.summary.startswith('Day') }}"
```

Events run back to back, one per level period, summarised as `Day · 20.0 °C`.
`calendar.get_events` reads any window, and days marked "follows Monday" are
resolved for you. "Day 8" has no place on a calendar, since the controller
selects it through an input rather than a date, so it is left out.

These calendars are **read-only, and show what is programmed rather than what is
happening**: holiday mode, a room switched off and a manual correction all
override the schedule without changing it. Editing goes through
`iqtec.set_calendar` or the card.

## Data updates

The controller is polled every 15 seconds over its local HTTP interface, and
calendars every 5 minutes because only an editor changes them. A command sent from Home Assistant requests an
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

## Versioning

This integration and [`piqtec`](https://github.com/oberth-effect/piqtec) share a
version number, and `manifest.json` pins the matching release exactly. A release
of one is a release of both, even when only one of them changed, so the version
you see in Home Assistant always names the library it was built against.

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
