# Gestione pulsanti

Il file `Buttons.h` implementa il modello di eventi dei pulsanti:

- `fell` – transizione HIGH→LOW (pressione).
- `rose` – transizione LOW→HIGH (rilascio).
- `longPress` – generato quando il pulsante resta premuto per almeno `longMs` ms.
- `isDown` – stato corrente del pulsante (LOW quando premuto).

Esempio con `longMs = 500`:

```
time (ms): 0    50   550   800
level    : HIGH \____LOW____/ HIGH
              fell longPress  rose
```

`longPress` viene emesso una sola volta per ogni pressione quando `isDown` 
resta LOW per il tempo indicato.
