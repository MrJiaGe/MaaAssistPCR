"""Prepare the pinned OCR model for running resources directly from the workspace."""

import subprocess
import sys

from install import ROOT, stage_ocr_model


if __name__ == "__main__":
    destination = ROOT / "assets/resource/model/ocr"
    try:
        stage_ocr_model(destination)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"OCR model configuration failed: {error}")
    print(f"OCR model configured: {destination}")
