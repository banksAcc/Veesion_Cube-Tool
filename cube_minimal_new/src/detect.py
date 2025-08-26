from typing import List
import numpy as np
import cv2

class Detection:
    def __init__(self, ids, corners):
        self.ids = ids   # (N,1) int32 or None
        self.corners = corners  # list of N arrays (4,1,2)


def get_dictionary():
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)


def detect_markers(gray) -> Detection:
    params = cv2.aruco.DetectorParameters()
    # Corner refine semplice (manteniamo perché è utile e a costo minimo)
    if hasattr(cv2.aruco, 'CornerRefineMethod') and hasattr(cv2.aruco.CornerRefineMethod, 'APRILTAG'):
        params.cornerRefinementMethod = cv2.aruco.CornerRefineMethod.APRILTAG
    else:
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

    detector = cv2.aruco.ArucoDetector(get_dictionary(), params)
    corners, ids, _ = detector.detectMarkers(gray)

    if ids is not None and len(ids) > 0:
        term = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
        for i in range(len(corners)):
            cv2.cornerSubPix(gray, corners[i], (5,5), (-1,-1), term)

    return Detection(ids, corners)