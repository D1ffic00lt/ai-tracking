import cv2
import numpy as np

from ultralytics import YOLO
from ultralytics.engine.results import Results
from collections import defaultdict
from datetime import datetime


class TrackedObject(object):
    MAX_POINTS = 90

    def __init__(self):
        self.tracked_points = []
        self.predicted_types = defaultdict(int)
        self.first_detection = None
        self.last_detection = None
        self.cropped_frame = None

    def detect(self):
        if self.first_detection is None:
            self.first_detection = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.last_detection = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    @property
    def type(self):
        return max(self.predicted_types.keys(), key=lambda x: self.predicted_types[x])

    @property
    def points(self) -> np.ndarray:
        return np.hstack(self.tracked_points).astype(np.int32).reshape((-1, 1, 2))

    @points.setter
    def points(self, value: tuple[float, float]):
        if len(self.tracked_points) > self.MAX_POINTS:
            self.tracked_points.pop(0)
        self.tracked_points.append(value)

    @classmethod
    def set_max_points_count(cls, value):
        cls.MAX_POINTS = value

    def save(self, path):
        cv2.imwrite(path, self.cropped_frame)

    def __str__(self):
        return f"({self.first_detection}) - ({self.last_detection}): {self.type}(count={len(self.points)}) "

    def __len__(self):
        if not self.tracked_points:
            return 0
        return sum(self.predicted_types.values())

    def __repr__(self):
        return f"TrackedObject<{self.type}>"


class Tracker(object):
    # MODEL THRESHOLDS
    CONF = 0.3
    IOU = 0.5
    FRAMES_COUNT = 10

    # VISUALIZE
    VERBOSE = False
    SHOW_PREDS = True
    SAVE = False

    def __init__(self, weights_path: str) -> None:
        self.model = YOLO(weights_path)
        self.tracked_objects = defaultdict(lambda: TrackedObject())

    def load_model(self, weights_path: str) -> None:
        self.model = YOLO(weights_path)

    def track_next_frame(self, frame: np.array) -> list[Results]:
        results = self.model.track(
            frame,
            persist=True,
            conf=self.CONF,
            iou=self.IOU,
            verbose=self.VERBOSE,
            save=self.SAVE,
            classes=[0, 2, 3, 6, 7]
        )
        if results[0].boxes.id is None:
            if self.SHOW_PREDS:
                cv2.imshow("YOLOv8 Tracking", frame)
            return results
        boxes = results[0].boxes
        names = results[0].names
        track_ids = results[0].boxes.id.int().cpu().tolist()

        annotated_frame = results[0].plot()
        for box, track_id, name in zip(boxes, track_ids, names):
            x, y, w, h = box.xywh.cpu()[0]
            cls = box.cls
            track = self.tracked_objects[track_id]
            track.detect()
            if track.cropped_frame is None and len(track) > self.FRAMES_COUNT:
                track.cropped_frame = self.crop_image_with_bbox(frame, map(float, box.xywhn.cpu()[0]))
            track.predicted_types[results[0].names[int(cls)]] += 1
            track.points = (float(x), float(y))
            if self.SHOW_PREDS:
                cv2.polylines(
                    annotated_frame,
                    [track.points],
                    isClosed=False,
                    color=(0, 255, 0),
                    thickness=2,
                    lineType=cv2.LINE_AA
                )

                cv2.imshow("YOLOv8 Tracking", annotated_frame)
        return results

    def track_video(self, video: str | cv2.VideoCapture) -> None:
        if isinstance(video, str):
            video = cv2.VideoCapture(video)
        while video.isOpened():
            success, frame = video.read()

            if success:
                self.track_next_frame(frame)
                if self.SHOW_PREDS:
                    if cv2.waitKey(1) & 0xFF in [ord("q"), 27]:
                        break
            else:
                break
        if self.SHOW_PREDS:
            cv2.destroyAllWindows()

    def get_objects(self):
        return {
            key: self.tracked_objects[key]
            for key in filter(lambda x: len(self.tracked_objects.get(x)) > self.FRAMES_COUNT, self.tracked_objects)
        }

    @staticmethod
    def crop_image_with_bbox(image, bbox):
        original_height, original_width = image.shape[:2]

        x_center, y_center, w, h = bbox

        x_center = int(x_center * original_width)
        y_center = int(y_center * original_height)
        w = int(w * original_width)
        h = int(h * original_height)

        x = int(x_center - w / 2)
        y = int(y_center - h / 2)

        cropped_image = image[y:y + h, x:x + w]

        return cropped_image


if __name__ == "__main__":
    tracker = Tracker("yolov8n.pt")
    tracker.SHOW_PREDS = True
    tracker.SAVE = False
    try:
        tracker.track_video("./1234.mp4")
    except KeyboardInterrupt:
        pass
    for num, i in enumerate(tracker.get_objects().values()):
        print(i)
        i.save(f"{num}.jpg")
