"""MediaPipe RGB input and Motus skeleton messages."""

import cv2
import mediapipe as mp
import numpy as np

from .pose_contract import OBSERVATION_SCHEMA, SIDES

BODY_INDEX = (11, 12, 13, 14, 15, 16, 23, 24)
BODY_NAMES = ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
              "left_wrist", "right_wrist", "left_hip", "right_hip")
HAND_NAMES = (
    "wrist", "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_mcp", "index_pip", "index_dip", "index_tip",
    "middle_mcp", "middle_pip", "middle_dip", "middle_tip",
    "ring_mcp", "ring_pip", "ring_dip", "ring_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
)
BODY_EDGES = [(0, 1), (0, 2), (2, 4), (1, 3), (3, 5), (0, 6), (1, 7), (6, 7)]
HAND_EDGES = [(0, 1), (0, 5), (0, 17), (5, 9), (9, 13), (13, 17)] + [
    (base + joint, base + joint + 1)
    for base in (1, 5, 9, 13, 17)
    for joint in range(3)
]


def _xyz(points):
    return [[p.x, p.y, p.z] for p in points]


def _score(point):
    return float(point.visibility if point.visibility is not None else 1.0)


class PoseDetector:
    def __init__(self, assets):
        vision = mp.tasks.vision
        base = mp.tasks.BaseOptions
        self.pose = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=base(model_asset_path=str(assets / "pose.task")),
                running_mode=vision.RunningMode.VIDEO, num_poses=2,
            )
        )
        self.hand = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=base(model_asset_path=str(assets / "hand.task")),
                running_mode=vision.RunningMode.VIDEO, num_hands=2,
            )
        )
        self.timestamp_ms = -1
        self.track_id = 0
        self.center = None

    def close(self):
        self.pose.close()
        self.hand.close()

    def detect(self, jpeg, capture_time):
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return {"schema": OBSERVATION_SCHEMA, "capture_time_s": capture_time,
                    "valid": False, "reason": "invalid_image"}, None
        height, width = frame.shape[:2]
        scale = np.array([width, height])
        timestamp = max(self.timestamp_ms + 1, int(capture_time * 1000))
        self.timestamp_ms = timestamp
        image = mp.Image(image_format=mp.ImageFormat.SRGB,
                         data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        pose = self.pose.detect_for_video(image, timestamp)
        observation = {"schema": OBSERVATION_SCHEMA, "capture_time_s": capture_time,
                       "valid": False, "reason": "person_not_visible"}
        preview = {"image_size": [width, height], "timestamp": capture_time,
                   "keypoint_names": list(BODY_NAMES), "skeleton": list(BODY_EDGES),
                   "count": 0, "persons": []}
        if len(pose.pose_landmarks) != 1:
            self.center = None
            if len(pose.pose_landmarks) > 1:
                observation["reason"] = "more_than_one_person"
            return observation, preview

        body = pose.pose_landmarks[0]
        points = [[body[i].x * width, body[i].y * height, _score(body[i])] for i in BODY_INDEX]
        if not np.isfinite(points).all():
            observation["reason"] = "invalid_body_points"
            return observation, preview
        torso = np.asarray([[body[i].x, body[i].y] for i in (11, 12, 23, 24)])
        center = torso.mean(axis=0)
        if self.center is None or np.linalg.norm(self.center - center) > 0.24:
            self.track_id += 1
        self.center = center
        observation["track_id"] = self.track_id
        preview["count"] = 1
        preview["persons"] = [{"id": self.track_id, "score": 1.0, "keypoints": points}]
        missing = [name for name, point in zip(BODY_NAMES, points) if point[2] < 0.5]
        if missing:
            observation.update(reason="upper_body_occluded", missing_keypoints=missing)
            return observation, preview

        world_body = _xyz(pose.pose_world_landmarks[0])
        if not np.isfinite(world_body).all():
            observation["reason"] = "invalid_world_points"
            return observation, preview

        hands = self.hand.detect_for_video(image, timestamp)
        wrists = np.asarray(points[4:6])[:, :2]
        shoulder_width = np.linalg.norm((torso[0] - torso[1]) * scale)
        max_distance = max(25, 0.55 * shoulder_width)
        matches = [[], []]
        for hand, world in zip(hands.hand_landmarks, hands.hand_world_landmarks):
            pixels = [[p.x * width, p.y * height, 1.0] for p in hand]
            xyz = _xyz(world)
            if not np.isfinite(pixels).all() or not np.isfinite(xyz).all():
                continue
            distances = np.linalg.norm(wrists - pixels[0][:2], axis=1)
            index = int(np.argmin(distances))
            if distances[index] <= max_distance and abs(distances[0] - distances[1]) >= 8:
                matches[index].append((pixels, xyz))

        world_hands = {}
        for index, (side, candidates) in enumerate(zip(SIDES, matches)):
            if len(candidates) != 1:
                continue
            pixels, world_hands[side] = candidates[0]
            offset = len(points)
            preview["skeleton"].extend((offset + a, offset + b) for a, b in HAND_EDGES)
            preview["skeleton"].append((4 + index, offset))
            preview["keypoint_names"].extend(f"{side}_hand_{name}" for name in HAND_NAMES)
            points.extend(pixels)
        observation.update(valid=True, reason=None, body=world_body, hands=world_hands)
        return observation, preview
