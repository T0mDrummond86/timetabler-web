/** The passphrase rule, kept in step with the backend's policy.
 *
 * Mirrors app/services/password_policy.py — the server is the authority, and
 * this exists so the rule can be stated before someone submits rather than
 * only in the rejection.
 */

/** ACSC ISM: 14 characters where a passphrase is a single factor. */
export const PASSPHRASE_MIN_LENGTH = 14;

export const PASSPHRASE_REQUIREMENTS =
  `Use at least ${PASSPHRASE_MIN_LENGTH} characters — four random words is ideal. ` +
  "Spaces are fine, and there are no upper/lower/symbol rules.";
