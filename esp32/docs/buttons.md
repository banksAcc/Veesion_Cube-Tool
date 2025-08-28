# Button Handling

`Buttons.h` implements a simple event model for button presses:

- `fell` – HIGH→LOW transition (button pressed)
- `rose` – LOW→HIGH transition (button released)
- `longPress` – emitted once when the button stays pressed for `longMs`
- `isDown` – current state (LOW when pressed)

Example with `longMs = 500`:

```
time (ms): 0    50   550   800
level    : HIGH \____LOW____/ HIGH
              fell longPress  rose
```

`longPress` is fired only once for each press when `isDown` remains LOW for the
specified duration.

