# cube_pose – Stima posa cubo da marker ArUco

Mini-moduli riutilizzabili per:
- rilevare marker ArUco,
- stimare la posa dei singoli marker (IPPE SQUARE),
- ricostruire la posa di un **cubo** (centro + orientazione) usando 1..3 marker visibili,
- disegnare overlay di diagnostica.

> **Convenzione**: la Z del **marker** (asse blu) esce dal piano del marker (verso la camera);  
> la Z del **cubo** è definita **uscente dal cubo** e per costruzione è `-Z_marker` di una delle facce.

## API principale

```python
from cube_minimal.cube_pose.api import estimate_cube_from_image

res = estimate_cube_from_image(
    image_or_path="cube_minimal/img/frame.tiff",
    camera_npz="cube_minimal/config/calib_data.npz",
    aruco_dict="4X4_50",
    marker_size=0.055,  # metri (lato del quadrato nero!)
    cube_size=0.060,    # metri
    pair_strategy="first",    # oppure "max_angle"
    return_overlay=True
)

tvec = res["tvec"]   # (3,) centro cubo in camera (m)
rvec = res["rvec"]   # (3,1) Rodrigues del cubo
R    = res["R"]      # (3,3) matrice di rotazione
quat = res["quat"]   # (4,) w,x,y,z
img  = res["overlay"]
```

## CLI di esempio 1

```
python -m cube_minimal.cli.estimate_one   --image cube_minimal/img/your_image.tiff   --camera cube_minimal/config/calib_data.npz   --aruco_dict 4X4_50   --marker_size 0.055   --cube_size 0.060   --pair_strategy first   --out overlay.png --show
```

## CLI di esempio 2

```
 python -m cube_minimal.cli.estimate_one --image dataset\test_01\Basler_acA2040-35gm__23324651__20250826_151237703_0000.tiff --camera config/calib_data.npz --aruco_dict 4X4_50 --marker_size 0.053 --cube_size 0.063 --pair_strategy first --out overlay.png --show
```

## Strategia di stima (riassunto)

1. **Detection** ArUco → corner 2D (ordine: tl, tr, br, bl).
2. **Pose marker** con `SOLVEPNP_IPPE_SQUARE` (scelgo la soluzione a errore minimo).
3. **Centro cubo** da singolo marker: `t_marker - Z_marker * L/2`.
4. **Centro cubo finale** = media dei centri (1..3 marker).
5. **Orientazione cubo**:
   - `>=2` marker: allinea due facce → `Z_cubo = -Z_marker_1`, `X_cubo = proj(-Z_marker_2 ⟂ Z_cubo)`, `Y_cubo = Z×X`.
   - `1` marker: `Z_cubo = -Z_marker`, `X/Y` dal piano della stessa faccia.
6. Output: `tvec`, `rvec` (Rodrigues), `R`, `quat`.

## Requisiti
- `opencv-python`
- `numpy`

## Note importanti
- `marker_size` deve essere il **lato del quadrato nero** (no bordo bianco).
- Il `.npz` della camera deve contenere `K`/`cameraMatrix` e `dist`/`distCoeffs`.
- Se usi più marker e vuoi più robustezza, prova `pair_strategy="max_angle"`.

## TODO (per futuri rilasci come libreria)
- Packaging con `pyproject.toml`.
- Test automatici (unit per `cube_pose`).
- Ponderazione/robustezza su centro (mediana / pesi ∝ area marker).
- Metriche di coerenza (angolo tra normali e deviazione riproiezione).
