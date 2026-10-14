# Prompt: Verifai use case diagram

Create a clean, editable UML use case diagram for the **Verifai** web application. Use the attached use case diagram only as a reference for the system-boundary-and-actors format; do not copy its labels or add its actors and actions to Verifai.

## Verify the scope

Use only the following actors and implemented capabilities:

- **Guest visitor:** accept guest consent, check remaining quota, analyze text for AI-writing signals, analyze an image for visible AI signals, verify a news claim, and check a news screenshot.
- **Registered user:** register or sign in, analyze text, analyze an image, verify a news claim or screenshot, view analysis results, view the dashboard and own scan history, delete one or clear own scan history, manage or revoke sessions, and request or complete a password reset.
- **Administrator:** list user accounts. Do not add user editing, deletion, reporting, or other administration functions.

Show a large system boundary labeled **Verifai Platform**. Place each actor outside the boundary and each use case inside it. Use concise verb phrases in the use case ovals. Keep similar analysis cases together, but preserve the distinction between text detection, image AI detection, and news verification.

## Actor connections

- Connect the guest only to guest consent, quota, text analysis, image analysis, news verification, screenshot checking, and viewing results.
- Connect the registered user only to registration/sign-in, the three analysis workflows, results, dashboard/history, history deletion, session management, and password reset.
- Connect the administrator only to **List user accounts**.
- Draw one clearly visible association for each actor-to-use-case relationship. Route lines around the ovals with right-angle bends where useful. Avoid shared trunks, duplicate lines, lines through labels, and unnecessary crossings. Keep all connections behind the use case shapes.
- Do not imply that a guest can use account history or session management. Do not imply that an administrator can edit or delete accounts.
- Do not add `<<include>>` or `<<extend>>` relationships unless the implementation clearly requires them.

## Visual design and output

Use a landscape canvas with ample white space, readable text, and a restrained professional palette inspired by Verifai: navy `#0B3D91`, teal `#147A72`, gold `#F4B400`, red `#D7263D`, pale blue-gray background, and dark slate text. Use a subtle accent to distinguish guest-only cases; keep the diagram understandable in grayscale too.

Deliver an **editable SVG** with a descriptive title and accessible text description. Keep the diagram uncluttered: combine tightly related account actions only when the label remains clear, and do not shrink text just to fit. Include a small note that the diagram reflects implemented application behavior. If a detail cannot be verified, leave it out instead of inventing a feature.
