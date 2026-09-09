#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install --yes --no-install-recommends \
    libegl1 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-util1 \
    libxcb-xkb1 \
    libxkbcommon-x11-0
