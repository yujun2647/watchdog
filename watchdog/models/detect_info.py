class DetectInfo(object):

    def __init__(self, frame_id, fps=25, width=None, height=None, label=None,
                 bbox=None, confidence=None, suggest_color=(255, 255, 255),
                 is_detected=True):
        self.frame_id = frame_id
        self.fps = fps
        self.width = width
        self.height = height
        self.label = label
        self.bbox = bbox  # x, y, w, h
        self.confidence = confidence
        self.suggest_color = suggest_color
        self.is_detected = is_detected

    @property
    def center_point(self):
        x, y, w, h = self.bbox
        return int(x + w / 2), int(y + h / 2)

    @property
    def area(self):
        _, _, w, h = self.bbox
        return w * h
