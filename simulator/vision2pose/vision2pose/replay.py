"""Feed a local clip through the same Motus browser-camera stream."""

import argparse
from pathlib import Path
from time import monotonic, sleep

import cv2
from websockets.sync.client import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--url", default="ws://127.0.0.1:15678/ws/camera")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        parser.error(f"无法打开视频 {args.video}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25
    try:
        with connect(args.url) as websocket:
            deadline = monotonic()
            while True:
                ok, frame = capture.read()
                if not ok:
                    if not args.loop:
                        break
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = capture.read()
                    if not ok:
                        raise ValueError("视频不含可读帧")
                width = frame.shape[1]
                if width > 960:
                    frame = cv2.resize(frame, (960, round(frame.shape[0] * 960 / width)))
                encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
                if encoded:
                    websocket.send(jpeg.tobytes())
                deadline += 1 / fps
                sleep(max(0, deadline - monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        capture.release()


if __name__ == "__main__":
    main()
