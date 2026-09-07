"""
preprocess.py
=============
Production-ready image preprocessing module for medical report OCR.

Cleans and enhances scanned / photographed medical documents and handwritten
prescriptions BEFORE they are passed to any OCR engine.  Handles:
  - Uneven illumination and background shadows
  - Low-quality or faded scans
  - Salt-and-pepper / Gaussian noise
  - Tilted / skewed document pages
  - Lightly handwritten prescriptions

No OCR is performed in this file.  The output is a NumPy ndarray
(uint8, grayscale) optimised for downstream OCR accuracy.

Dependencies
------------
    pip install opencv-python-headless numpy

Usage (CLI)
-----------
    python preprocess.py --input sample.jpg --output processed.jpg
    python preprocess.py --input scan.png  --output clean.png --verbose

Usage (Python API)
------------------
    from preprocess import preprocess_image, save_processed_image

    img = preprocess_image("report.jpg")          # → np.ndarray
    save_processed_image("report.jpg", "out.jpg") # → None
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("preprocess")


# ===========================================================================
# ─── HELPER FUNCTIONS ───────────────────────────────────────────────────────
# ===========================================================================


def load_image(image_path: str) -> np.ndarray:
    """
    Read a BGR image from disk using OpenCV.

    Parameters
    ----------
    image_path : str
        Absolute or relative path to the image file.

    Returns
    -------
    np.ndarray
        BGR image (3-channel uint8) as returned by cv2.imread.

    Raises
    ------
    FileNotFoundError
        If the file does not exist at the given path.
    ValueError
        If OpenCV cannot decode the file (corrupt or unsupported format).
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: '{image_path}'")

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError(
            f"OpenCV could not decode the image at '{image_path}'. "
            "Ensure it is a valid PNG, JPEG, TIFF, or BMP file."
        )

    logger.info("Loaded  '%s'  shape=%s  dtype=%s", image_path, image.shape, image.dtype)
    return image


# ---------------------------------------------------------------------------


def resize_image_if_needed(
    image: np.ndarray,
    min_width: int = 1000,
    max_width: int = 4000,
) -> np.ndarray:
    """
    Rescale the image so its width falls within [min_width, max_width].

    Very small images produce poor OCR accuracy; very large images slow
    down processing.  Aspect ratio is always preserved.

    Parameters
    ----------
    image : np.ndarray
        Input image (any number of channels).
    min_width : int
        Upscale if image width is below this value (default 1000 px).
    max_width : int
        Downscale if image width exceeds this value (default 4000 px).

    Returns
    -------
    np.ndarray
        Resized image, or the original if it already fits the range.
    """
    h, w = image.shape[:2]
    target_w: int | None = None

    if w < min_width:
        target_w = min_width
        logger.info("Image narrow (%d px) — upscaling to %d px wide.", w, target_w)
    elif w > max_width:
        target_w = max_width
        logger.info("Image wide (%d px) — downscaling to %d px wide.", w, target_w)

    if target_w is not None:
        scale = target_w / w
        new_size = (target_w, int(h * scale))
        # INTER_CUBIC produces sharper results when enlarging;
        # INTER_AREA produces less aliasing when shrinking.
        interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
        image = cv2.resize(image, new_size, interpolation=interp)

    return image


# ---------------------------------------------------------------------------


def remove_shadows(image: np.ndarray) -> np.ndarray:
    """
    Normalize uneven illumination and reduce background shadows.

    **Must be called BEFORE grayscale conversion** so that colour-channel
    differences caused by shadows are also corrected.

    The technique processes each channel independently:
      1. Estimate the background light-map by applying a large morphological
         dilation (dark text pixels are "filled in", leaving only the
         background brightness variation).
      2. Divide the original channel by the estimated background so
         brightness becomes roughly uniform across the entire page.
      3. Rescale the result back to the [0, 255] uint8 range.

    Parameters
    ----------
    image : np.ndarray
        BGR (3-channel) or grayscale (single-channel) uint8 image.

    Returns
    -------
    np.ndarray
        Shadow-normalised image, same shape and dtype as input.
    """
    # Large structuring element so the dilation spans character widths
    # and captures only the slowly varying background brightness.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))

    if image.ndim == 2:
        # ── Grayscale path ────────────────────────────────────────────────
        background = cv2.dilate(image, kernel, iterations=1)
        normalised = _normalise_against_background(image, background)
        logger.debug("Shadow removal applied (grayscale).")
        return normalised

    # ── BGR path: process each channel independently ──────────────────────
    channels = cv2.split(image)
    normalised_channels = []
    for ch in channels:
        background = cv2.dilate(ch, kernel, iterations=1)
        normalised_channels.append(_normalise_against_background(ch, background))

    result = cv2.merge(normalised_channels)
    logger.debug("Shadow removal applied (colour, %d channels).", len(channels))
    return result


def _normalise_against_background(
    channel: np.ndarray,
    background: np.ndarray,
) -> np.ndarray:
    """
    Divide a single channel by its estimated background and rescale to uint8.

    Parameters
    ----------
    channel : np.ndarray
        Single-channel uint8 image.
    background : np.ndarray
        Estimated background light-map (same shape as *channel*).

    Returns
    -------
    np.ndarray
        Normalised single-channel uint8 image.
    """
    # Float division avoids integer overflow / underflow
    ch_f = channel.astype(np.float32)
    bg_f = background.astype(np.float32)

    # Small epsilon prevents division by zero in pure-black background areas
    normalised = (ch_f / (bg_f + 1e-6)) * 255.0
    return np.clip(normalised, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------


def remove_noise(image: np.ndarray) -> np.ndarray:
    """
    Reduce random noise using Non-Local Means denoising.

    Non-Local Means compares small patches across the whole image to
    distinguish true signal (text edges) from random noise.  It preserves
    edge sharpness better than simple Gaussian or median filters, which is
    critical for thin character strokes.

    Parameters
    ----------
    image : np.ndarray
        Single-channel (grayscale) uint8 image.

    Returns
    -------
    np.ndarray
        Denoised grayscale image (uint8).
    """
    # h: filter strength — higher values remove more noise but may blur fine
    #    text; 10 is a good default for 300 DPI document scans.
    # templateWindowSize: size of the patch used for comparison (must be odd).
    # searchWindowSize: neighbourhood to search for similar patches (must be odd).
    denoised = cv2.fastNlMeansDenoising(
        image,
        h=10,
        templateWindowSize=7,
        searchWindowSize=21,
    )
    logger.debug("Non-Local Means denoising applied.")
    return denoised


# ---------------------------------------------------------------------------


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    """
    Improve local contrast using CLAHE (Contrast Limited Adaptive Histogram
    Equalisation).

    Unlike global histogram equalisation, CLAHE divides the image into small
    tiles and equalises each tile independently, so local contrast is boosted
    without over-amplifying noise in regions that are already bright or dark.
    The *clipLimit* parameter prevents runaway noise amplification.

    Parameters
    ----------
    gray : np.ndarray
        Single-channel grayscale uint8 image.

    Returns
    -------
    np.ndarray
        Contrast-enhanced grayscale image (uint8).
    """
    # clipLimit: maximum contrast amplification factor per tile.
    # tileGridSize: number of tiles along each axis (8×8 is standard).
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    logger.debug("CLAHE contrast enhancement applied.")
    return enhanced


# ---------------------------------------------------------------------------


def apply_morphology(binary: np.ndarray) -> np.ndarray:
    """
    Apply morphological opening followed by closing to a binary image.

    - **Opening** (erode → dilate): removes isolated noise blobs and thin
      speckles that would confuse an OCR engine.
    - **Closing** (dilate → erode): fills small gaps inside character strokes
      and reconnects near-touching letter parts — especially useful for
      handwritten text where ink may be discontinuous.

    A small 2×2 rectangular structuring element is used so only tiny features
    are affected and no meaningful character geometry is lost.

    Parameters
    ----------
    binary : np.ndarray
        Binary (thresholded) single-channel uint8 image.

    Returns
    -------
    np.ndarray
        Morphologically cleaned binary image (uint8).
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))

    # Opening: remove noise first
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    # Closing: reconnect broken strokes
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=1)

    logger.debug("Morphological open + close applied.")
    return closed


# ---------------------------------------------------------------------------


def sharpen_image(image: np.ndarray) -> np.ndarray:
    """
    Apply an unsharp-mask filter to sharpen text edges.

    The unsharp mask subtracts a blurred copy of the image from the original,
    effectively amplifying high-frequency detail (edges, fine strokes).

    Parameters
    ----------
    image : np.ndarray
        Single-channel grayscale uint8 image.

    Returns
    -------
    np.ndarray
        Sharpened image (uint8).
    """
    # Gaussian blur produces the "unsharp" mask
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=3)

    # alpha=1.5 boosts the original; beta=-0.5 subtracts the blur.
    # gamma=0 is the scalar offset added to every pixel.
    sharpened = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)

    logger.debug("Unsharp-mask sharpening applied.")
    return sharpened


# ---------------------------------------------------------------------------


def deskew_image(
    image: np.ndarray,
    tolerance_degrees: float = 0.5,
) -> np.ndarray:
    """
    Detect and correct the rotation (skew) of a document image.

    Algorithm
    ---------
    1. Invert the binary image so text pixels become *white* on a black
       background (required because minAreaRect finds the bounding box of
       white pixels).
    2. Collect all white pixel coordinates.
    3. Fit a minimum-area bounding rectangle around the text mass using
       ``cv2.minAreaRect``, which returns the dominant text angle.
    4. Convert OpenCV's angle convention (range [-90, 0)) to a true
       rotation angle in [-45, 45).
    5. If |angle| ≤ *tolerance_degrees*, return the image unchanged to
       avoid introducing interpolation blur on already-straight pages.
    6. Rotate the image around its centre with ``cv2.warpAffine``, filling
       any newly exposed border areas with **white** (255) so document
       corners do not turn black after rotation.

    Parameters
    ----------
    image : np.ndarray
        Single-channel grayscale or binary uint8 image.
    tolerance_degrees : float
        Minimum skew angle (in degrees) that triggers a correction.
        Rotations smaller than this value are skipped.  Default is 0.5°.

    Returns
    -------
    np.ndarray
        Deskewed image (uint8), same spatial dimensions as input.
    """
    # Invert so that dark text on a white page becomes white on black
    inverted = cv2.bitwise_not(image)

    # Collect (row, col) coordinates of every non-zero (white) pixel
    coords = np.column_stack(np.where(inverted > 0))

    if coords.size == 0:
        # Completely blank image — nothing to measure
        logger.warning("Deskew: no foreground pixels found; returning original.")
        return image

    # Minimum-area bounding rectangle of all text pixels.
    # Returns: (centre_point, (width, height), angle)
    # The angle is in the range [-90, 0) by OpenCV convention.
    rect = cv2.minAreaRect(coords)
    angle: float = rect[-1]

    # Convert to a rotation angle in [-45, 45):
    # When angle < -45°, the rectangle is oriented the "other way" and
    # adding 90° gives the correct smaller angle.
    if angle < -45.0:
        angle += 90.0

    # Skip correction if the document is already nearly horizontal
    if abs(angle) <= tolerance_degrees:
        logger.info(
            "Deskew: angle %.2f° is within ±%.1f° tolerance — skipping.",
            angle,
            tolerance_degrees,
        )
        return image

    logger.info("Deskew: correcting %.2f° skew.", angle)

    h, w = image.shape[:2]
    centre: Tuple[float, float] = (w / 2.0, h / 2.0)

    # 2-D rotation matrix around the image centre (scale = 1, no zoom)
    rotation_matrix = cv2.getRotationMatrix2D(centre, angle, scale=1.0)

    # Apply affine rotation.
    # BORDER_CONSTANT + borderValue=255 fills newly exposed corner areas
    # with white so they match the document background rather than turning black.
    deskewed = cv2.warpAffine(
        image,
        rotation_matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )

    return deskewed


# ===========================================================================
# ─── PRIMARY PUBLIC PIPELINE ────────────────────────────────────────────────
# ===========================================================================


def preprocess_image(image_path: str) -> np.ndarray:
    """
    Full preprocessing pipeline for a scanned or photographed medical document.

    Pipeline stages (in order)
    --------------------------
    1.  **Load** — read the image from disk and validate.
    2.  **Resize** — ensure a sensible working resolution.
    3.  **Shadow removal** — normalize uneven illumination on the BGR image
        *before* colour information is discarded.
    4.  **Grayscale conversion** — collapse to single channel.
    5.  **Denoising** — Non-Local Means filter to reduce random noise.
    6.  **Contrast enhancement** — CLAHE for local contrast.
    7.  **Adaptive thresholding** — convert to a clean binary (B&W) image.
        Adaptive method is used because medical scans often have varying
        brightness across different parts of the page.
    8.  **Morphological operations** — opening removes speckle noise;
        closing reconnects broken character strokes.
    9.  **Sharpening** — unsharp-mask to crisp text edges.
    10. **Deskew** — detect and correct page rotation.

    Parameters
    ----------
    image_path : str
        Path to the input image (JPEG, PNG, TIFF, BMP, etc.).

    Returns
    -------
    np.ndarray
        Preprocessed, OCR-ready grayscale binary image (uint8).

    Raises
    ------
    FileNotFoundError
        If the image file does not exist.
    ValueError
        If the file cannot be decoded by OpenCV.
    """
    # ── Stage 1 : Load ────────────────────────────────────────────────────
    bgr = load_image(image_path)

    # ── Stage 2 : Resize to a usable resolution ───────────────────────────
    bgr = resize_image_if_needed(bgr, min_width=1000, max_width=4000)

    # ── Stage 3 : Shadow / illumination removal (on BGR) ─────────────────
    # Run BEFORE grayscale so colour-channel brightness differences caused
    # by non-uniform lighting are also corrected.
    bgr = remove_shadows(bgr)

    # ── Stage 4 : Grayscale conversion ───────────────────────────────────
    # Discard colour information; all remaining steps are single-channel.
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    logger.info("Grayscale conversion done  shape=%s", gray.shape)

    # ── Stage 5 : Denoising ──────────────────────────────────────────────
    gray = remove_noise(gray)

    # ── Stage 6 : Contrast enhancement ───────────────────────────────────
    gray = enhance_contrast(gray)

    # ── Stage 7 : Adaptive thresholding → binary image ───────────────────
    # ADAPTIVE_THRESH_GAUSSIAN_C computes a weighted mean over a local
    # neighbourhood.  This handles pages where one half is darker than the
    # other — a very common artefact in scanned medical reports.
    # blockSize: neighbourhood diameter (must be odd).
    # C: constant subtracted from the computed mean to set the threshold.
    binary = cv2.adaptiveThreshold(
        gray,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=15,
        C=11,
    )
    logger.info("Adaptive thresholding applied.")

    # ── Stage 8 : Morphological operations ───────────────────────────────
    binary = apply_morphology(binary)

    # ── Stage 9 : Sharpening ─────────────────────────────────────────────
    sharpened = sharpen_image(binary)

    # ── Stage 10 : Deskew ────────────────────────────────────────────────
    # Tolerance of ±0.5° means nearly straight documents are left untouched
    # to avoid introducing interpolation blur.
    final = deskew_image(sharpened, tolerance_degrees=0.5)
    logger.info("Preprocessing complete.  Output shape=%s  dtype=%s",
                final.shape, final.dtype)

    return final


# ===========================================================================
# ─── SAVE HELPER ────────────────────────────────────────────────────────────
# ===========================================================================


def save_processed_image(input_path: str, output_path: str) -> None:
    """
    Preprocess an image and write the cleaned result to disk.

    Parameters
    ----------
    input_path : str
        Path to the source image.
    output_path : str
        Destination path for the processed image.
        Parent directories are created automatically if they do not exist.

    Raises
    ------
    FileNotFoundError
        Propagated from ``preprocess_image`` if the source file is missing.
    ValueError
        Propagated from ``preprocess_image`` if the source cannot be decoded.
    OSError
        If OpenCV cannot write to *output_path* (invalid path / permissions).
    """
    # Ensure the destination directory exists before attempting to write
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)

    processed = preprocess_image(input_path)

    success = cv2.imwrite(output_path, processed)
    if not success:
        raise OSError(
            f"cv2.imwrite failed — could not write to '{output_path}'. "
            "Check that the path is valid and you have write permissions."
        )

    logger.info("Processed image saved → '%s'", output_path)


# ===========================================================================
# ─── COMMAND-LINE INTERFACE ─────────────────────────────────────────────────
# ===========================================================================


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="preprocess",
        description=(
            "Medical document image preprocessor.\n"
            "Cleans and enhances a scanned or photographed medical report / "
            "handwritten prescription so it produces higher-quality OCR output."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python preprocess.py --input report.jpg --output clean.jpg\n"
            "  python preprocess.py --input scan.png  --output out.png --verbose"
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="PATH",
        help="Path to the input image (JPEG, PNG, TIFF, BMP, …).",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="Destination path for the preprocessed image.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging to see every pipeline step.",
    )
    return parser


def main() -> int:
    """
    CLI entry point.

    Returns
    -------
    int
        0 on success, 1 on any handled error.
    """
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        save_processed_image(input_path=args.input, output_path=args.output)
        print(f"✓  Preprocessed image saved → {args.output}")
        return 0

    except FileNotFoundError as exc:
        logger.error("File not found: %s", exc)
        print(f"✗  Error: {exc}", file=sys.stderr)
        return 1

    except ValueError as exc:
        logger.error("Decode error: %s", exc)
        print(f"✗  Error: {exc}", file=sys.stderr)
        return 1

    except OSError as exc:
        logger.error("I/O error: %s", exc)
        print(f"✗  Error: {exc}", file=sys.stderr)
        return 1

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during preprocessing.")
        print(f"✗  Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
