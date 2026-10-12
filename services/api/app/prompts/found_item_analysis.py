"""Exact active two-view prompt from the supplied SAULI backend handoff."""

FOUND_ITEM_ANALYSIS_PROMPT = """
Analyze all supplied photographs as different views of the same reported
lost item. Combine the evidence into exactly one JSON object. Do not count
the same object or component more than once merely because it appears in
multiple views.

Exactly two images are supplied:
1. Full front view.
2. Full back view.

You must inspect every image separately before combining the results. Include
view_observations with exactly two entries. Each entry must state the image
number, visible region, image quality, and any independently observed damage.

If fewer than two views can be examined, set needs_review to true. Never claim
that a surface has no visible damage when that surface is hidden, blurry,
overexposed, too small, or outside the image.

Prioritize physical geometry over color. Inspect the silhouette, surface
curvature, highlight continuity, shadows, and symmetry. A localized inward
curve, flattened area, or repeated contour irregularity visible from multiple
angles must be reported as a dent.

Perform the following inspection internally before producing the JSON:

1. VIEW CONSISTENCY
Determine whether all photographs show the same physical item. Compare its
shape, color, markings, attachments, damage, and component placement.

2. OBJECT IDENTIFICATION
Identify the item using:
- generic_name: the common general name, such as "water bottle".
- object_name: a specific everyday description supported by visible evidence.
- alternative_names: other common names someone might search for.
Use visible non-sensitive product names and model markings when legible.
Do not invent a brand, model, material, or feature.

3. COMPONENT COUNTING
Count unique primary objects and visible functional components. A component
seen in several views must be counted only once. If a component is hidden or
overlapping, provide the minimum clearly visible count and mark it as an
estimate.

4. MANDATORY CONDITION INSPECTION
Inspect every visible surface before assigning the overall condition.

For every visible component, examine:
- the outer silhouette and contour;
- symmetry and normal geometry;
- changes in reflections, highlights, and shadows;
- inward or outward deformation;
- flattened, compressed, bent, or warped areas;
- scratches, scuffs, chips, cracks, stains, discoloration, and missing parts;
- wear around edges, corners, lids, handles, straps, screens, and connectors.

For rigid bottles and similar containers, specifically inspect:
- the neck and shoulder immediately below the lid;
- the complete left and right side walls;
- the front and rear body surfaces;
- the bottom edge and base.

A localized inward curve, flattened section, distorted contour, or interruption
in an otherwise continuous surface highlight may indicate a dent. If the same
deformation is supported by more than one view, report it as confirmed visible
damage. If it appears in only one view and could be lighting or reflection,
report it as uncertain or probable damage.

Do not state "no visible damage" merely because the item's color looks smooth.
Use "no_visible_damage" only when the relevant surface is clearly shown at
sufficient size, focus, and lighting. Otherwise use "not_assessable".

For every surface assessment:
- status must be "visible_damage", "no_visible_damage", or "not_assessable".
- damage_types must list specific observed damage such as "dent", "scratch",
  "scuff", "crack", "chip", "stain", "bending", or "discoloration".
- location must identify where the damage appears.
- severity must be "minor", "moderate", "severe", or null.
- certainty must be "confirmed", "probable", or "uncertain".
- evidence must describe the visible observation, not an unsupported conclusion.

Overall condition:
- "new": no observable use or wear.
- "good": intact with no damage or only minor cosmetic wear.
- "fair": visible dent, deformation, or moderate wear, but still generally intact.
- "poor": broken, severely damaged, or missing important components.
- "unknown": the condition cannot be assessed reliably.

5. MATERIAL INSPECTION
Return material as a flat JSON array of short strings, never as an object. When
the component matters, include it in the string, for example "body: coated
metal" or "lid: plastic". If material cannot be confirmed visually, describe it
as likely or leave the array empty rather than claiming certainty.

6. STORAGE SIZE
Choose exactly one storage_size for the whole item, including handles, straps,
or other attached parts. Use "pocket" for small personal objects such as a
wristwatch, keys, jewelry, a wallet, or a phone. Use "medium" for bulkier
objects such as a water bottle, lunchbox, book, bag, or clothing. Judge the
item's likely real-world dimensions from its type and visible features, not
from how many pixels it occupies in the photograph. If scale or fit is unclear,
choose the safer medium size and explain the uncertainty in uncertainty_notes.
This is an estimate; do not claim a measured fit from photographs.

Return every one of these fields:
views_consistent, generic_name, object_name, alternative_names, object_count,
component_counts, count_is_estimate, count_confidence, counting_notes,
category, subcategory, document_kind, document_owner_name, colors, material, brand, model_or_variant,
visible_markings, functional_components, condition, condition_visibility,
condition_confidence, surface_assessments, condition_details, patterns,
distinctive_features, likely_use, short_description, storage_size, confidence, needs_review,
uncertainty_notes, extraction_summary, received_view_count, view_observations.

Data requirements:
- views_consistent, count_is_estimate, and needs_review: boolean.
- object_count: integer.
- alternative_names, colors, material, visible_markings,
  functional_components, condition_details, patterns, distinctive_features,
  counting_notes, and uncertainty_notes: arrays of strings.
- Every entry in condition_details must be a string, never an object.
- generic_name, object_name, category, subcategory, condition_visibility,
  likely_use, short_description, and extraction_summary: single strings, never
  arrays or objects.
- component_counts: array of objects with component, count, and
  count_is_estimate.
- surface_assessments: array of objects with component, status, damage_types,
  location, severity, certainty, and evidence.
- count_confidence, condition_confidence, and confidence:
  "high", "medium", or "low".
- storage_size: exactly "pocket" or "medium".
- brand and model_or_variant: string or null.
- document_kind: "none", "school ID", "driver's license", "government ID",
  "passport", "bank card", "identification card", or "sensitive document".
- document_owner_name: the clearly readable printed person's name on an ID,
  or null. Never guess a name or copy any other private text.
- extraction_summary: concise searchable summary containing the supported
  item type and name, count, colors, visible brand and model (if any),
  materials, markings, distinctive features, damage and its location,
  condition, and important uncertainty. Do not omit a known searchable detail
  or invent one to make the summary sound complete.
- received_view_count: integer.
- view_observations: array of objects containing image_index, visible_region,
  image_quality, damage_observations, and notes. damage_observations and notes
  must each be arrays of strings.

Privacy rules:
Do not perform facial recognition. If either image shows an ID or another
sensitive document, set document_kind even when the document is inside a
holder. Return only its type and a clearly readable printed owner name in
document_owner_name. Never copy numbers, addresses, signatures, barcodes,
contact details, or other private document text into ANY field.
Non-sensitive product branding and model markings on ordinary objects may be
reported.

Return only one valid JSON object. Do not return Markdown, commentary, or the
internal inspection process.
""".strip()

