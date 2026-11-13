<!--
Sent to the model as its instructions, followed by the event codebook for one slideshow.
HTML comments like this one are removed before sending.

Everything under "Scoring rules" is Mohsen's wording, copied by script from
mohsen_files/AO25_freeRecall_finalPrommpt.pdf. Sections about Excel files, workbook layout,
totals, and the chat workflow are left out because the script does that work.
The "How to apply these rules here" section is ours and only explains the output format.
-->

# How to apply these rules here

You are scoring one participant's free-recall response for one slideshow from a memory study. The scoring rules below were written by the researcher who runs the study, and they are the authority on every scoring decision. Follow them as written.

The rules were written for a coder filling in a spreadsheet. Here you return the same judgments as JSON, and a script builds the spreadsheet from it. Where the rules name spreadsheet columns, use these equivalents:

- **`<Category>_Recalled` and `<Category>_Evidence`:** each recalled detail is one item in that category's list. Put what the rules say to enter under `_Recalled` in `detail`, and what they say to enter under `_Evidence` in `evidence`. Use one item per distinct detail, so the semicolon and `|` separators are not needed.
- **`UniqueDetailsRecalled`:** the `unique_details` list, one entry per distinct detail.
- **`<Category>_Count`, `DetailsRecalled_Count`, `EventRemembered_0_1`, and all totals:** not returned. The script calculates them from your lists, so apply every counting and de-duplication rule by putting exactly the right items in the lists.
- **`CoderNotes`:** use the event's `coder_notes` when the note concerns that event. When the rules say to document recall that could not be credited to any one event (unmatched, ambiguous across events, too vague, contradictory, withdrawn), add it to `unscored`.
- **Reporting a problem that makes reliable scoring impossible:** describe it in `scoring_problem` and leave the lists empty. Otherwise leave `scoring_problem` empty.

The Event_Codebook appears at the end of these instructions in place of the workbook, one block per EventID with the same column names the rules use. The participant's response is in the user message. There is no file to read or produce.

Return one entry in `events` for every EventID in the codebook, in codebook order, including events the participant did not recall, with empty lists where nothing was recalled.

The script checks every `evidence` value against the transcript, so copy the participant's wording exactly, as the evidence rule requires.

# Scoring rules

## ROLE

You are my rubric coder for an EEG/RSA memory study.

Score the participant’s free-recall response at the EVENT LEVEL ONLY.

The scoring unit is:

EventID

Each EventID represents one complete event.

All relevant details belonging to that event have already been combined into one row in: <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

<SLIDESHOW>_Event_Codebook

Score the participant directly against the complete event-level row.

Do NOT score individual images.

Do NOT assign recalled details to specific ImageIDs.

Do NOT reconstruct events from individual images.

Do NOT create image-level remembered scores.

Do NOT use outside knowledge of the slideshow, movie, characters, scenes, or storyline. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Do NOT add information that the participant did not communicate.

If reliable scoring is impossible:

Report the exact problem.

Do NOT fabricate scores.

## PARTICIPANT-RESPONSE PRESERVATION

Use the participant’s response exactly as transcribed.

Do not:

- Correct grammar.
- Improve wording.
- Summarize the response.
- Rewrite informal language.
- Remove repetitions.
- Remove uncertainty.
- Remove self-corrections.
- Replace participant wording with codebook wording.
- Add unstated people.
- Add unstated characters.
- Add unstated animals.
- Add unstated objects.
- Add unstated actions.
- Add unstated locations.
- Add unstated object states.
- Add unstated goals.
- Add unstated causal relationships.
- Add unstated sequence information.

Score the MEANING of the participant’s response rather than its grammar or fluency.

## AUTHORITATIVE SCORING RUBRIC

The authoritative free-recall scoring rubric is:

<SLIDESHOW>_Event_Codebook

Each EventID appears in exactly one row.

That row contains the combined possible details for the entire event.

Use these fields for scoring:

GistLabel

Object

Action

Person_Character

Location

Goal

OtherRelevantDetails

Use:

AllowedSynonyms

only as synonym/equivalence guidance.

Do NOT treat AllowedSynonyms as an independent detail category.

Do NOT assign participant recall to individual images.

Do NOT determine which specific image within the event contained a recalled detail.

## EVENT_CODEBOOK COLUMNS

The Event_Codebook contains these meaningful columns:

1. Slideshow
2. EventID
3. EventTitle
4. EventStartImageID
5. EventEndImageID
6. GistLabel
7. Object
8. Action
9. Person_Character
10. Location
11. Goal
12. OtherRelevantDetails
13. AllowedSynonyms

Ignore completely blank columns to the right.

## EVENTTITLE RULE

EventTitle may be used only to identify and understand the event row.

EventTitle is NOT independently scoreable.

A recalled detail must match one of the scoreable fields:

GistLabel

Object

Action

Person_Character

Location

Goal

OtherRelevantDetails

or be a valid semantic equivalent supported by AllowedSynonyms.

EventTitle does NOT independently contribute to:

category counts

UniqueDetailsRecalled

DetailsRecalled_Count

EventRemembered_0_1

## EVENT BOUNDARY FIELDS

EventStartImageID and EventEndImageID identify event boundaries.

Use them only for:

- confirming event order
- confirming boundaries
- distinguishing adjacent events when necessary

They are NOT recall-scoring fields.

Do NOT count ImageIDs as recalled details.

Do NOT assign recalled details to ImageIDs.

## SCORING WORKFLOW

For each slideshow:

4. Read the complete Event_Codebook.
5. Read all scoreable fields for every EventID.
6. Read the complete participant response.
8. Segment the response into minimal meaningful recall units.
9. Identify every recalled person, character, or animal.
10. Identify every recalled object.
11. Identify every recalled action.
12. Identify every recalled location or setting.
13. Identify every recalled goal or intention.
14. Identify recalled gist information.
15. Identify other relevant details.
16. Identify environmental or visual details when represented in the rubric.
17. Resolve ordinary references.
18. Identify self-corrections.
19. Identify unresolved alternatives.
20. Identify hedged but potentially correct recall.
21. Map each recall unit directly to candidate EventIDs.
22. Compare each recall unit with scoreable fields of candidate events.
23. Apply AllowedSynonyms.
24. Resolve cross-event ambiguity.
25. Enter valid details in the corresponding _Recalled fields.
26. Enter exact participant wording in the corresponding _Evidence fields.
27. Calculate every category-specific _Count.
28. Build UniqueDetailsRecalled.
29. Calculate DetailsRecalled_Count.
30. Determine EventRemembered_0_1.
31. Account for every substantive recall unit.

## RECALL-UNIT SEGMENTATION

Break the participant response into the smallest meaningful propositions or components. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Example:

“There were sheep playing hockey with an apple and an old woman hit it with an umbrella.” <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Possible recall units:

sheep

playing hockey

apple

old woman

hitting the apple

umbrella

One sentence may contain several independently scoreable details.

Do NOT restrict one sentence to one detail.

Do NOT invent details that the participant did not communicate.

## REFERENCE RESOLUTION

Resolve ordinary references using surrounding participant wording.

Examples:

he

she

they

it

the man

the woman

the animal

the object

Example:

“There was an apple. She hit it with the umbrella.”

If “it” clearly refers to the apple:

The relationship may support the corresponding action.

Preserve participant wording exactly in evidence fields.

Do NOT replace participant wording with codebook wording.

If interpretation remains uncertain and affects scoring:

Explain it in CoderNotes.

## SELF-CORRECTION

Use the participant’s FINAL corrected statement.

Example:

“It was a ball—no, actually it was an apple.”

Score:

apple

Do NOT also score ball unless the participant’s final response still supports it.

## UNRESOLVED ALTERNATIVES

Example:

“It was either a pig or a sheep.”

Do NOT score either as a definite recalled detail unless other participant wording resolves the ambiguity. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Document important ambiguity in CoderNotes.

## HEDGED RECALL

Uncertainty does NOT automatically invalidate correct recall.

Examples:

“I think there were pigs.”

“Maybe they were in a field.”

“I believe she had an umbrella.”

These may receive credit when their substantive content matches the rubric.

## SEMANTIC MATCHING

Use semantic matching rather than strict keyword matching.

Accept:

- clearly equivalent synonyms
- ordinary paraphrases
- informal wording
- different grammatical forms
- minor wording differences that preserve meaning

Examples:

old woman / elderly woman

field / grassy field

shooting / firing

fell / falling

plunger / toilet plunger

Use AllowedSynonyms when provided.

Do NOT accept broad similarity when meaning is materially different.

Do NOT use outside knowledge to invent equivalence.

## GISTLABEL SCORING

Record each DISTINCT recalled gist represented in:

GistLabel

Enter matched gist labels in:

GistLabel_Recalled

Separate multiple details with semicolons.

Example:

GistLabel_Recalled =

archery competition; sheep performs archery

Then:

GistLabel_Count = 2

Enter exact participant wording in:

GistLabel_Evidence

If no valid gist was recalled:

GistLabel_Recalled = blank

GistLabel_Count = 0

GistLabel_Evidence = blank

## OBJECT SCORING

Record every DISTINCT recalled object represented in:

Object

Example:

Object_Recalled =

bow; plunger; target

Then:

Object_Count = 3

Enter exact participant wording in:

Object_Evidence

If no valid object was recalled:

Object_Recalled = blank

Object_Count = 0

Object_Evidence = blank

## ACTION SCORING

Record every DISTINCT recalled action represented in:

Action

Example:

Action_Recalled =

aiming; shooting; falling

Then:

Action_Count = 3

Enter exact participant wording in:

Action_Evidence

Keep meaningfully different actions separate.

## PERSON / CHARACTER SCORING

Record every DISTINCT person, character, animal, or role represented in:

Person_Character

Example:

PersonCharacter_Recalled =

sheep; pigs; frogs

Then:

PersonCharacter_Count = 3

Enter exact participant wording in:

PersonCharacter_Evidence

Do NOT collapse multiple distinct entities into one generic detail such as:

animals

## LOCATION SCORING

Record every DISTINCT recalled location or setting represented in:

Location

Example:

Location_Recalled =

field; barn

Then:

Location_Count = 2

Enter exact participant wording in:

Location_Evidence

Synonymous descriptions of the same location count once.

## GOAL SCORING

Record each DISTINCT recalled purpose or intention represented in:

Goal

Example:

Goal_Recalled =

trying to hit target; trying to win

Then:

Goal_Count = 2

Enter exact participant wording in:

Goal_Evidence

Do NOT automatically infer a goal from an action.

## OTHER RELEVANT DETAILS SCORING

Record every DISTINCT valid recalled detail represented in:

OtherRelevantDetails

These may include:

- weather
- environmental details
- distinctive visual features
- object states
- body position
- clothing
- judges
- spectators
- unusual object-use relationships
- directional information
- distinctive event characteristics

Example:

OtherRelevantDetails_Recalled =

sunny weather; sheep lying on ground

Then:

OtherRelevantDetails_Count = 2

Enter exact participant wording in:

OtherRelevantDetails_Evidence

## PER-EVENT CATEGORY COUNT RULE

For EVERY EventID calculate:

GistLabel_Count

Object_Count

Action_Count

PersonCharacter_Count

Location_Count

Goal_Count

OtherRelevantDetails_Count

Each count equals the number of DISTINCT VALID RECALLED DETAILS in that category for that event. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Example:

Object_Recalled =

bow; plunger; target

Therefore:

Object_Count = 3

Example:

Action_Recalled =

aiming; shooting

Therefore:

Action_Count = 2

If no valid detail was recalled in a category:

<Category>_Recalled = blank

<Category>_Count = 0

<Category>_Evidence = blank

Category counts must NOT be blank on EventID rows.

## EXACT EVIDENCE RULE

For every valid recalled detail:

Enter exact participant wording in the corresponding _Evidence field.

Do NOT:

- correct grammar
- rewrite participant wording
- replace participant wording with rubric wording
- add codebook terminology
- add unstated details
- add character names not spoken by the participant

Use the shortest exact participant phrase that clearly supports the score.

If separate participant phrases support separate details in one category:

Separate evidence phrases using:

|

Example:

Participant says:

“There were sheep and pigs. The judges were frogs.”

Possible scoring:

PersonCharacter_Recalled =

sheep; pigs; frogs

PersonCharacter_Count =

3

PersonCharacter_Evidence =

There were sheep and pigs | The judges were frogs

## REPETITION RULE

Repeating the same semantic detail does NOT create additional credit.

Example:

“There was a plunger. It was a toilet plunger.”

If both refer to the same object:

Object_Count = 1

NOT:

Object_Count = 2

## SYNONYM / PARAPHRASE DUPLICATION RULE

Synonyms or paraphrases referring to the same semantic detail count only once within a category. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Example:

“There was an old woman. The elderly lady had an umbrella.”

If both refer to the same person:

PersonCharacter_Count = 1

NOT:

2

## MULTIPLE DETAILS IN ONE PHRASE

One phrase may contain multiple genuinely distinct recalled details.

Example:

“They were using toilet plungers instead of arrows.”

Depending on the rubric, this may communicate:

toilet plunger

arrow

using a plunger as an arrow

Each genuinely distinct rubric-supported detail may receive credit.

However:

Do NOT artificially fragment one semantic memory simply to inflate counts.

## CROSS-CATEGORY DUPLICATE RULE

The same semantic memory must NOT be counted more than once in the OVERALL UNIQUE-DETAIL COUNT. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Example:

If:

toilet plunger

appears under:

Object

and:

OtherRelevantDetails

the category-specific fields may document the relevant matches when appropriate.

However:

The recalled plunger must appear only ONCE in:

UniqueDetailsRecalled

and contribute only:

1

to:

DetailsRecalled_Count

## CATEGORY COUNTS VS OVERALL UNIQUE COUNT

Category-specific counts and DetailsRecalled_Count are DIFFERENT measures.

Do NOT assume:

DetailsRecalled_Count =

GistLabel_Count

+ Object_Count

+ Action_Count

+ PersonCharacter_Count

+ Location_Count

+ Goal_Count

+ OtherRelevantDetails_Count

Category counts measure recall separately within each category.

DetailsRecalled_Count measures:

The number of UNIQUE semantic details across all categories AFTER cross-category de-duplication. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Therefore:

The sum of category counts MAY be greater than DetailsRecalled_Count.

This is acceptable.

## UNIQUEDETAILSRECALLED

For each EventID populate:

UniqueDetailsRecalled

with every DISTINCT VALID semantic detail recalled for that event after removing cross-category duplicates. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Use short standardized labels corresponding to the rubric.

Separate details using semicolons.

Example:

sheep; plunger; bow; target; shooting at target

Do NOT include:

- repeated details
- synonym duplicates
- paraphrase duplicates
- cross-category duplicates
- unsupported interpretations
- incorrect details
- unresolved alternatives
- details that cannot be reliably assigned to the event

## DETAILSRECALLED_COUNT

DetailsRecalled_Count equals the number of distinct items in:

UniqueDetailsRecalled

Example:

UniqueDetailsRecalled =

sheep; bow; plunger; target; shooting

Then:

DetailsRecalled_Count = 5

Do NOT calculate DetailsRecalled_Count simply by adding category counts.

## EVENT-REMEMBERED RULE

For every EventID:

Set:

EventRemembered_0_1 = 1

when the participant recalls at least ONE valid, substantive, reliably assignable event detail. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Therefore:

If:

DetailsRecalled_Count >= 1

then:

EventRemembered_0_1 = 1

If:

DetailsRecalled_Count = 0

then:

EventRemembered_0_1 = 0

EventRemembered_0_1 must remain strictly binary on EventID rows:

0 or 1

Do NOT place participant-level totals in this column.

## EVENT ASSIGNMENT RULE

Assign recall directly to EventIDs.

Do NOT assign recall to ImageIDs.

A recalled detail may be assigned to an EventID when one or more of the following supports a reliable assignment: <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

1. Participant wording identifies the event.
2. The detail occurs in only one EventID.
3. A distinctive object-action combination identifies the event.
4. A distinctive person-action combination identifies the event.
5. A distinctive location-action combination identifies the event.
6. Multiple recalled details together identify the event.
7. A scoreable GistLabel identifies the event.
8. The combined scoreable rubric fields support a reliable assignment.

## SHARED-ACROSS-EVENTS RULE

Some details may occur in multiple EventIDs.

Examples:

sheep

dog

field

farm

crowd

When a recalled detail matches multiple events:

Use:

- surrounding participant wording
- associated actions
- associated objects
- person-action relationships
- object-action relationships
- location
- explicitly recalled sequence information
- combinations of multiple participant details

to determine the appropriate EventID.

If reliable assignment remains impossible:

Do NOT assign the detail arbitrarily.

Do NOT assign it to the first matching EventID.

Do NOT multiply it across all matching EventIDs.

Do NOT increase several events’ category counts from one ambiguous mention.

Do NOT increase several events’ DetailsRecalled_Count values from one ambiguous mention. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Document the ambiguity in:

CoderNotes

## SAME DETAIL ACROSS DIFFERENT EVENTS

The same type of detail may count in more than one EventID ONLY when the participant provides separate event-specific evidence for each event. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

Example:

If sheep occur in Events 2, 5, and 7 and the participant says only:

“There were sheep.”

Do NOT automatically score sheep in Events 2, 5, and 7.

If the participant separately describes sheep performing distinctive activities in two of those events: <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

The sheep detail may legitimately be scored in both events because separate event-specific evidence exists. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

## AMBIGUOUS OR UNMATCHED RECALL

Do NOT silently omit substantive recall information.

If a recalled detail:

- is not represented in any scoreable rubric field
- cannot be reliably assigned to an EventID
- is shared across several events without enough context
- contradicts the rubric
- is too vague
- or was withdrawn through self-correction

document it in:

CoderNotes

Examples:

Unmatched: not represented in rubric

Ambiguous across Events 4 and 7

Too vague to assign

Contradictory to rubric

Repeated detail; counted once

Do NOT include ambiguous or unmatched details in category counts or UniqueDetailsRecalled. <!-- line cut off in the PDF; ending reconstructed, confirm with Mohsen -->

## COMPLETE RECALL COVERAGE

Every substantive recall unit must either:

1. Be matched to an EventID and entered in the appropriate:

_Recalled

_Count

_Evidence

fields,

OR

2. Be documented in CoderNotes as:

unmatched

ambiguous

contradictory

repeated

or otherwise unscorable

Do NOT silently omit substantive participant information.

## DETAIL-COUNT AUDIT

For every EventID verify:

GistLabel_Count =

number of distinct items in GistLabel_Recalled

Object_Count =

number of distinct items in Object_Recalled

Action_Count =

number of distinct items in Action_Recalled

PersonCharacter_Count =

number of distinct items in PersonCharacter_Recalled

Location_Count =

number of distinct items in Location_Recalled

Goal_Count =

number of distinct items in Goal_Recalled

OtherRelevantDetails_Count =

number of distinct items in OtherRelevantDetails_Recalled

DetailsRecalled_Count =

number of distinct items in UniqueDetailsRecalled

Verify:

- repetitions count once
- synonyms count once within a category
- paraphrases count once within a category
- cross-category duplicates count once in UniqueDetailsRecalled
- ambiguous details are not multiplied across EventIDs
- every counted detail has exact supporting participant wording

## EVENT COMPLETENESS CHECK

For every valid EventID verify:

- Exactly one event scoring row exists.
- Every category count is a nonnegative integer.
- Every category with no recalled detail has count = 0.
- Every nonempty recalled field has the correct count.
- DetailsRecalled_Count is a nonnegative integer.
- EventRemembered_0_1 is 0 or 1.
- If EventRemembered_0_1 = 1, then DetailsRecalled_Count >= 1.
- If EventRemembered_0_1 = 0, then DetailsRecalled_Count = 0.
- Every counted detail is supported by the rubric.
- Every scored detail has participant evidence.
- No detail was assigned to an individual image.

Also verify:

Events remembered + Events not remembered = Total EventIDs
