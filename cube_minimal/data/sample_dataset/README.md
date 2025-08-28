# Sample dataset

Immagini di esempio per testare l'API/CLI del modulo `cube_minimal`.
Le immagini `example_*.png` mostrano un cubo con marker ArUco già pronto per la stima di posa.

## Aggiungere nuove immagini

1. Copia le nuove immagini in questa cartella (`cube_minimal/data/sample_dataset/`).
2. Usa nomi descrittivi (es. `nuovo_01.png`).
3. Richiama l'immagine dalla CLI usando l'opzione `--sample-dir`:

```bash
python -m cube_minimal.src.cli.estimate_one --sample-dir cube_minimal/data/sample_dataset --image nuovo_01.png --camera <camera.npz> --marker_size <m> --cube_size <m>
```

Le immagini possono anche essere richiamate direttamente nell'API passando `sample_dir`.
