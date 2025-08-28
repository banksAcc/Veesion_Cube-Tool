import os
import math
import sys
import traceback
import cv2
import numpy as np

# -------------------------------
# Main parameters
# -------------------------------
IDS = [0, 1, 2, 3, 4, 5]   # 6 valid IDs for DICT_4X4_50 (0..49)
MARKER_MM = 75             # marker side in millimetres
DPI = 300                  # print resolution
OUT_DIR = "aruco_4x4_50_75mm"

# Optional A4 layout
MAKE_A4 = True
A4_MARGIN_MM = 12
A4_GAP_MM = 10

# -------------------------------
# Utility / logging
# -------------------------------
def log(msg):
    print(msg, flush=True)


def mm_to_px(mm, dpi=DPI):
    """Convert millimetres to pixels for the given DPI."""
    return int(round(mm / 25.4 * dpi))


def ensure_aruco():
    """Verify that the required ArUco module and constants are available."""
    if not hasattr(cv2, "aruco"):
        raise ImportError("cv2.aruco module not found. Install: pip install opencv-contrib-python")
    if not hasattr(cv2.aruco, "DICT_4X4_50"):
        raise ImportError("DICT_4X4_50 constant missing in this OpenCV build.")
    return True


def get_dict_4x4_50():
    """Return the DICT_4X4_50 predefined dictionary regardless of OpenCV version."""
    if hasattr(cv2.aruco, "getPredefinedDictionary"):
        return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    else:
        return cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)


def render_marker(dictionary, marker_id, side_px, border_bits=1):
    """Render an ArUco marker image using the available OpenCV API."""
    if hasattr(cv2.aruco, "generateImageMarker"):
        img = np.zeros((side_px, side_px), dtype=np.uint8)
        cv2.aruco.generateImageMarker(dictionary, marker_id, side_px, img, borderBits=border_bits)
        return img
    if hasattr(cv2.aruco, "drawMarker"):
        return cv2.aruco.drawMarker(dictionary, marker_id, side_px, border_bits=border_bits)

    raise RuntimeError("Neither generateImageMarker nor drawMarker available in this OpenCV build.")


def save_png(img, path):
    """Save a grayscale image to PNG, raising on error."""
    ok = cv2.imwrite(path, img)
    if not ok:
        raise IOError(f"cv2.imwrite failed to save: {path}")


# -------------------------------
# Single marker generation
# -------------------------------
def generate_markers(ids=IDS, marker_mm=MARKER_MM, dpi=DPI, out_dir=OUT_DIR, white_border_mm=5):
    """Generate individual marker PNGs for the given IDs."""
    ensure_aruco()
    os.makedirs(out_dir, exist_ok=True)
    log(f"[INFO] Output dir: {os.path.abspath(out_dir)}")

    marker_px = mm_to_px(marker_mm, dpi)
    white_border_px = mm_to_px(white_border_mm, dpi) if white_border_mm > 0 else 0
    ar_dict = get_dict_4x4_50()

    paths = []
    for mid in ids:
        log(f"[GEN] Marker ID {mid} ({marker_px} px)")
        marker = render_marker(ar_dict, mid, marker_px, border_bits=1)

        if white_border_px > 0:
            marker = cv2.copyMakeBorder(
                marker, white_border_px, white_border_px, white_border_px, white_border_px,
                borderType=cv2.BORDER_CONSTANT, value=255,
            )

        fname = f"aruco_4x4_50_id{mid}_{marker_mm}mm.png"
        out_path = os.path.join(out_dir, fname)
        save_png(marker, out_path)
        log(f"[OK] Saved: {out_path}")
        paths.append(out_path)
    return paths


# -------------------------------
# A4 layout (2x3)
# -------------------------------
def make_a4_sheet(ids=IDS, marker_mm=MARKER_MM, dpi=DPI, margin_mm=A4_MARGIN_MM, gap_mm=A4_GAP_MM, out_dir=OUT_DIR):
    """Place multiple markers on an A4 sheet (2 columns × 3 rows)."""
    ensure_aruco()
    os.makedirs(out_dir, exist_ok=True)

    a4_w_px = mm_to_px(210, dpi)
    a4_h_px = mm_to_px(297, dpi)
    page = np.full((a4_h_px, a4_w_px), 255, dtype=np.uint8)

    margin_px = mm_to_px(margin_mm, dpi)
    gap_px = mm_to_px(gap_mm, dpi)
    marker_px = mm_to_px(marker_mm, dpi)

    total_w_mm = 2 * marker_mm + gap_mm + 2 * margin_mm
    total_h_mm = 3 * marker_mm + 2 * gap_mm + 2 * margin_mm
    if total_w_mm > 210 or total_h_mm > 297:
        raise ValueError(f"Too big for A4 with these margins/gap: {total_w_mm:.1f}×{total_h_mm:.1f} mm")

    ar_dict = get_dict_4x4_50()

    positions = []
    for r in range(3):          # 3 rows
        for c in range(2):      # 2 columns
            x = margin_px + c * (marker_px + gap_px)
            y = margin_px + r * (marker_px + gap_px)
            positions.append((x, y))

    use_ids = (ids * math.ceil(6 / max(1, len(ids))))[:6]
    log(f"[A4] Layout IDs: {use_ids}")

    for (mid, (x, y)) in zip(use_ids, positions):
        marker = render_marker(ar_dict, mid, marker_px, border_bits=1)
        page[y:y + marker_px, x:x + marker_px] = marker

    out_path = os.path.join(out_dir, f"aruco_4x4_50_A4_{marker_mm}mm.png")
    save_png(page, out_path)
    log(f"[OK] Saved A4 sheet: {out_path}")
    return out_path


# -------------------------------
# Execution
# -------------------------------
if __name__ == "__main__":
    log(f"[INFO] OpenCV: {cv2.__version__}")
    log(
        f"[INFO] aruco.generateImageMarker? {hasattr(cv2.aruco,'generateImageMarker')}  |  "
        f"aruco.drawMarker? {hasattr(cv2.aruco,'drawMarker')}"
    )
    try:
        paths = generate_markers(IDS, MARKER_MM, DPI, OUT_DIR, white_border_mm=5)
        for p in paths:
            log(f"[FILE] {p}")
        if MAKE_A4:
            a4 = make_a4_sheet(IDS, MARKER_MM, DPI, A4_MARGIN_MM, A4_GAP_MM, OUT_DIR)
            log(f"[FILE] {a4}")
        log("[DONE] Print at 100% (scale 1:1) to obtain 75×75 mm markers.")
    except Exception as e:
        log("[ERROR] Exception during generation:")
        traceback.print_exc()
        sys.exit(1)
