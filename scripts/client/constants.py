# Camera / frame pipeline
CAMERA_DEVICE    = 0
FRAME_INTERVAL   = 0.2      # seconds between frame-send attempts
FORCE_SEND_MS    = 350      # always send even without motion after this many ms
JPEG_QUALITY     = 85
BLUR_THRESHOLD   = 100.0    # Laplacian variance; below this → frame too blurry to send
MOTION_THRESHOLD = 1.0      # mean abs-diff; below this → frame too static to send

# Audio / VAD
SAMPLE_RATE   = 16000
VAD_THRESHOLD = 0.5

# Detection tracking
SMOOTHING_ALPHA = 0.4
TRACK_MAX_AGE   = 8

# Timing / TTL
DETECTION_TTL_S       = 1.2   # drop live_detections when YOLO result is older than this
ANALYSIS_TTL_S        = 8.0   # clear VLM callout after this many seconds
CALLOUT_COOLDOWN_S    = 5.0   # minimum gap between repeated voice callouts
HIGH_ANOMALY_THRESHOLD = 0.15  # anomaly_score above this → red border (vs yellow)
LABEL_UNSEEN_TIMEOUT_S = 20.0  # label can be re-announced after this many seconds absent

# COCO labels irrelevant to CAT inspection — suppressed from display and terminal
_IGNORE_LABELS = {
    "person", "chair", "tv", "laptop", "cell phone", "book", "bottle",
    "cup", "clock", "keyboard", "mouse", "remote", "couch", "potted plant",
    "bed", "dining table", "toilet", "sink", "refrigerator", "microwave",
    "oven", "toaster", "wine glass", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog",
    "pizza", "donut", "cake", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis",
    "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket",
}

ALL_ZONES = [
    "boom_arm", "bucket", "cab", "cooling", "drivetrain",
    "engine", "hydraulics", "steps_handrails", "stick",
    "structural", "tires_rims", "tracks_left", "tracks_right",
    "undercarriage", "attachments",
]

ZONE_COLORS = {
    "GREEN":  (0, 200, 0),
    "YELLOW": (0, 200, 255),
    "RED":    (0, 0, 220),
    "GRAY":   (120, 120, 120),
}
