package io.github.krszozda.latawiec

/**
 * A player the shell can quiet while its screen is covered.
 *
 * DivKit's own DivPlayer has play/pause but no memory of whether the
 * video was playing, so a covered-then-uncovered screen would either
 * restart a paused video or leave a playing one silent. Both players in
 * the shell implement this instead.
 */
interface HoldablePlayer {
    /** Covered by another screen: stop, remembering whether it played. */
    fun hold()

    /** Back on top: pick up only what was playing. */
    fun resume()
}
