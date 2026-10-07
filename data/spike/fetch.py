"""Download pinned inputs for the Sanskrit tooling spike into data/vendor/ (gitignored).

uv run python -m spike.fetch          # Vidyut data + GRETIL texts (~40 MB)
uv run python -m spike.fetch --dcs    # + DCS gold morphology for evaluation (163 MB)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
USER_AGENT = "VedicVoice/0.1 (https://github.com/shivraj1991/vedic-voice)"

VIDYUT_DATA = (
    "https://github.com/ambuda-org/vidyut/releases/download/py-0.4.0/data-0.4.0.zip",
    "5269cda86451a75dbc93b605f6864bb5a52cc79d66da02f18f30cf87d0059ecb",
)
GRETIL = "https://gretil.sub.uni-goettingen.de/gretil"
GRETIL_PLAIN = f"{GRETIL}/corpustei/transformations/plaintext"
TEXTS = {
    # Unpinned: GRETIL files carry no version id; we record retrieval date in sources.yaml.
    "rv_padapatha.txt": f"{GRETIL_PLAIN}/sa_RgvedasaMhitApadapATha.txt",
    "rv_samhita.txt": f"{GRETIL_PLAIN}/sa_Rgveda-edAufrecht.txt",
    "bhagavadgita.htm": f"{GRETIL}/1_sanskr/2_epic/mbh/ext/bhgce__u.htm",
}
DCS = (
    "https://huggingface.co/datasets/sampathlonka/DCS_Sanskrit_Morphology_v1/resolve/"
    "df4b8002f360bff4ffdaa2990faa222a8f41232e/train.csv",
    "9b46f48cd9f40a84452f5a86a31c5caedfead362100ca59f5f4813fde3e60be8",
)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _check(data: bytes, sha256: str | None, what: str) -> bytes:
    if sha256 and hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError(f"checksum mismatch for {what}")
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dcs", action="store_true", help="also fetch DCS gold data (evaluation)")
    args = ap.parse_args()
    VENDOR.mkdir(exist_ok=True)

    vdir = VENDOR / "vidyut-0.4.0"
    if not (vdir / "kosha").exists():
        data = _check(_get(VIDYUT_DATA[0]), VIDYUT_DATA[1], "vidyut data")
        zipfile.ZipFile(io.BytesIO(data)).extractall(vdir)
    print(f"ok   {vdir.relative_to(ROOT)}")

    for name, url in TEXTS.items():
        dest = VENDOR / name
        if not dest.exists():
            dest.write_bytes(_get(url))
        print(f"ok   {dest.relative_to(ROOT)}")

    if args.dcs:
        dest = VENDOR / "dcs_morphology.csv"
        if not dest.exists():
            dest.write_bytes(_check(_get(DCS[0]), DCS[1], "DCS"))
        print(f"ok   {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
