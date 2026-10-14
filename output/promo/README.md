# Verif.AI promo

- Final: `verifai-promo-10s.mp4`
- Format: 1080 × 1920, 9:16, 30 fps, H.264 / AAC, 10 seconds.
- Content: product introduction, animated walkthrough of an existing news-check screen capture, recorded result with sources, and closing call to action.
- Audio: Windows Microsoft Zira Desktop voice, with an original locally synthesized instrumental bed.
- Editable source: `render_promo.py`; requires Python, Pillow, NumPy, and imageio-ffmpeg. The original voice WAV is included for rerendering.
- Source image: `verifai-frontend/public/images/news-analyzer-preview.png` in the workspace. This is an existing result, not a new analysis. Footers identify the recorded example and compressed timing.
- Validation: reviewed the contact sheet; confirmed 300 frames at 30 fps and 1080 × 1920; decoded the entire video and audio with FFmpeg without errors.

No Higgsfield service or paid generation API was used.
