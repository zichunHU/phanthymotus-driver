"""Install the pinned Google and MuJoCo model assets into the project runtime."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shutil import copyfileobj
from tarfile import open as open_tar
from urllib.request import urlopen

ASSETS = Path(__file__).resolve().parent / ".runtime" / "assets"
MODELS = "https://storage.googleapis.com/mediapipe-models"
FILES = (
    ("pose.task", f"{MODELS}/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"),
    ("hand.task", f"{MODELS}/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"),
    ("g1.tar.xz", "https://github.com/google-deepmind/mujoco_menagerie/releases/download/assets/"
                 "unitree_g1-b1954d9b3940949d.tar.xz"),
)


def download(item):
    name, url = item
    path = ASSETS / name
    if not path.is_file():
        partial = path.with_suffix(path.suffix + ".part")
        with urlopen(url, timeout=60) as response, partial.open("wb") as output:
            copyfileobj(response, output)
        partial.replace(path)
    print(f"{name}  {path.stat().st_size:,} bytes", flush=True)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    g1 = ASSETS / "g1"
    files = [item for item in FILES if item[0] != "g1.tar.xz" or not g1.is_dir()]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, files))
    if not g1.is_dir():
        with open_tar(ASSETS / "g1.tar.xz", "r:xz") as archive:
            archive.extractall(ASSETS)
        (ASSETS / "unitree_g1").rename(g1)


if __name__ == "__main__":
    main()
