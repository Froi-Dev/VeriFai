# Localized AI-edit validation

Tested on October 4, 2026 with the configured `gemini-3.5-flash-lite` model,
using `prepare_image`, `GeminiImageDetector.analyze`, and
`ImageDetectionResponse.model_validate`. The user explicitly authorized sending
both supplied examples to Google Gemini. Source images and personal ID details
are not stored in this report.

The user described the edits as generated writing in a photographed document and
an altered interaction between people (a "make them kiss" prompt). This is
user-supplied ground truth; original images and editing histories were not available.

| Example | Returned classification | Local edit assessment | Interpretation |
| --- | --- | --- | --- |
| Document | No clear AI signals | no_clear_signals | Missed the user-reported edit. |
| Two-panel interaction | Manipulation suspected | suspected | The stated reasons concern collage layout, different moments, and an overlay. These do not establish that the interaction was AI-edited. Do not count this as a validated detection. |

The model produced schema-valid responses within the configured deadline for
both requests. Only one live inference per example was completed. This is not
an accuracy benchmark, a deployment test, or a false-positive measurement.

## Remaining limitations

The current changes improve the review instructions, preserve uncertainty, and
remove the authenticity percentage from the interface. They do not add a trained
forensic detector. The model still used collage-related reasoning despite prompt
instructions excluding it as evidence of AI. Structured output compliance does
not guarantee evidence quality.

The legacy API field `authentic_probability` remains the complement of the AI
score for client compatibility. It is not a calibrated authenticity probability
and is no longer displayed as one in the image results interface.

Before claiming improved detection accuracy, evaluate an edit-detection or
localization model on a consented, held-out set containing AI-edited documents,
faces and interactions, alongside genuine photographs, ordinary handwriting,
unedited interactions, conventional collages, captions, and compressed or
screenshot versions. Measure both missed edits and false accusations. Do not
hard-code these examples or use their known labels as model instructions.

The prior implementation checks passed: 43 backend tests and a frontend build.
Those checks validate software behavior, not the vision model's accuracy.
