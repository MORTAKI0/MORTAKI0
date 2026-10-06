from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "source-prepped.png"


def load_image(path: str | None, url: str | None) -> Image.Image:
    if url:
        response = requests.get(url, timeout=30, headers={"User-Agent": "MORTAKI0-profile-art/1.0"})
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGBA")
    if not path:
        raise SystemExit("provide an input image path or --url")
    return Image.open(path).convert("RGBA")


def maybe_remove_background(image: Image.Image, enabled: bool) -> Image.Image:
    if not enabled:
        return image
    try:
        from rembg import remove
    except ImportError as exc:
        raise SystemExit("--remove-background requires optional dependency 'rembg'") from exc
    result = remove(image)
    return result.convert("RGBA")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a portrait for clean monochrome ASCII conversion")
    parser.add_argument("input", nargs="?", help="local portrait path")
    parser.add_argument("--url", help="download portrait from URL instead of a local path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--remove-background", action="store_true")
    args = parser.parse_args()

    image = load_image(args.input, args.url)
    image = ImageOps.exif_transpose(image)
    image = maybe_remove_background(image, args.remove_background)

    # Center crop to a portrait-friendly square.
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize((700, 700), Image.Resampling.LANCZOS)

    # Composite transparency onto white so empty background becomes spaces later.
    white = Image.new("RGBA", image.size, "white")
    white.alpha_composite(image)
    gray = np.array(white.convert("L"))

    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    # Lift the brightest values so plain backgrounds disappear more reliably.
    enhanced = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(enhanced).save(output)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
