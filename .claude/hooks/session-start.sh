#!/bin/bash
# Richtet Cloud-Sessions fuer den Ad-Video-Agenten ein (adagent/engine.py):
# ffmpeg, espeak-ng + deutsche MBROLA-Stimme, Pillow, numpy.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

missing=()
command -v ffmpeg >/dev/null || missing+=(ffmpeg)
command -v espeak-ng >/dev/null || missing+=(espeak-ng)
[ -d /usr/share/mbrola/de7 ] || missing+=(mbrola mbrola-de7)

if [ ${#missing[@]} -gt 0 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq "${missing[@]}" >/dev/null
fi

python3 -c "import PIL, numpy" 2>/dev/null || pip install -q pillow numpy

echo "Ad-Video-Agent: Abhaengigkeiten bereit (ffmpeg, espeak-ng, mbrola-de7, Pillow, numpy)."
