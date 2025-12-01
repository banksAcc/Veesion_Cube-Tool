"""Example CLI using the high level API.

Usage
-----
```
python -m cube_minimal.cli.estimate_one \
    --image cube_minimal/img/your_image.tiff \
    --camera cube_minimal/config/calib_data.npz \
    --aruco_dict 4X4_50 \
    --marker_size 0.055 \
    --cube_size 0.060 \
    --pair_strategy first \
    --out overlay.png
```

Note that images must now be provided with their full path; the ``--sample-dir``
option has been removed.
"""

import argparse
import cv2 as cv

from cube_minimal.cube_pose import estimate_cube_from_image

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--aruco_dict", default="4X4_50")
    ap.add_argument("--marker_size", type=float, required=True)
    ap.add_argument("--cube_size", type=float, required=True)
    ap.add_argument("--pair_strategy", choices=["first","max_angle"], default="first")
    ap.add_argument("--out", default=None, help="save overlay (optional)")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    result = estimate_cube_from_image(
        args.image,
        camera_npz=args.camera,
        aruco_dict=args.aruco_dict,
        marker_size=args.marker_size,
        cube_size=args.cube_size,
        pair_strategy=args.pair_strategy,
        return_overlay=bool(args.out or args.show),
    )

    print(f"markers used: {result['num_markers']}")
    print(f"tvec (m): {result['tvec']}")
    print(f"rvec (Rodrigues): {result['rvec'].reshape(-1)}")
    print(f"quat (w,x,y,z): {result['quat']}")

    if result["overlay"] is not None:
        if args.out:
            cv.imwrite(args.out, result["overlay"])
        if args.show:
            cv.imshow("overlay", result["overlay"])
            cv.waitKey(0)

if __name__ == "__main__":
    main()
