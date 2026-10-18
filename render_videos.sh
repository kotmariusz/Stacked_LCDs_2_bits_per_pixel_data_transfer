#!/usr/bin/env bash
# Render every animation in polarizer_states.py and collect the results in ./videos
#
#   ./render_videos.sh            4K (3840x2160) at 30 fps       <- default
#   ./render_videos.sh 4k60       4K at 60 fps: twice the frames, twice the time
#   ./render_videos.sh hd         1080p at 60 fps
#   ./render_videos.sh preview    480p at 15 fps, a quick check of everything
#
#   ./render_videos.sh 4k S5_WhyTheLCDMakesColour     just one scene
#
#   ./render_videos.sh publish    copy videos/4k into docs/videos and rebuild the
#                                 GIF previews in docs/animations that the README
#                                 shows (needs ffmpeg: sudo apt install ffmpeg)
#   ./render_videos.sh publish S5_WhyTheLCDMakesColour     just one scene
#
# Needs Manim Community v0.18 or newer. LaTeX is optional: without it the
# labels fall back to plain text automatically.

set -euo pipefail
cd "$(dirname "$0")"

ALL=(S1_TwoPolarizers
     S2_MiddlePolarizer
     S3_WhereTheFourthComesFrom
     S4_MountTheThirdOffAxis
     S5_WhyTheLCDMakesColour)

mode="${1:-4k}"
shift || true

if [ "$#" -gt 0 ]; then scenes=("$@"); else scenes=("${ALL[@]}"); fi

# -- publish: the README cannot play an MP4 from the repo, so it shows a GIF
#    preview of each video and links the GIF to the full 4K file
if [ "$mode" = publish ]; then
  command -v ffmpeg >/dev/null || {
    echo "publish needs the ffmpeg command: sudo apt install ffmpeg" >&2; exit 1; }
  mkdir -p docs/videos docs/animations
  for s in "${scenes[@]}"; do
    src="videos/4k/$s.mp4"
    [ -f "$src" ] || {
      echo "missing $src - render it first: ./render_videos.sh 4k $s" >&2; exit 1; }
    cp "$src" "docs/videos/$s.mp4"
    # 960 px wide at 15 fps, one 256-colour palette per video, and only the
    # changed part of each frame stored: Manim's flat colours need no dither.
    # The scene's last frame goes first too: every scene starts black, and
    # the first frame is the still GitHub shows when autoplay is off. When
    # the GIF loops, the end runs into that identical frame, so it is unseen.
    ffmpeg -v error -y -sseof -0.05 -i "$src" -i "$src" -filter_complex "\
[0:v]fps=15,scale=960:-1:flags=lanczos,trim=end_frame=1[still];\
[1:v]fps=15,scale=960:-1:flags=lanczos[anim];\
[still][anim]concat=n=2:v=1:a=0,split[a][b];\
[a]palettegen=stats_mode=full[p];\
[b][p]paletteuse=dither=none:diff_mode=rectangle" \
      -loop 0 "docs/animations/$s.gif"
    echo "  $s   video $(du -h "docs/videos/$s.mp4" | cut -f1)" \
         "  preview $(du -h "docs/animations/$s.gif" | cut -f1)"
  done
  exit 0
fi

case "$mode" in
  preview) args=(-ql);           folder="480p15"  ;;
  hd)      args=(-qh);           folder="1080p60" ;;
  4k60)    args=(-qk);           folder="2160p60" ;;
  4k)      args=(-qk --fps 30);  folder="2160p30" ;;
  *) echo "unknown mode '$mode' - use 4k, 4k60, hd, preview or publish" >&2
     exit 1 ;;
esac

out="videos/$mode"
mkdir -p "$out"

for s in "${scenes[@]}"; do
  echo
  echo "=== $s  ($mode)"
  start=$(date +%s)
  manim "${args[@]}" polarizer_states.py "$s"
  cp "media/videos/polarizer_states/$folder/$s.mp4" "$out/$s.mp4"
  echo "    done in $(( $(date +%s) - start )) s  ->  $out/$s.mp4"
done

echo
echo "All rendered:"
ls -lh "$out"/*.mp4
