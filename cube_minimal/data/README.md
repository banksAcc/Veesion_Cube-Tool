# Sample dataset

Immagini di esempio per testare l'API/CLI del modulo `cube_minimal`.
Le immagini `example_*.png` mostrano un cubo con marker ArUco già pronto per la stima di posa.

## Aggiungere nuove immagini

1. Copia le nuove immagini in questa cartella (`cube_minimal/data/`).
2. Usa nomi descrittivi (es. `nuovo_01.png`).
3. Richiama l'immagine dalla CLI specificando il percorso completo con l'opzione `--image`:

```bash
python -m cube_minimal.src.cli.estimate_one --image cube_minimal/data/nuovo_01.png --camera <camera.npz> --marker_size <m> --cube_size <m>
```

Le immagini possono anche essere richiamate direttamente nell'API usando il percorso completo.
