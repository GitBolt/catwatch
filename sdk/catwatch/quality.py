import cv2


def blur_score(gray):
    """Laplacian variance -- higher means sharper. Expects grayscale input."""
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def motion_score(prev_gray, curr_gray):
    """Mean absolute pixel difference between consecutive frames."""
    if prev_gray is None:
        return 999.0
    return cv2.absdiff(prev_gray, curr_gray).mean()
