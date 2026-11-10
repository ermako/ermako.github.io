// Tagline phrases under your name. Each list is shown in random order, every
// phrase once before any repeats. Blank entries ("") are ignored.

// Timings, in milliseconds
const TAGLINE_FIRST_MS = 10000;    // how long the first phrase stays (counted from when it scrolls into view)
const TAGLINE_CHANGE_MS = 10000;    // how often the phrase changes on its own after that
const TAGLINE_FADE_OUT_MS = 1000;   // fade out
const TAGLINE_PAUSE_MS = 50;      // pause while hidden, before the new phrase
const TAGLINE_FADE_IN_MS = 1300;   // fade in

// Always shown first
const TAGLINE_FIRST = "it was cloudy, but i used my imagination.";

// Shown on their own, one every TAGLINE_CHANGE_MS. Keep these tame.
const TAGLINES_AUTO = [
  "it was cloudy, but i used my imagination.",
  "dilute juice, not semantics.",
  "end browser tab chaos.",
  "moderation is underrated.",
  "i'd get so much more done if i was less efficient.",
];

// Shown when someone presses "next" (they asked for it). While this list
// is empty, "next" uses the automatic list instead.
const TAGLINES_NEXT = [
  "taking it easy.",
  "people tend to forget that water is a product of combustion.",
  "i gave the sky a hug.",
  "petrichor.",
  "no, you're not that strong and that's okay.",
  "fiery should not be spelled that way.",
  "few acronyms save more time than they waste.",
  "homo sapiens is a pretty invasive species.",
  "evil should be less socially acceptable.",
  "this is not a drill.",
  "have you gone for a walk today?",
  "🫠.",
  "a freath of bresh air",
];

// Shown instead of a phrase on every 10th press of "next"
const TAGLINE_EASTER_EGG = "okay, at this rate, we're gonna run out.";
