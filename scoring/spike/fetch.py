"""Download the model and test recordings for the spike (pinned + checksummed).

    uv run python -m spike.fetch            # model + Su-śrotā test split
    uv run python -m spike.fetch --commons  # also Wikimedia Commons files (slow, rate-limited)

Everything lands in gitignored folders (models/, spike/audio/).
"""

from __future__ import annotations

import argparse
import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "qnighy/wav2vec2-xlsr-53-espeak-cv-ft-ONNX"
MODEL_REV = "d2987af7ae07d53eafee15dc7190479062faa1e8"
MODEL_FILES = {
    "vocab.json": "d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0",
    "config.json": None,
    "preprocessor_config.json": None,
    "onnx/model.onnx": "e36d613ec49b7c158ab7a53de315e5e142e78284ae4353d23e073261d76de48e",
    "onnx/model_q4.onnx": "d6268189f919b7eeecff55512d433fc704c12247537318d906a07698ff77cf70",
}
DATASET_REPO = "prathoshap/sushrota-sanskrit-asr-data"
DATASET_REV = "9ea73b50734901a5fabbb98233e062a05d1b71f0"
DATASET_FILE = "data/in_the_wild_test-00000-of-00001.parquet"
DATASET_SHA = "233b124c7fafb870c8b23382cd3339f970b87802fdd221790a53c23f30c58f5d"
# Wikimedia asks automated clients to identify themselves.
USER_AGENT = "VedicVoiceSpike/0.1 (https://github.com/shivraj1991/vedic-voice)"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, sha256: str | None = None, retries: int = 5) -> None:
    if dest.exists() and (sha256 is None or _sha256(dest) == sha256):
        print(f"ok   {dest.relative_to(ROOT)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    wait = 30
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with (
                urllib.request.urlopen(req, timeout=120) as r,
                dest.with_suffix(".part").open("wb") as f,
            ):
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            dest.with_suffix(".part").rename(dest)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries - 1:
                raise
            print(f"429 for {url}; retrying in {wait}s")
            time.sleep(wait)
            wait *= 2
    if sha256 and _sha256(dest) != sha256:
        dest.unlink()
        raise RuntimeError(f"checksum mismatch for {dest}")
    print(f"got  {dest.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commons", action="store_true", help="also fetch Wikimedia Commons files")
    ap.add_argument("--skip-fp32", action="store_true", help="only the 4-bit model (230 MB)")
    args = ap.parse_args()

    model_dir = ROOT / "models" / "w2v2-xlsr53-espeak"
    for name, sha in MODEL_FILES.items():
        if args.skip_fp32 and name == "onnx/model.onnx":
            continue
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REV}/{name}"
        download(url, model_dir / Path(name).name, sha)

    audio_dir = ROOT / "spike" / "audio"
    download(
        f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/{DATASET_REV}/{DATASET_FILE}",
        audio_dir / "sushrota" / "in_the_wild_test.parquet",
        DATASET_SHA,
    )
    if args.commons:
        manifest = yaml.safe_load((ROOT / "spike" / "recordings.yaml").read_text("utf-8"))
        for rec in manifest["recordings"]:
            download(rec["url"], audio_dir / rec["file"])
            time.sleep(10)  # be polite; upload.wikimedia.org rate-limits aggressively


if __name__ == "__main__":
    main()
