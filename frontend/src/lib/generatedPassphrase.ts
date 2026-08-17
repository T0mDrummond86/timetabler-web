/** A random four-word passphrase for a new or reset account.
 *
 * Replaces a single shared default. One publicly-known starting password
 * across every account meant that between an admin creating an account and the
 * user first signing in, anyone who knew the convention could sign in as them —
 * and the convention was printed on the admin screen.
 *
 * Generated in the browser because that is where it has to be shown: the admin
 * reads it once and passes it on, and the account carries
 * ``must_change_password`` so it only ever survives one sign-in.
 */

/** Short, unambiguous, unlikely to be mistyped when read aloud. */
const WORDS = [
  "amber", "anchor", "apple", "arrow", "autumn", "bamboo", "beacon", "birch",
  "bishop", "bramble", "bridge", "bronze", "burrow", "canyon", "cedar", "chorus",
  "cinder", "clover", "cobalt", "comet", "copper", "coral", "cotton", "crimson",
  "cyprus", "dahlia", "dapple", "dawn", "delta", "dingo", "domino", "dune",
  "ember", "falcon", "fathom", "fennel", "fjord", "flint", "forest", "fossil",
  "garnet", "gecko", "ginger", "granite", "harbour", "hazel", "heron", "hollow",
  "indigo", "ivory", "jasper", "jetty", "juniper", "kelpie", "kettle", "lagoon",
  "lantern", "lattice", "lemon", "lichen", "lilac", "linen", "lumen", "magnet",
  "mallee", "mango", "maple", "marble", "meadow", "mellow", "mesa", "meteor",
  "mimosa", "mineral", "mirror", "monsoon", "mulberry", "nectar", "nimbus",
  "nutmeg", "oasis", "olive", "onyx", "opal", "orbit", "orchid", "osprey",
  "otter", "paddock", "pampas", "pebble", "pelican", "pepper", "pewter",
  "pigment", "pinion", "plateau", "plover", "pollen", "poplar", "prairie",
  "quartz", "quiver", "rafter", "ramble", "rattan", "ridge", "rosella", "russet",
  "saffron", "sage", "sandal", "sapphire", "sequoia", "shale", "shelter",
  "sienna", "silver", "sorrel", "spinner", "spruce", "starling", "stipple",
  "summit", "sundial", "syrup", "tamarind", "tandem", "teal", "tempo", "thicket",
  "thistle", "timber", "topaz", "trellis", "tundra", "turmeric", "umber",
  "valley", "velvet", "verbena", "vessel", "walnut", "wattle", "willow",
  "windmill", "yarrow", "zephyr", "zinnia",
];

/**
 * Four random words joined by hyphens — comfortably over the 14-character
 * minimum, and readable enough to pass on verbally.
 *
 * Uses crypto.getRandomValues, and rejection-samples so every word is equally
 * likely: `% length` on a raw 32-bit value quietly favours the earlier words.
 */
export function generatePassphrase(wordCount = 4): string {
  const picked: string[] = [];
  const limit = Math.floor(0x100000000 / WORDS.length) * WORDS.length;
  const buf = new Uint32Array(1);
  while (picked.length < wordCount) {
    crypto.getRandomValues(buf);
    if (buf[0] >= limit) continue; // discard, to keep the draw uniform
    picked.push(WORDS[buf[0] % WORDS.length]);
  }
  return picked.join("-");
}
