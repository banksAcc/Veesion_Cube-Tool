# Sample dataset

Sample images for exercising the `cube_minimal` API/CLI.
The `example_*.png` files show a cube with ArUco markers ready for pose estimation.

## Add new images

1. Copy new images into this folder (`cube_minimal/data/`).
2. Use descriptive filenames (e.g. `new_01.png`).
3. Call the CLI with the full image path via `--image`:

```bash
python -m cube_minimal.cli.estimate_one --image cube_minimal/data/new_01.png --camera cube_minimal/config/calib_data.npz --marker_size 0.022 --cube_size 0.06
```

Adjust `--marker_size` (marker side length in meters) and `--cube_size` (cube edge length in meters) to match your scene. Example calibration files live in `cube_minimal/config/` (e.g. `calib_data.npz`).

Images can also be consumed directly from the API by reusing the same absolute paths.

## Quick try

1. Copy or export a new test image into `cube_minimal/data/`. Ensure the markers are clearly visible and that the physical dimensions match the `marker_size` and `cube_size` values you will pass.
2. Run the CLI to estimate the pose and optionally display/save the result:

```bash
python -m cube_minimal.cli.estimate_one --image cube_minimal/data/example_01.png --camera cube_minimal/config/calib_data.npz --marker_size 0.022 --cube_size 0.06 --show --out cube_minimal/data/example_01_result.json
```

- `--show` opens a window that overlays the projected cube onto the input image.
- `--out` stores pose matrices, error metrics, and other outputs in the provided JSON file.

3. From Python code you can perform the same estimation using the high-level helper:

```python
from cube_minimal.cli import estimate_cube_from_image

result = estimate_cube_from_image(
    image_path="cube_minimal/data/example_01.png",
    camera_path="cube_minimal/config/calib_data.npz",
    marker_size=0.022,
    cube_size=0.06,
    show=True,
)
print(result.pose)
```

`estimate_cube_from_image` returns an object with the pose transform and diagnostic details, reusing the same images and calibration files as the CLI.

To plug these images into the PC pipeline in simulated mode, see the [main README](../README.md).
